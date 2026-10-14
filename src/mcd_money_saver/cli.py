"""CLI for 麦门省钱助手."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from mcd_money_saver import __version__
from mcd_money_saver.mcp_client import EXPECTED_TOOLS, FORBIDDEN_DEFAULT_TOOLS, McdMcpClient
from mcd_money_saver.money_saver import MoneySaver


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcd-money-saver",
        description="麦门省钱助手 — 结合优惠券与积分，通过麦当劳中国 MCP 给出省钱点餐策略（非官方产品）",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command")

    plan = sub.add_parser("plan", help="生成省钱点餐方案")
    plan.add_argument(
        "--items",
        type=str,
        default="",
        help="逗号分隔的想点餐品，如: 巨无霸套餐,薯条",
    )
    plan.add_argument("--budget", type=float, default=None, help="预算上限（元）")
    plan.add_argument("--city", type=str, default=None, help="城市（选店参考）")
    plan.add_argument(
        "--demo",
        action="store_true",
        help="强制演示模式（不调用真实 MCP）",
    )
    plan.add_argument(
        "--bind-coupons",
        action="store_true",
        help="可选：调用 auto-bind-coupons 一键领券后再比价（仍不下单）",
    )
    plan.add_argument(
        "--delivery",
        action="store_true",
        help="外卖场景：优先 delivery-query-stores",
    )
    plan.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="以 JSON 输出报告",
    )

    tools = sub.add_parser("tools", help="列出 MCP tools/list（或演示期望工具）")
    tools.add_argument("--demo", action="store_true")

    coupons = sub.add_parser("coupons", help="查询优惠券相关工具")
    coupons.add_argument("--demo", action="store_true")
    coupons.add_argument("--bind", action="store_true", help="尝试 auto-bind-coupons")

    points = sub.add_parser("points", help="查询积分账户与积分商城（只读）")
    points.add_argument("--demo", action="store_true")

    # bare --help works; also allow no subcommand to show help
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "plan":
        return _cmd_plan(args)
    if args.command == "tools":
        return _cmd_tools(args)
    if args.command == "coupons":
        return _cmd_coupons(args)
    if args.command == "points":
        return _cmd_points(args)
    parser.print_help()
    return 1


def _cmd_plan(args: argparse.Namespace) -> int:
    items = [x.strip() for x in (args.items or "").split(",") if x.strip()]
    client = McdMcpClient.from_env(force_demo=bool(args.demo))
    saver = MoneySaver(client)
    report = saver.plan_order(
        items,
        budget=args.budget,
        city=args.city,
        bind_coupons=bool(args.bind_coupons),
        delivery=bool(args.delivery),
    )
    if args.as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.to_text())
    return 0


def _cmd_tools(args: argparse.Namespace) -> int:
    client = McdMcpClient.from_env(force_demo=bool(args.demo))
    client.initialize()
    tools = client.list_tools()
    print(f"mode={'demo' if client.demo_mode else 'live'} url={client.base_url}")
    print(f"tools ({len(tools)}):")
    for t in tools:
        mark = ""
        if t.name in EXPECTED_TOOLS:
            mark = " [省钱流程]"
        if t.name in FORBIDDEN_DEFAULT_TOOLS:
            mark = " [默认禁止]"
        print(f"  - {t.name}{mark}")
        if t.description:
            print(f"      {t.description[:120]}")
    if client.demo_mode:
        print("\n提示: 设置环境变量 MCD_MCP_TOKEN 后可列出真实 tools/list。")
    return 0


def _cmd_coupons(args: argparse.Namespace) -> int:
    client = McdMcpClient.from_env(force_demo=bool(args.demo))
    saver = MoneySaver(client)
    # Reuse plan with empty items to exercise coupon path in demo; for live, call tools.
    if client.demo_mode:
        report = saver.plan_order(["巨无霸套餐"], bind_coupons=bool(args.bind))
        print("【演示】优惠券候选:")
        for c in report.coupons:
            print(f"  - {c.get('name')} ({c.get('source')})")
        return 0

    client.initialize()
    for name in ("query-my-coupons", "query-store-coupons", "available-coupons"):
        r = client.safe_call(name, {})
        print(f"== {name} ok={r.ok} ==")
        print(json.dumps(r.data if r.ok else {"error": r.error}, ensure_ascii=False, indent=2))
    if args.bind:
        r = client.safe_call("auto-bind-coupons", {})
        print(f"== auto-bind-coupons ok={r.ok} ==")
        print(json.dumps(r.data if r.ok else {"error": r.error}, ensure_ascii=False, indent=2))
    return 0


def _cmd_points(args: argparse.Namespace) -> int:
    client = McdMcpClient.from_env(force_demo=bool(args.demo))
    if client.demo_mode:
        print("【演示】积分账户: 1200")
        print("【演示】积分商城: 800积分兑换「满30减5」券（示例，未兑换）")
        print("默认不会调用 mall-create-order。")
        return 0
    client.initialize()
    for name in ("query-my-account", "mall-points-products"):
        r = client.safe_call(name, {})
        print(f"== {name} ok={r.ok} ==")
        print(json.dumps(r.data if r.ok else {"error": r.error}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
