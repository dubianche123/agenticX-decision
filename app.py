#!/usr/bin/env python3
"""Local web console for the decision-audit harness.

Flow mirrors the real pipeline:
  1. paste a rule -> decomposer LLM maps it onto a template spec
  2. pick a workspace (a loose PDF or a material-package org folder
     under data/)
  3. run -> SSE stream of per-item verdicts, evidence, usage

Settings support per-stage models (decompose / main / vision); each
stage may override base_url/model and inherits the global key otherwise.

Usage:
  python app.py                    # http://127.0.0.1:8620
  python app.py --mock             # offline demo, no key needed
  python app.py --port 9000

The server binds to 127.0.0.1 on purpose: it can read client material
and holds the API key locally — do not expose it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

import mzt_common
import decomposer
from engine import audit_stream
from sample_data import RULES

app = FastAPI(title="AgenticX Decision Console")
STATIC_DIR = mzt_common.REPO_ROOT / "static"
MOCK = False


def _rules_file() -> Path:
    d = mzt_common.data_dir()
    if not d.exists():
        d.mkdir(parents=True)
    return d / "rules.json"


def _load_rules() -> List[Dict[str, Any]]:
    f = _rules_file()
    if not f.exists():
        return deepcopy(RULES)
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("rules", [])
    except Exception:
        return []


def _save_rules(rules: List[Dict[str, Any]]) -> None:
    _rules_file().write_text(
        json.dumps({"rules": rules}, ensure_ascii=False, indent=2), encoding="utf-8")


def _next_rule_id(rules: List[Dict[str, Any]]) -> str:
    nums = []
    for r in rules:
        rid = str(r.get("id", ""))
        if rid.startswith("r") and rid[1:].isdigit():
            nums.append(int(rid[1:]))
    return f"r{max(nums, default=0) + 1}"


# ─────────────────────── Static ───────────────────────

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/app.js")
async def app_js() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.js", media_type="text/javascript")


@app.get("/style.css")
async def style_css() -> FileResponse:
    return FileResponse(STATIC_DIR / "style.css", media_type="text/css")


# ─────────────────────── Health / settings ───────────────────────

@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "mock": MOCK}


@app.get("/api/settings")
async def get_settings() -> Dict[str, Any]:
    profile = mzt_common.load_profile()
    def public_config(config):
        if not isinstance(config, dict):
            return {}
        visible = {k: config[k] for k in ("provider", "base_url", "model") if k in config}
        if visible.get("base_url"):
            try:
                url = urlsplit(str(visible["base_url"]))
                visible["base_url"] = urlunsplit((url.scheme, url.netloc.rsplit("@", 1)[-1], url.path, "", ""))
            except ValueError:
                visible["base_url"] = ""
        return visible
    visible = public_config(profile)
    visible["stages"] = {k: public_config(v) for k, v in (profile.get("stages") or {}).items()
                         if k in ("decompose", "main", "vision")}
    return {"profile": visible, "key_configured": bool(mzt_common.read_key()),
            "mock": MOCK}


@app.post("/api/settings")
async def post_settings(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    profile_path = mzt_common.config_path(".mzt_demo_profile.json")
    profile: Dict[str, Any] = {}
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            profile = {}

    key = (body.get("key") or "").strip()
    def check_url(config):
        value = config.get("base_url")
        if value:
            try:
                url = urlsplit(str(value))
                if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
                    raise ValueError()
            except ValueError:
                raise HTTPException(422, "端点必须是无内嵌凭据和查询参数的 HTTP(S) URL")
    check_url(body)
    for config in (body.get("stages") or {}).values():
        if isinstance(config, dict):
            check_url(config)
    if key:
        key_path = mzt_common.config_path(".mzt_demo_key")
        mzt_common.write_private(key_path, key)

    for field in ("provider", "base_url", "model"):
        if field in body and body[field] is not None:
            profile[field] = str(body[field]).strip()
    stages = body.get("stages") or {}
    if isinstance(stages, dict):
        merged: Dict[str, Any] = profile.get("stages") or {}
        for stage in ("decompose", "main", "vision"):
            incoming = stages.get(stage)
            if isinstance(incoming, dict):
                merged[stage] = {
                    "base_url": (str(incoming.get("base_url")).strip()
                                 if incoming.get("base_url") else None),
                    "model": (str(incoming.get("model")).strip()
                              if incoming.get("model") else None),
                }
        profile["stages"] = merged

    mzt_common.write_private(profile_path, json.dumps(profile, ensure_ascii=False, indent=2))
    return {"ok": True, "key_configured": bool(mzt_common.read_key())}


# ─────────────────────── Workspaces ───────────────────────

@app.get("/api/workspaces")
async def list_workspaces() -> Dict[str, Any]:
    root: Path = mzt_common.data_dir()
    items: List[Dict[str, Any]] = []
    if root.exists():
        pdfs = sorted(root.rglob("*.pdf"))
        # loose PDFs directly under data/ become single-PDF workspaces
        for pdf in pdfs:
            rel = pdf.relative_to(root)
            if len(rel.parts) == 1:
                items.append({"id": f"pdf:{rel}", "kind": "pdf",
                              "name": pdf.stem, "path": str(rel)})
        # any directory containing PDFs becomes a package workspace
        seen = set()
        for pdf in pdfs:
            d = pdf.parent
            if d == root or d in seen:
                continue
            seen.add(d)
            rel = d.relative_to(root)
            count = sum(1 for _ in d.rglob("*.pdf"))
            items.append({"id": f"pkg:{rel}", "kind": "package",
                          "name": rel.parts[-1], "path": str(rel),
                          "files": count})
    items.append({"id": "demo", "kind": "demo", "name": "离线演示工作区（内置剧本）"})
    return {"workspaces": items, "data_dir": str(root)}


def resolve_workspace(workspace_id: str) -> Dict[str, Any]:
    root = mzt_common.data_dir().resolve()
    if workspace_id == "demo":
        return {"kind": "demo", "name": "离线演示工作区"}
    try:
        kind, rel = workspace_id.split(":", 1)
    except ValueError:
        raise HTTPException(400, f"非法 workspace id: {workspace_id}")
    try:
        target = mzt_common.contained_path(root, rel)
    except ValueError:
        raise HTTPException(400, "workspace 越界")
    if kind == "pdf":
        if not target.exists():
            raise HTTPException(404, f"PDF 不存在: {rel}")
        return {"kind": "pdf", "name": target.stem, "path": target}
    if kind == "pkg":
        if not target.is_dir():
            raise HTTPException(404, f"目录不存在: {rel}")
        return {"kind": "package", "name": target.name, "org_dir": target}
    raise HTTPException(400, f"非法 workspace 类型: {kind}")


# ─────────────────────── Rules ───────────────────────

@app.get("/api/rules")
async def get_rules() -> Dict[str, Any]:
    return {"rules": _load_rules()}


@app.post("/api/rules")
async def add_rule(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    spec = body.get("spec")
    if not isinstance(spec, dict):
        raise HTTPException(400, "缺少 spec")
    problems = decomposer.validate_spec(spec)
    if problems:
        raise HTTPException(422, {"problems": problems})
    rules = _load_rules()
    rule = dict(spec)
    rule["id"] = _next_rule_id(rules)
    if body.get("expect_verdict"):
        rule["expect_verdict"] = str(body["expect_verdict"])
    rules.append(rule)
    _save_rules(rules)
    return {"ok": True, "rule": rule}


@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: str) -> Dict[str, Any]:
    rules = _load_rules()
    kept = [r for r in rules if r.get("id") != rule_id]
    if len(kept) == len(rules):
        raise HTTPException(404, f"规则不存在: {rule_id}")
    _save_rules(kept)
    return {"ok": True}


@app.post("/api/rules/decompose")
async def decompose(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "规则文本为空")
    if MOCK or body.get("mock"):
        return decomposer.decompose_rule_mock(text)
    try:
        return await decomposer.decompose_rule(text)
    except SystemExit as exc:
        raise HTTPException(400, str(exc))


# ─────────────────────── Audit run (SSE) ───────────────────────

@app.post("/api/audit/run")
async def audit_run(body: Dict[str, Any] = Body(...)):
    rule_ids: List[str] = body.get("rule_ids") or []
    rules = [r for r in _load_rules() if r.get("id") in set(rule_ids)] \
        if rule_ids else _load_rules()
    if not rules:
        raise HTTPException(400, "没有可执行的规则")
    use_mock = MOCK or bool(body.get("mock"))
    try:
        workspace = resolve_workspace(str(body.get("workspace") or "demo")) \
            if not use_mock else {"kind": "demo", "name": "离线演示工作区"}
    except HTTPException:
        raise

    async def gen():
        async for ev in audit_stream(rules, workspace, mock=use_mock):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield "data: {\"event\": \"eof\"}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ─────────────────────── Entrypoint ───────────────────────

def main() -> None:
    global MOCK
    parser = argparse.ArgumentParser(description="AgenticX Decision console")
    parser.add_argument("--port", type=int, default=8620)
    parser.add_argument("--mock", action="store_true", help="offline demo mode")
    args = parser.parse_args()
    MOCK = args.mock
    print(f"AgenticX Decision console → http://127.0.0.1:{args.port}"
          f"{'  (MOCK)' if MOCK else ''}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
