"""Entirely invented public fixtures. These are not regulatory guidance."""
import json

REPORT_TEXT = """SYNTHETIC EXAMPLE — fictitious project, no customer source.
报告年度：2030
报告日期：2031-04-12
成员人数：31
审批状态：待复核
审批依据：未提供
会议次数：3
"""

RULES = [
    {"id": "sample_number", "name": "示例成员人数范围", "type": "rule",
     "template": "numeric_range", "params": {"keywords": ["成员人数"], "min": 3, "max": 15, "parity": "odd"},
     "regulation": "虚构示例规则：3至15人且为奇数", "expect_verdict": "不合格"},
    {"id": "sample_date", "name": "示例报送日期", "type": "rule",
     "template": "date_deadline", "params": {"keywords": ["报告日期"], "year_offset": 1, "month": 6, "day": 30},
     "regulation": "虚构示例规则：报告年度次年6月30日前", "expect_verdict": "合格"},
    {"id": "sample_review", "name": "示例审批状态复核", "type": "semantic", "template": None,
     "params": {"keywords": ["审批状态"], "doubt_condition": "审批待复核且未提供依据时，判为存疑"},
     "regulation": "虚构示例流程", "expect_verdict": "存疑"},
]


def scripts():
    """Scripted model responses; real search and rule tools still execute."""
    cases = [
        ("成员人数", {"value": 31}, "成员人数：31", "不合格", "31超过示例上限15"),
        ("报告日期", {"report_date": "2031-04-12", "report_year": 2030}, "报告日期：2031-04-12", "合格", "早于示例截止日2031-06-30"),
        ("审批状态", None, "审批状态：待复核\n审批依据：未提供", "存疑", "需要人工复核并补充依据"),
    ]
    result = {}
    for rule, (keyword, args, quote, verdict, reason) in zip(RULES, cases):
        steps = [{"tool": "search_text", "args": {"keyword": keyword}}]
        if args is not None:
            steps.append({"tool": "check_" + rule["id"], "args": args})
        evidence = f"[位置≈{REPORT_TEXT.index(keyword)}] {quote}"
        steps.append({"final": json.dumps({"item_id": rule["id"], "verdict": verdict,
                                         "evidence": evidence, "reason": reason}, ensure_ascii=False)})
        result[rule["id"]] = steps
    return result
