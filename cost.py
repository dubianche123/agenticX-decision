#!/usr/bin/env python3
"""Recompute token costs with user-supplied rates.

The `example` preset is invented for arithmetic checks, not a provider quote.
Example: python cost.py calc --in 1000 --out 200 --preset example
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# RMB per 1M tokens. cache = cached-input price (prompt cache hit).
PRESETS = {
    "example": {"label": "Synthetic example (not a quote)",
                "in": 1.0, "out": 2.0, "cache": 0.5,
                "source": "Invented arithmetic fixture; supply current rates for real estimates"},
}


def call_cost(prompt_tokens: int, completion_tokens: int, cached_tokens: int,
              p_in: float, p_out: float, p_cache: float) -> float:
    uncached = max(prompt_tokens - cached_tokens, 0)
    return (uncached * p_in + cached_tokens * p_cache
            + completion_tokens * p_out) / 1_000_000


def cmd_presets(_args) -> None:
    print(f"{'preset':<26}{'输入':>8}{'输出':>8}{'缓存命中':>10}   来源")
    for name, p in PRESETS.items():
        print(f"{name:<26}{p['in']:>8}{p['out']:>8}{p['cache']:>10}   {p['source']}")
    print("\n单位：元 / 百万 tokens（人民币；示例单价仅用于算术验证）")


def _resolve_prices(args) -> tuple[float, float, float]:
    if args.preset:
        p = PRESETS[args.preset]
        return p["in"], p["out"], p["cache"]
    if args.price_in is None or args.price_out is None:
        raise SystemExit("需要 --preset 或同时给出 --price-in/--price-out（--price-cache 可选）")
    return args.price_in, args.price_out, (args.price_cache if args.price_cache is not None else args.price_in)


def cmd_calc(args) -> None:
    p_in, p_out, p_cache = _resolve_prices(args)
    cost = call_cost(args.prompt_tokens, args.completion_tokens,
                     args.cached_tokens, p_in, p_out, p_cache)
    cached_note = f"（其中缓存命中 {args.cached_tokens}）" if args.cached_tokens else ""
    print(f"本次调用成本：¥{cost:.4f}")
    print(f"  输入 {args.prompt_tokens} tok{cached_note} · 输出 {args.completion_tokens} tok")
    print(f"  单价：输入 ¥{p_in}/M · 输出 ¥{p_out}/M · 缓存命中 ¥{p_cache}/M")
    if args.calls and args.calls > 1:
        print(f"  × {args.calls} 次同量调用 = ¥{cost * args.calls:.4f}")


def cmd_estimate(args) -> None:
    usage = json.loads(Path(args.usage).read_text(encoding="utf-8"))
    rows = usage if isinstance(usage, list) else usage.get("usage", [])
    per_run_in = sum(r["prompt_tokens"] for r in rows)
    per_run_out = sum(r["completion_tokens"] for r in rows)
    per_run_cached = sum(r.get("cached_tokens", 0) for r in rows)

    baseline = None
    if args.baseline:
        b = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        b_rows = b.get("baseline", {}).get("usage", [])
        baseline = {
            "in": sum(r["prompt_tokens"] for r in b_rows),
            "out": sum(r["completion_tokens"] for r in b_rows),
            "cached": sum(r.get("cached_tokens", 0) for r in b_rows),
        }

    print(f"单次运行（全部审核项）：输入 {per_run_in} tok（缓存命中 {per_run_cached}）· 输出 {per_run_out} tok")
    if baseline:
        ratio = per_run_in / baseline["in"] if baseline["in"] else 0
        print(f"全文直判基线：    输入 {baseline['in']} tok · 输出 {baseline['out']} tok  →  输入量为本方案的 {1/ratio:.1f} 倍" if ratio else "")
    print(f"\n按 {args.reports} 份外推（线性，隐含缓存比例不变）：\n")
    print(f"{'方案':<40}{'成本(元)':>12}")
    if args.preset:
        names = [args.preset]
    else:
        names = list(PRESETS)
    for name in names:
        p = PRESETS[name]
        cost = call_cost(per_run_in * args.reports, per_run_out * args.reports,
                         per_run_cached * args.reports, p["in"], p["out"], p["cache"])
        print(f"{p['label']:<40}{cost:>12,.0f}")
        if baseline:
            b_cost = call_cost(baseline["in"] * args.reports, baseline["out"] * args.reports,
                               baseline["cached"] * args.reports, p["in"], p["out"], p["cache"])
            print(f"{'  ↳ 同价下全文直判基线':<40}{b_cost:>12,.0f}")
    print("\n注：线性外推不含视觉核验、失败重试和基础设施费用。")
    print("    内置价格为虚构示例；实际报价必须替换为当前合同/供应商单价。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("presets", help="列出内置价目（合成示例价）")

    p_calc = sub.add_parser("calc", help="按 token 量与单价算一次调用的钱")
    p_calc.add_argument("--in", dest="prompt_tokens", type=int, required=True)
    p_calc.add_argument("--out", dest="completion_tokens", type=int, required=True)
    p_calc.add_argument("--cached", dest="cached_tokens", type=int, default=0)
    p_calc.add_argument("--calls", type=int, default=1, help="同量调用次数（×N 展示）")
    p_calc.add_argument("--preset", choices=sorted(PRESETS))
    p_calc.add_argument("--price-in", type=float)
    p_calc.add_argument("--price-out", type=float)
    p_calc.add_argument("--price-cache", type=float)

    p_est = sub.add_parser("estimate", help="从运行日志外推整仓成本并对比基线")
    p_est.add_argument("--reports", type=int, default=100)
    p_est.add_argument("--usage", default="results/demo_usage.json",
                       help="E1 用量日志（本方案）")
    p_est.add_argument("--baseline", default="",
                       help="E3 基线结果（全文直判）；传空字符串跳过")
    p_est.add_argument("--preset", choices=sorted(PRESETS))

    args = parser.parse_args()
    if args.cmd == "presets":
        cmd_presets(args)
    elif args.cmd == "calc":
        cmd_calc(args)
    elif args.cmd == "estimate":
        if args.baseline == "":
            args.baseline = None
        cmd_estimate(args)


if __name__ == "__main__":
    main()
