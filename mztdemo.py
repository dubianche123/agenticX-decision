#!/usr/bin/env python3
"""E1: bounded audit on invented fixtures (--mock), or a local PDF (live).

The mock runs actual AgenticX tool orchestration with scripted model responses.
It does not measure model accuracy, performance, or token costs.
"""
from __future__ import annotations

import argparse
import asyncio
import json

import mzt_common
from engine import build_mock_provider, patch_usage_collection, run_react_item
from sample_data import REPORT_TEXT, RULES, scripts


async def main(mock: bool) -> None:
    text = REPORT_TEXT if mock else mzt_common.pdf_text(mzt_common.default_pdf())
    usage, state, results = [], {"current_item": None}, []
    if not mock:
        patch_usage_collection(usage, state)
    replay = scripts() if mock else {}
    for rule in RULES:
        state["current_item"] = rule["id"]
        provider = build_mock_provider(replay[rule["id"]]) if mock else None
        result = await run_react_item(rule, text, rule["expect_verdict"], provider=provider)
        result["mock"] = mock
        results.append(result)
        print(f"{rule['id']}: {result['agent_verdict']} (blocked={result['blocked']})")
        print(f"  {result['evidence']}")
    dest = mzt_common.REPO_ROOT / "results"
    dest.mkdir(exist_ok=True)
    (dest / "demo_result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (dest / "demo_usage.json").write_text(json.dumps(usage, indent=2), encoding="utf-8")
    if mock and any(r["blocked"] or not r["match_expectation"] for r in results):
        raise SystemExit("Synthetic replay failed")
    print("Synthetic replay only; no measured model usage." if mock else "Local live results saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true")
    asyncio.run(main(parser.parse_args().mock))
