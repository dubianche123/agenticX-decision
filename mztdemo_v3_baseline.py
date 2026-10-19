#!/usr/bin/env python3
"""E3: full-text baseline using the same invented rules as E1.

Live calls send the configured local PDF to a provider; --mock only replays
invented answers. No private benchmark or measured accuracy is included.
"""
import argparse
import asyncio
import json

import mzt_common
from engine import build_mock_provider, build_provider
from sample_data import REPORT_TEXT, RULES, scripts


async def main(mock: bool) -> None:
    text = REPORT_TEXT if mock else mzt_common.pdf_text(mzt_common.default_pdf())
    results, usage = [], []
    replay = scripts() if mock else {}
    for rule in RULES:
        provider = (build_mock_provider([replay[rule["id"]][-1]]) if mock else build_provider("main"))
        prompt = (f"以下为完整文档：\n{text}\n审核项：{rule['name']}\n"
                  f"示例规则：{json.dumps(rule['params'], ensure_ascii=False)}\n"
                  '输出 JSON：{"verdict":"合格|不合格|存疑","evidence":"原文","reason":"理由"}')
        resp = await provider.ainvoke([{"role": "user", "content": prompt}])
        raw = resp.content or ""
        try:
            parsed = json.loads(raw[raw.find("{"):raw.rfind("}")+1])
        except (ValueError, TypeError):
            parsed = {}
        results.append({"item_id": rule["id"], "verdict": parsed.get("verdict"),
                        "match_label": parsed.get("verdict") == rule["expect_verdict"], "raw": raw})
        u = resp.token_usage
        usage.append({"item_id": rule["id"], "prompt_tokens": u.prompt_tokens if u else 0,
                      "completion_tokens": u.completion_tokens if u else 0,
                      "cached_tokens": u.cached_tokens if u else 0})
    dest = mzt_common.REPO_ROOT / "results"
    dest.mkdir(exist_ok=True)
    (dest / "demo_v3_baseline_result.json").write_text(json.dumps(
        {"mock": mock, "baseline": {"results": results, "usage": usage}}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Synthetic replay only; no measured model performance." if mock else "Local baseline saved; compare usage with E1 under identical settings.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true")
    asyncio.run(main(parser.parse_args().mock))
