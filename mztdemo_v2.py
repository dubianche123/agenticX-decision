#!/usr/bin/env python3
"""E2: local cross-document audit. Live mode requires PDFs and vision config.

--mock checks only the deterministic comparison, not OCR or model quality.
"""
import argparse
import asyncio
import json

import mzt_common
from engine import check_evidence_count, run_cross_file


async def main(mock: bool) -> None:
    if mock:
        result = {"mock": True, "synthetic": True,
                  **check_evidence_count(claim_count=3, evidence_count=2, min_evidence=2)}
    else:
        root = mzt_common.material_root()
        if not root.is_dir() or not any(root.rglob("*.pdf")):
            raise SystemExit("Set MZT_MATERIAL_ROOT to a local PDF package before a live run.")
        rule = {"id": "sample_cross_file", "name": "示例会议次数与附件核验", "type": "cross_file",
                "regulation": "虚构示例规则", "params": {"claim_keywords": ["会议次数"],
                "attachment_keywords": ["会议纪要"], "min_evidence": 2}}
        result = await run_cross_file(rule, root)
    dest = mzt_common.REPO_ROOT / "results"
    dest.mkdir(exist_ok=True)
    (dest / "demo_v2_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true")
    asyncio.run(main(parser.parse_args().mock))
