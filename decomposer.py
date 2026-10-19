#!/usr/bin/env python3
"""Rule decomposer: natural-language rule -> template spec (JSON).

The decomposer LLM (configure a strong model for this stage, e.g. a
DeepSeek flagship) does exactly one thing: map the rule text onto one of
the hand-written, versioned templates — or classify it as semantic /
cross-file when no template fits. It never generates executable code;
the verdict authority stays in the template tools (engine.py).

The mapping output is plain data: auditable, diffable, versionable —
which is exactly what a frozen rule list needs to be.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import mzt_common

# ─────────────────────── Template catalog (single source of truth) ───────────────────────

TEMPLATE_CATALOG = """
可用规则模板（type="rule" 时，template 必须是下列之一）：

1. numeric_range —— 数值/次数/金额是否落在范围内（可加奇偶约束）。
   params: {"keywords": string[]  // 在年报中定位该字段的检索词
            "min": number|null, "max": number|null,
            "parity": "odd"|"even"|null}
   例：成员人数应为3-15且为奇数 -> min=3, max=15, parity="odd"

2. date_deadline —— 日期是否晚于截止日（截止日 = 报告年度 + year_offset 年的 month 月 day 日）。
   params: {"keywords": string[]  // 定位报告日期的检索词
            "year_offset": int, "month": int, "day": int}
   例：应在报告年度次年6月30日前报送 -> year_offset=1, month=6, day=30

3. field_presence —— 关键字段/文号/签章是否存在，缺失按 missing_verdict 判定。
   params: {"keywords": string[], "required_desc": string, "missing_verdict": "存疑"|"不合格"}
   例：现职人员任职须有官方委派文件文号，否则存疑 -> required_desc="委派文件文号", missing_verdict="存疑"

type="semantic"（语义判断，无模板）：params 用 {"keywords": string[], "doubt_condition": string}
   —— 仅当规则核心是主观理解、无法代码判定时使用。

type="cross_file"（跨文件核验）：params 用
   {"claim_keywords": string[],   // 在主年报定位申报值的检索词
    "attachment_keywords": string[],  // 定位证据附件的检索词
    "min_evidence": int}          // 附件实证次数的法定下限
   —— 申报值与附件实证不符或低于下限即不合格，视觉兜底读扫描件。
"""

_OUTPUT_CONTRACT = """输出严格 JSON（不要输出 JSON 以外的任何内容）：
{"name": string,                      // 审核项短名
 "type": "rule"|"semantic"|"cross_file",
 "template": string|null,             // type="rule" 时必填
 "params": object,
 "regulation": string,                // 法规依据；用户未给则写"待补充"
 "expect_verdict": string}            // 用户文本里如果隐含期望结论（合格/不合格/存疑）就填，否则空字符串"""


FEWSHOT = """
示例 1（数值）：
规则："示例成员人数应当在三人到十五人之间，并且人数为奇数"
-> {"name": "示例成员人数范围", "type": "rule", "template": "numeric_range",
    "params": {"keywords": ["成员人数"], "min": 3, "max": 15, "parity": "odd"},
    "regulation": "虚构示例规则", "expect_verdict": ""}

示例 2（日期）：
规则："年报应当在报告年度次年的6月30日之前报送"
-> {"name": "年报按时报送", "type": "rule", "template": "date_deadline",
    "params": {"keywords": ["报告日期"], "year_offset": 1, "month": 6, "day": 30},
    "regulation": "虚构示例规则", "expect_verdict": ""}

示例 3（跨文件）：
规则："理事会每年至少召开2次，年报申报的召开次数必须与会议纪要附件一致"
-> {"name": "理事会召开次数与附件一致", "type": "cross_file", "template": null,
    "params": {"claim_keywords": ["召开理事会"], "attachment_keywords": ["理事会会议纪要"], "min_evidence": 2},
    "regulation": "虚构示例规则", "expect_verdict": ""}
"""

DECOMPOSE_SYSTEM = (
    "你是年报审核规则拆解器。把自然语言审核规则映射为结构化规则 spec。\n"
    + TEMPLATE_CATALOG
    + "\n选择原则：数值/日期/有无类规则必须映射到模板（判定权在代码）；"
      "只有规则核心是主观理解时才用 semantic；一条规则包含多个可判定子条件时，"
      "取最主要的一个条件映射，其余在 name 里注明（用户可拆成多条规则）。\n"
      + _OUTPUT_CONTRACT
    + "\n" + FEWSHOT
)


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """Structural checks on a decomposed spec (no LLM involved)."""
    problems: List[str] = []
    if not isinstance(spec, dict):
        return ["spec 不是 JSON 对象"]
    if not spec.get("name"):
        problems.append("缺少 name")
    stype = spec.get("type")
    if stype not in ("rule", "semantic", "cross_file"):
        problems.append(f"type 非法: {stype}")
        return problems
    params = spec.get("params") or {}
    if not isinstance(params, dict):
        problems.append("params 不是对象")
        return problems
    if stype == "rule":
        tpl = spec.get("template")
        if tpl not in ("numeric_range", "date_deadline", "field_presence"):
            problems.append(f"template 非法: {tpl}")
        elif tpl == "numeric_range":
            if params.get("min") is None and params.get("max") is None:
                problems.append("numeric_range 需要 min/max 至少一个")
            if params.get("parity") not in (None, "odd", "even"):
                problems.append(f"parity 非法: {params.get('parity')}")
        elif tpl == "date_deadline":
            for k in ("year_offset", "month", "day"):
                if params.get(k) is None:
                    problems.append(f"date_deadline 缺少 {k}")
        elif tpl == "field_presence":
            if not params.get("required_desc"):
                problems.append("field_presence 缺少 required_desc")
        if not (params.get("keywords") or []):
            problems.append("缺少 keywords（定位字段用的检索词）")
    elif stype == "semantic":
        if not params.get("doubt_condition"):
            problems.append("semantic 缺少 doubt_condition（何时判存疑）")
        if not (params.get("keywords") or []):
            problems.append("缺少 keywords")
    else:  # cross_file
        if not (params.get("claim_keywords") or []):
            problems.append("cross_file 缺少 claim_keywords")
        if not (params.get("attachment_keywords") or []):
            problems.append("cross_file 缺少 attachment_keywords")
        if params.get("min_evidence") is None:
            problems.append("cross_file 缺少 min_evidence")
    return problems


async def decompose_rule(rule_text: str) -> Dict[str, Any]:
    """Map one natural-language rule to a validated spec (stage: decompose)."""
    from engine import build_provider

    provider = build_provider("decompose")
    resp = await provider.ainvoke([
        {"role": "system", "content": DECOMPOSE_SYSTEM},
        {"role": "user", "content": f"审核规则原文：\n{rule_text}\n\n输出 JSON spec："},
    ])
    raw = resp.content or ""
    try:
        spec = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception:
        return {"ok": False, "raw": raw, "problems": ["拆解输出不是合法 JSON"]}
    problems = validate_spec(spec)
    return {"ok": not problems, "spec": spec, "problems": problems, "raw": raw}


def decompose_rule_mock(rule_text: str) -> Dict[str, Any]:
    """Offline demo mapping (no API): routes a canned numeric example."""
    spec = {
        "name": "示例成员人数范围（演示映射）",
        "type": "rule",
        "template": "numeric_range",
        "params": {"keywords": ["成员人数"], "min": 3, "max": 15, "parity": "odd"},
        "regulation": "虚构示例规则",
        "expect_verdict": "",
    }
    return {"ok": True, "spec": spec, "problems": [],
            "raw": json.dumps(spec, ensure_ascii=False), "mock": True}
