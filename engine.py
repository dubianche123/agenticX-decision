#!/usr/bin/env python3
"""Shared decision-audit engine.

Everything the web console and the experiment scripts agree on lives here:

- Tools:          SearchTextTool (position-anchored keyword retrieval)
- Rule templates: numeric_range / date_deadline / field_presence —
                  deterministic verdict code the model must adopt.
                  (Templates are hand-written and versioned; the LLM only
                  maps a natural-language rule onto template + params.)
- Validation:     fail-closed — missing rule-tool call, missing evidence
                  citation, or non-JSON output blocks the verdict
- Providers:      per-stage config (decompose / main / vision), each
                  stage can override base_url/model/key and inherits the
                  global profile otherwise
- Runner:         audit_stream() — async generator of SSE-ready events;
                  cross-file rules run the three-phase chain (text agent
                  -> vision counting -> code comparison)
- Mock:           scripted offline replay, no API key needed

The three experiment scripts (mztdemo*.py) keep their historical,
self-contained shape for reproducibility; engine.py is the generalized
descendant of the same patterns.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from agenticx.agents import ReActAgent, ToolCallEvent
from agenticx.llms.base import BaseLLMProvider
from agenticx.llms.response import LLMResponse, LLMChoice, TokenUsage
from agenticx.tools.base import BaseTool

import mzt_common


def _lazy_pypdf():
    from pypdf import PdfReader

    return PdfReader


# ─────────────────────────── Retrieve tool ───────────────────────────

class SearchTextTool(BaseTool):
    """Keyword search over a document body; returns hit count and
    context snippets with positions (used as evidence citations)."""

    def __init__(self, text: str) -> None:
        super().__init__(
            name="search_text",
            description="在年报全文中搜索关键词，返回命中次数和带位置的上下文片段。查证据必须先用这个工具。",
        )
        self._text = text

    def _run(self, keyword: str, window: int = 150, max_hits: int = 3) -> str:
        hits: List[str] = []
        start = 0
        while len(hits) < max_hits:
            idx = self._text.find(keyword, start)
            if idx < 0:
                break
            snippet = self._text[max(0, idx - 40) : idx + window].replace("\n", " ")
            hits.append(f"[位置≈{idx}] …{snippet}…")
            start = idx + len(keyword)
        if not hits:
            return json.dumps({"hits": 0, "note": "未找到，请换关键词"}, ensure_ascii=False)
        return json.dumps({"hits": len(hits), "snippets": hits}, ensure_ascii=False)


# ─────────────────────── Rule templates (code verdicts) ───────────────
#
# The LLM maps a natural-language rule onto template + params (see
# decomposer.py). These tools hold the verdict authority; the model must
# adopt the tool's returned verdict.

class NumericRangeTool(BaseTool):
    """数值/次数/金额是否落在范围内（可加奇偶约束）。"""

    def __init__(self, rule: Dict) -> None:
        p = rule.get("params", {})
        self._p = p
        parts = []
        if p.get("min") is not None:
            parts.append(f"≥ {p['min']}")
        if p.get("max") is not None:
            parts.append(f"≤ {p['max']}")
        if p.get("parity") in ("odd", "even"):
            parts.append("为奇数" if p["parity"] == "odd" else "为偶数")
        self._desc_cn = " 且 ".join(parts) if parts else "无约束"
        super().__init__(
            name=f"check_{rule['id']}",
            description=(
                f"确定性规则工具（数值范围）：输入从年报提取的数值，代码判定是否满足"
                f"{self._desc_cn}。结论以此工具返回为准，禁止自行心算。"
            ),
        )

    def _run(self, value: float) -> str:
        v = float(value)
        p = self._p
        ok = True
        if p.get("min") is not None:
            ok = ok and v >= float(p["min"])
        if p.get("max") is not None:
            ok = ok and v <= float(p["max"])
        if p.get("parity") == "odd":
            ok = ok and (int(v) % 2 == 1)
        elif p.get("parity") == "even":
            ok = ok and (int(v) % 2 == 0)
        return json.dumps(
            {"verdict": "合格" if ok else "不合格",
             "rule": f"数值须满足：{self._desc_cn}",
             "input": v, "engine": "template.numeric_range"},
            ensure_ascii=False,
        )


class DateDeadlineTool(BaseTool):
    """日期是否晚于截止日（截止日 = 报告年度 + year_offset 年的 month 月 day 日）。"""

    def __init__(self, rule: Dict) -> None:
        p = rule.get("params", {})
        self._p = p
        self._deadline_cn = (
            f"报告年度 +{p.get('year_offset', 1)} 年的 {p.get('month', 5)} 月 {p.get('day', 31)} 日前"
        )
        super().__init__(
            name=f"check_{rule['id']}",
            description=(
                f"确定性规则工具（日期时限）：输入从年报提取的日期(YYYY-MM-DD)与报告年度，"
                f"代码判定是否在{self._deadline_cn}。结论以此工具返回为准，禁止自行心算。"
            ),
        )

    def _run(self, report_date: str, report_year: int) -> str:
        d = date.fromisoformat(str(report_date).strip())
        p = self._p
        deadline = date(int(report_year) + int(p.get("year_offset", 1)),
                        int(p.get("month", 5)), int(p.get("day", 31)))
        ok = d <= deadline
        return json.dumps(
            {"verdict": "合格" if ok else "不合格",
             "rule": f"日期须不晚于 {deadline.isoformat()}",
             "input": {"report_date": d.isoformat(), "report_year": int(report_year)},
             "engine": "template.date_deadline"},
            ensure_ascii=False,
        )


_MISSING_WORDS = {"", "无", "没有", "暂无", "none", "null", "n/a", "/", "-", "未提供", "未填写"}


class FieldPresenceTool(BaseTool):
    """关键字段/文号/签章是否存在；缺失时按 missing_verdict 判定。"""

    def __init__(self, rule: Dict) -> None:
        p = rule.get("params", {})
        self._missing_verdict = p.get("missing_verdict", "存疑")
        self._required_desc = p.get("required_desc", "必备字段")
        super().__init__(
            name=f"check_{rule['id']}",
            description=(
                f"确定性规则工具（字段存在性）：输入从年报提取的字段值，代码判定"
                f"{self._required_desc}是否存在；缺失则判「{self._missing_verdict}」。"
                "结论以此工具返回为准。"
            ),
        )

    def _run(self, field_value: str) -> str:
        raw = str(field_value).strip()
        missing = raw.lower() in _MISSING_WORDS
        return json.dumps(
            {"verdict": self._missing_verdict if missing else "合格",
             "rule": f"须有{self._required_desc}",
             "input": raw[:60],
             "engine": "template.field_presence"},
            ensure_ascii=False,
        )


_TEMPLATE_TOOLS = {
    "numeric_range": NumericRangeTool,
    "date_deadline": DateDeadlineTool,
    "field_presence": FieldPresenceTool,
}


def build_rule_tool(rule: Dict) -> BaseTool:
    """Instantiate the deterministic tool for a mapped rule spec."""
    tpl = rule.get("template")
    if tpl not in _TEMPLATE_TOOLS:
        raise ValueError(f"unknown template: {tpl}")
    return _TEMPLATE_TOOLS[tpl](rule)


# ─────────────────────── Validation (fail-closed) ───────────────────────

def validate_item(output: str, events: List[Any],
                  require_tool: bool = False, tool_name: str = "") -> Dict:
    """Parse the final output and enforce the fail-closed guarantees."""
    problems = []
    if require_tool:
        called = any(
            isinstance(e, ToolCallEvent) and e.tool_name == tool_name
            for e in events
        )
        if not called:
            problems.append(f"未调用规则工具 {tool_name}，结论拦截")
    parsed = None
    try:
        m = output[output.find("{") : output.rfind("}") + 1]
        parsed = json.loads(m)
        if not parsed.get("evidence"):
            problems.append("结论缺证据引用")
    except Exception:
        problems.append("输出不是合法 JSON")
    return {"blocked": bool(problems), "problems": problems, "parsed": parsed}


# ─────────────────────── Providers (per-stage config) ───────────────────────

def build_provider(stage: str = "main", timeout: int = 120) -> BaseLLMProvider:
    cfg = mzt_common.resolve_stage(stage)
    api_key = cfg["key"]
    if not api_key:
        raise SystemExit(
            "缺少 LLM key。运行一次配置向导即可：\n"
            "  python3 setup_key.py\n"
            "（或在控制台设置页填写；环境变量 MZT_LLM_KEY 亦可）"
        )
    if not cfg["base_url"] or not cfg["model"]:
        raise SystemExit("Configure MZT_LLM_BASE_URL and MZT_LLM_MODEL (or local settings).")
    from agenticx.llms.litellm_provider import LiteLLMProvider
    return LiteLLMProvider(
        model=f"openai/{cfg['model']}",
        api_key=api_key,
        base_url=cfg["base_url"],
        timeout=timeout,
        drop_params=True,
    )


# ─────────────────────── Mock provider (offline replay) ───────────────────────

class MockProvider(BaseLLMProvider):
    model: str = "mock-fc"

    def __init__(self, script: List[Dict]) -> None:
        super().__init__()
        self._script = script
        self._step = 0

    async def ainvoke(self, prompt, tools=None, **kwargs) -> LLMResponse:
        self._step += 1
        step = self._script[self._step - 1] if self._step <= len(self._script) else {"final": "STEP_EXHAUSTED"}
        if "final" in step:
            return LLMResponse(
                id=f"m{self._step}", model_name=self.model, created=0,
                content=step["final"], choices=[LLMChoice(index=0, content=step["final"])],
                token_usage=TokenUsage(),
            )
        return LLMResponse(
            id=f"m{self._step}", model_name=self.model, created=0,
            content="",
            tool_calls=[{
                "id": f"tc{self._step}", "type": "function",
                "function": {"name": step["tool"],
                             "arguments": json.dumps(step["args"], ensure_ascii=False)},
            }],
            choices=[LLMChoice(index=0, content="")],
            token_usage=TokenUsage(),
        )

    def invoke(self, prompt, **kwargs): raise NotImplementedError
    def stream(self, prompt, **kwargs): raise NotImplementedError
    async def astream(self, prompt, **kwargs): raise NotImplementedError


def build_mock_provider(script: List[Dict]) -> BaseLLMProvider:
    """script = [{'tool': name, 'args': {...}} | {'final': text}, ...]"""
    return MockProvider(script)


# ─────────────────────── Usage collection ───────────────────────

def patch_usage_collection(usage_log: List[Dict], state: Dict) -> None:
    """Class-level patch of LiteLLMProvider.ainvoke to record token usage."""
    from agenticx.llms.litellm_provider import LiteLLMProvider

    if getattr(LiteLLMProvider, "_usage_patched", False):
        return
    _orig = LiteLLMProvider.ainvoke

    async def patched(self, prompt, **kw):
        resp = await _orig(self, prompt, **kw)
        u = resp.token_usage
        usage_log.append({
            "item_id": state.get("current_item"),
            "prompt_tokens": u.prompt_tokens if u else 0,
            "completion_tokens": u.completion_tokens if u else 0,
            "cached_tokens": u.cached_tokens if u else 0,
        })
        return resp

    LiteLLMProvider.ainvoke = patched  # type: ignore[method-assign]
    LiteLLMProvider._usage_patched = True  # type: ignore[attr-defined]


def usage_totals(usage_log: List[Dict], item_id: Any) -> Dict[str, int]:
    rows = [u for u in usage_log if u.get("item_id") == item_id]
    return {
        "calls": len(rows),
        "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
        "completion_tokens": sum(r["completion_tokens"] for r in rows),
        "cached_tokens": sum(r["cached_tokens"] for r in rows),
    }


# ─────────────────────── Item runners ───────────────────────

def _rule_system_prompt(rule: Dict) -> str:
    p = rule.get("params", {}) or {}
    kws = p.get("keywords") or rule.get("keywords") or []
    kw_cn = "、".join(kws) if kws else "自选合适关键词"
    return (
        f"你是年报审核项执行器。审核项：{rule.get('name', '')}。法规依据：{rule.get('regulation', '待补充')}。\n"
        f"流程（强制）：1) 用 search_text（关键词可参考：{kw_cn}）在年报中定位相关字段；"
        f"2) 把提取到的值传给工具 check_{rule['id']}；"
        f"3) 最终结论只能采用工具返回的 verdict，禁止不经工具自行得出结论。\n"
        f"最后以 JSON 输出："
        f'{{"item_id":"{rule["id"]}","verdict":"合格|不合格","evidence":"<位置与原文片段>","reason":"<一句话>"}}'
    )


def _semantic_system_prompt(rule: Dict) -> str:
    p = rule.get("params", {}) or {}
    kws = p.get("keywords") or rule.get("keywords") or []
    kw_cn = "、".join(kws) if kws else "自选合适关键词"
    doubt = p.get("doubt_condition", "规则细则待补充")
    return (
        f"你是年报审核项执行器（语义判断类）。审核项：{rule.get('name', '')}。法规依据：{rule.get('regulation', '待补充')}。\n"
        f"判定细则：{doubt}\n"
        f"流程：用 search_text（关键词参考：{kw_cn}）检索相关字段，基于证据输出结论，"
        f"evidence 必须引用检索到的原文。\n"
        f"最后以 JSON 输出："
        f'{{"item_id":"{rule["id"]}","verdict":"合格|不合格|存疑","evidence":"<位置与原文片段>","reason":"<一句话>"}}'
    )


async def run_react_item(rule: Dict, text: str, expect_verdict: str = "",
                         provider: Optional[BaseLLMProvider] = None) -> Dict:
    """One deterministic/semantic rule against one document text."""
    require_tool = rule["type"] == "rule"
    tool = build_rule_tool(rule) if require_tool else None
    provider = provider if provider is not None else build_provider("main")
    tools: List[BaseTool] = [SearchTextTool(text)] + ([tool] if tool else [])
    agent = ReActAgent(
        llm=provider,
        tools=tools,
        system_prompt=_rule_system_prompt(rule) if require_tool else _semantic_system_prompt(rule),
        max_iterations=12,
        model_name=provider.model,
    )
    if require_tool:
        query = (f"审核「{rule['name']}」：先用 search_text 定位字段，"
                 f"再调用 check_{rule['id']}，基于证据按 JSON 输出结论。")
    else:
        query = f"审核「{rule['name']}」：用 search_text 检索相关字段，基于证据按 JSON 输出结论。"
    result = await agent.arun(query)
    check = validate_item(str(result.output), result.events,
                          require_tool=require_tool,
                          tool_name=f"check_{rule['id']}")
    return {
        "item_id": rule["id"],
        "name": rule["name"],
        "type": f"rule:{rule.get('template')}" if require_tool else "semantic",
        "agent_verdict": (check["parsed"] or {}).get("verdict") if check["parsed"] else None,
        "match_expectation": (
            bool(check["parsed"]) and bool(expect_verdict)
            and (check["parsed"] or {}).get("verdict") == expect_verdict
        ) if expect_verdict else None,
        "evidence": (check["parsed"] or {}).get("evidence", "")[:200] if check["parsed"] else "",
        "blocked": check["blocked"],
        "problems": check["problems"],
        "iterations": result.iterations,
    }


# ─────────────────────── Cross-file chain (three phases) ───────────────────────

def check_evidence_count(claim_count: int, evidence_count: int, min_evidence: int) -> Dict[str, Any]:
    ok = evidence_count >= min_evidence and evidence_count == claim_count
    return {
        "verdict": "合格" if ok else "不合格",
        "rule": f"附件实证次数须与申报一致且不低于法定下限（≥ {min_evidence} 次）",
        "input": {"claim_count": claim_count, "evidence_count": evidence_count},
        "engine": "template.cross_file_count_compare",
    }


async def run_cross_file(rule: Dict, org_dir: Path, expect_verdict: str = "",
                         usage_log: Optional[List[Dict]] = None) -> Dict:
    """Claim (text agent) -> vision counting (scanned attachment) -> code rule."""
    import base64

    import pymupdf

    p = rule.get("params", {}) or {}
    claim_keywords = p.get("claim_keywords") or ["召开理事会"]
    attachment_keywords = p.get("attachment_keywords") or ["理事会会议纪要"]
    min_evidence = int(p.get("min_evidence", 2))
    kw_hint = "、".join(claim_keywords)

    # -- Phase A: text agent over the material index --
    file_index = [
        {"path": str(f.relative_to(org_dir)), "size_kb": round(f.stat().st_size / 1024)}
        for f in sorted(org_dir.rglob("*")) if f.is_file() and f.resolve().is_relative_to(org_dir.resolve())
    ]

    class ListFilesTool(BaseTool):
        def __init__(self) -> None:
            super().__init__(
                name="list_files",
                description="列出材料包中的文件（可按关键词过滤）。跨文件核验前必须先用它定位证据文件。",
            )

        def _run(self, pattern: str = "") -> str:
            hits = [f for f in file_index if pattern in f["path"]] if pattern else file_index
            return json.dumps({"total": len(hits), "files": hits[:40]}, ensure_ascii=False)

    class ReadPdfTextTool(BaseTool):
        def __init__(self) -> None:
            super().__init__(
                name="read_pdf_text",
                description="读取 PDF 文本内容（带页码定位）。适用于年报主文件等电子版 PDF；纯扫描件无文本层，返回空时请改走视觉核验流程。",
            )

        def _run(self, path: str, keyword: str = "", window: int = 300, max_chars: int = 4000) -> str:
            try:
                reader = _lazy_pypdf()(str(mzt_common.contained_path(org_dir, path)))
                pages = [f"--- 第{i+1}页 ---\n" + (pg.extract_text() or "")
                         for i, pg in enumerate(reader.pages)]
                text = "\n".join(pages)
            except Exception as exc:
                return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
            if not text.strip():
                return json.dumps({"chars": 0, "note": "该 PDF 无文本层（纯扫描件），需要视觉核验"}, ensure_ascii=False)
            if keyword:
                frags, start = [], 0
                while len(frags) < 5:
                    i = text.find(keyword, start)
                    if i < 0:
                        break
                    page_no = text.rfind("--- 第", 0, i)
                    page_tag = text[page_no:page_no + 10].split("---")[1] if page_no >= 0 else "?"
                    frags.append(f"[第{page_tag}页 位置≈{i}] …{text[max(0,i-60):i+window]}…".replace("\n", " "))
                    start = i + len(keyword)
                body = "\n".join(frags) if frags else f"未找到关键词 {keyword}"
            else:
                body = text[:max_chars]
            return json.dumps({"chars": len(text), "content": body}, ensure_ascii=False)

    system = (
        f"你是年报跨文件审核执行器，材料包共 {len(file_index)} 个文件。\n"
        f"任务：核验「{rule['name']}」。法规依据：{rule.get('regulation', '待补充')}。\n"
        f"流程（强制）：\n"
        f"1) 用 list_files 浏览材料包，找到主年报（文件名含「年报」）；\n"
        f"2) 用 read_pdf_text 读主年报，用 keyword='{kw_hint}' 定位申报的次数；\n"
        f"3) 用 list_files（关键词：{attachment_keywords[0]}）找到相关附件；\n"
        f"4) 若附件无文本层（纯扫描件），直接进入输出——附件计数交给视觉核验流程，不要反复尝试读取；\n"
        f"5) 以 JSON 输出："
        f'{{"claim_count": 申报的次数, "claim_evidence": "申报值出处(页码/原文)", '
        f'"attachment_path": "附件相对路径", "attachment_note": "附件类型说明"}}'
    )
    provider = build_provider("main", timeout=180)
    agent = ReActAgent(
        llm=provider,
        tools=[ListFilesTool(), ReadPdfTextTool()],
        system_prompt=system,
        max_iterations=10,
        model_name=mzt_common.resolve_stage("main")["model"],
    )
    a_result = await agent.arun(f"开始核验「{rule['name']}」：先读主年报找申报值，再定位附件，按 JSON 输出。")
    a_out = str(a_result.output)
    try:
        a = json.loads(a_out[a_out.find("{"): a_out.rfind("}") + 1])
    except Exception:
        a = {"raw": a_out}

    claim = int(a.get("claim_count", 0) or 0)
    attachment = a.get("attachment_path", "")
    if not claim or not attachment:
        return {
            "item_id": rule["id"], "name": rule["name"], "type": "cross_file",
            "agent_verdict": None, "match_expectation": None, "evidence": "",
            "blocked": True,
            "problems": [f"阶段A 未产出申报值/附件定位：{a_out[:150]}"],
            "iterations": a_result.iterations,
        }

    # -- Phase B: vision counting on the scanned attachment --
    doc = pymupdf.open(str(mzt_common.contained_path(org_dir, attachment)))
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=110)
        images.append("data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode())
    doc.close()

    from openai import OpenAI

    vcfg = mzt_common.resolve_stage("vision")
    if not vcfg["key"]:
        raise SystemExit("缺少 LLM key（视觉核验阶段）")
    client = OpenAI(api_key=vcfg["key"], base_url=vcfg["base_url"], timeout=180)
    content: List[Dict[str, Any]] = [{
        "type": "text",
        "text": (
            "这是一份 PDF 的全部页面截图（逐页）。请判断：里面一共包含几份独立的同类文件"
            f"（关键词：{attachment_keywords[0]}）？每份的名称/日期分别是什么？"
            "只依据图片可见内容回答，以 JSON 输出："
            '{"meeting_count": 数字, "meetings": ["<名称(日期)>", ...], "basis": "可见依据一句话"}'
        ),
    }]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": img}})
    v_resp = client.chat.completions.create(
        model=vcfg["model"],
        messages=[{"role": "user", "content": content}],
        max_tokens=600,
    )
    v_raw = v_resp.choices[0].message.content or ""
    v_usage = v_resp.usage
    try:
        vision_output = json.loads(v_raw[v_raw.find("{"): v_raw.rfind("}") + 1])
    except Exception:
        vision_output = {"raw": v_raw}
    if usage_log is not None:
        usage_log.append({
            "item_id": rule["id"],
            "prompt_tokens": v_usage.prompt_tokens,
            "completion_tokens": v_usage.completion_tokens,
            "cached_tokens": 0,
        })

    evidence_count = int(vision_output.get("meeting_count", 0) or 0)

    # -- Phase C: code rule comparison --
    verdict = check_evidence_count(claim, evidence_count, min_evidence)

    return {
        "item_id": rule["id"],
        "name": rule["name"],
        "type": "cross_file",
        "agent_verdict": verdict["verdict"],
        "match_expectation": (verdict["verdict"] == expect_verdict) if expect_verdict else None,
        "evidence": json.dumps({
            "claim": a.get("claim_evidence", ""),
            "attachment": attachment,
            "vision": vision_output,
        }, ensure_ascii=False)[:400],
        "blocked": False,
        "problems": [],
        "iterations": a_result.iterations,
        "claim_count": claim,
        "evidence_count": evidence_count,
        "rule": verdict["rule"],
    }


# ─────────────────────── Workspaces ───────────────────────

def workspace_text(workspace: Dict) -> Optional[str]:
    """Extract the main-report text for a pdf/package workspace."""
    if workspace.get("kind") == "pdf":
        return mzt_common.pdf_text(Path(workspace["path"]))
    if workspace.get("kind") == "package":
        org_dir = Path(workspace["org_dir"])
        candidates = [p for p in sorted(org_dir.rglob("*.pdf")) if "年报" in p.name]
        if not candidates:
            candidates = sorted(org_dir.rglob("*.pdf"))
        if not candidates:
            return None
        return mzt_common.pdf_text(candidates[0])
    return None


# ─────────────────────── Mock demo assets ───────────────────────



def _blocked_result(rule: Dict, problem: str) -> Dict[str, Any]:
    return {
        "item_id": rule["id"], "name": rule.get("name", ""), "type": rule.get("type", ""),
        "agent_verdict": None, "match_expectation": None, "evidence": "",
        "blocked": True, "problems": [problem], "iterations": 0,
    }


# ─────────────────────── Audit stream (SSE-ready) ───────────────────────

async def audit_stream(rules: List[Dict], workspace: Dict,
                       mock: bool = False) -> AsyncGenerator[Dict, None]:
    """Yield events: start -> item_result* -> done. Designed for SSE."""
    usage_log: List[Dict] = []
    state: Dict = {"current_item": None}
    results: List[Dict] = []

    yield {"event": "start", "total": len(rules), "mock": mock,
           "workspace": workspace.get("name", "")}

    if mock:
        from sample_data import REPORT_TEXT, RULES, scripts
        samples = {r["id"]: r for r in RULES}
        replay = scripts()
        for rule in rules:
            sample = samples.get(rule["id"])
            if sample is None or rule != sample:
                result = _blocked_result(rule, "离线模式只支持内置合成规则；自定义规则请配置模型后运行")
            else:
                result = await run_react_item(rule, REPORT_TEXT, rule.get("expect_verdict", ""),
                                              provider=build_mock_provider(replay[rule["id"]]))
            result.update({"demo": True, "synthetic": True, "usage": {"calls": 0, "prompt_tokens": 0,
                           "completion_tokens": 0, "cached_tokens": 0}})
            results.append(result)
            yield {"event": "item_result", **result}
        yield {"event": "done", "summary": _summary(results)}
        return

    if not mock:
        patch_usage_collection(usage_log, state)

    for rule in rules:
        state["current_item"] = rule["id"]
        expect = rule.get("expect_verdict", "")
        try:
            if rule.get("type") == "cross_file":
                if workspace.get("kind") != "package":
                    result = _blocked_result(rule, "跨文件规则需要材料包工作区（含主年报与附件）")
                else:
                    result = await run_cross_file(rule, Path(workspace["org_dir"]),
                                                  expect, usage_log)
            else:
                text = workspace_text(workspace)
                if not text:
                    result = _blocked_result(rule, "主年报 PDF 未找到或无法提取文本")
                else:
                    result = await run_react_item(rule, text, expect)
            result["usage"] = usage_totals(usage_log, rule["id"])
        except SystemExit as exc:
            result = _blocked_result(rule, f"配置缺失：{exc}")
        except Exception as exc:  # noqa: BLE001 — report, never crash the stream
            result = _blocked_result(rule, f"执行异常：{type(exc).__name__}: {exc}")
        results.append(result)
        yield {"event": "item_result", **result}

    yield {"event": "done", "summary": _summary(results)}


def _summary(results: List[Dict]) -> Dict[str, Any]:
    return {
        "items": len(results),
        "verdicts": {
            "合格": sum(1 for r in results if r.get("agent_verdict") == "合格"),
            "不合格": sum(1 for r in results if r.get("agent_verdict") == "不合格"),
            "存疑": sum(1 for r in results if r.get("agent_verdict") == "存疑"),
        },
        "blocked": sum(1 for r in results if r.get("blocked")),
        "calls": sum((r.get("usage") or {}).get("calls", 0) for r in results),
        "prompt_tokens": sum((r.get("usage") or {}).get("prompt_tokens", 0) for r in results),
        "completion_tokens": sum((r.get("usage") or {}).get("completion_tokens", 0) for r in results),
        "cached_tokens": sum((r.get("usage") or {}).get("cached_tokens", 0) for r in results),
    }
