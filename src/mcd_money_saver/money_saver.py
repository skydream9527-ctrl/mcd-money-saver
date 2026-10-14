"""Core money-saving workflow: coupons + points + menu + calculate-price."""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from mcd_money_saver.mcp_client import (
    EXPECTED_TOOLS,
    FORBIDDEN_DEFAULT_TOOLS,
    McdMcpClient,
    extract_text_content,
)


@dataclass
class Strategy:
    name: str
    payable: float
    coupons_used: list[str] = field(default_factory=list)
    savings: float = 0.0
    notes: str = ""
    source: str = "demo"


@dataclass
class PlanReport:
    mode: str  # "live" | "demo"
    items: list[str]
    budget: Optional[float]
    city: Optional[str]
    store: Optional[dict[str, Any]]
    coupons: list[dict[str, Any]]
    points: Optional[dict[str, Any]]
    mall_hints: list[dict[str, Any]]
    strategies: list[Strategy]
    best: Optional[Strategy]
    timeline: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_snippets: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "items": self.items,
            "budget": self.budget,
            "city": self.city,
            "store": self.store,
            "coupons": self.coupons,
            "points": self.points,
            "mall_hints": self.mall_hints,
            "strategies": [
                {
                    "name": s.name,
                    "payable": s.payable,
                    "coupons_used": s.coupons_used,
                    "savings": s.savings,
                    "notes": s.notes,
                    "source": s.source,
                }
                for s in self.strategies
            ],
            "best": None
            if self.best is None
            else {
                "name": self.best.name,
                "payable": self.best.payable,
                "coupons_used": self.best.coupons_used,
                "savings": self.best.savings,
            },
            "timeline": self.timeline,
            "warnings": self.warnings,
        }

    def to_text(self) -> str:
        lines: list[str] = []
        tag = "【演示示例】" if self.mode == "demo" else "【实时 MCP】"
        lines.append(f"=== 麦门省钱助手报告 {tag} ===")
        lines.append(f"目标餐品: {', '.join(self.items) or '（未指定）'}")
        if self.budget is not None:
            lines.append(f"预算上限: ¥{self.budget:.2f}")
        if self.city:
            lines.append(f"城市: {self.city}")
        if self.store:
            lines.append(f"门店: {self.store.get('name') or self.store}")
        lines.append("")
        lines.append(f"可用优惠券候选: {len(self.coupons)} 张")
        for c in self.coupons[:8]:
            lines.append(f"  - {c.get('name') or c.get('title') or c}")
        if self.points:
            bal = self.points.get("points") or self.points.get("balance") or self.points
            lines.append(f"积分账户: {bal}")
        if self.mall_hints:
            lines.append("积分商城换券提示（未自动兑换）:")
            for h in self.mall_hints[:5]:
                lines.append(f"  - {h.get('name') or h}")
        lines.append("")
        lines.append("比价策略:")
        for s in self.strategies:
            used = ", ".join(s.coupons_used) if s.coupons_used else "无券"
            lines.append(
                f"  · {s.name}: 应付 ¥{s.payable:.2f} | 节省 ¥{s.savings:.2f} | 券: {used}"
            )
            if s.notes:
                lines.append(f"      备注: {s.notes}")
        if self.best:
            lines.append("")
            lines.append(
                f"★ 推荐: {self.best.name} → 约 ¥{self.best.payable:.2f}"
                f"（节省约 ¥{self.best.savings:.2f}）"
            )
            if self.budget is not None and self.best.payable > self.budget:
                lines.append(f"⚠ 仍高于预算 ¥{self.budget:.2f}，可考虑减配或换活动套餐。")
            elif self.budget is not None:
                lines.append(f"✓ 在预算 ¥{self.budget:.2f} 内。")
        if self.timeline:
            lines.append("")
            lines.append("执行步骤:")
            for step in self.timeline:
                lines.append(f"  {step}")
        if self.warnings:
            lines.append("")
            lines.append("提示:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        lines.append("")
        lines.append(
            "声明: 非麦当劳官方产品；价格/券/供应以官方 App·小程序实时结果为准。"
            "默认不下单（不调用 create-order / mall-create-order / draw-lottery）。"
        )
        return "\n".join(lines)


# --- Demo fixtures (explicitly labeled) ---

_DEMO_COUPONS = [
    {
        "id": "demo-c1",
        "name": "示例券-巨无霸套餐减10",
        "amount": 10,
        "scope": "巨无霸套餐",
        "source": "demo",
    },
    {
        "id": "demo-c2",
        "name": "示例券-满40减6",
        "amount": 6,
        "min_spend": 40,
        "scope": "整单",
        "source": "demo",
    },
    {
        "id": "demo-c3",
        "name": "示例券-麦辣鸡腿堡套餐买一送一券(示意折半)",
        "amount": 18,
        "scope": "麦辣鸡腿堡套餐",
        "source": "demo",
    },
]

_DEMO_MEAL_PRICES = {
    "巨无霸套餐": 38.0,
    "麦辣鸡腿堡套餐": 36.0,
    "薯条": 12.0,
    "薯条(中)": 12.0,
    "可乐": 10.0,
    "麦乐鸡": 14.0,
}


def _estimate_item_price(name: str) -> float:
    for k, v in _DEMO_MEAL_PRICES.items():
        if k in name or name in k:
            return v
    return 28.0  # generic demo unit price


class MoneySaver:
    """Orchestrates MCP tools for a read-only save-money plan."""

    def __init__(self, client: Optional[McdMcpClient] = None, *, demo: bool = False) -> None:
        if client is None:
            client = McdMcpClient.from_env(force_demo=demo)
        elif demo:
            client.demo_mode = True
        self.client = client

    def plan_order(
        self,
        items: list[str],
        *,
        budget: Optional[float] = None,
        city: Optional[str] = None,
        bind_coupons: bool = False,
        delivery: bool = False,
    ) -> PlanReport:
        mode = "demo" if self.client.demo_mode else "live"
        timeline: list[str] = []
        warnings: list[str] = [
            "本助手为只读省钱顾问，不会调用 create-order / mall-create-order / draw-lottery。"
        ]
        raw: dict[str, Any] = {}

        if mode == "demo":
            warnings.append(
                "未检测到 MCD_MCP_TOKEN 或已指定 --demo：以下为标注示例数据，非实时报价。"
            )
            return self._demo_plan(items, budget=budget, city=city, warnings=warnings)

        # Live path
        timeline.append("1. initialize + tools/list")
        init = self.client.initialize()
        if not init.ok:
            warnings.append(f"MCP initialize 失败，回退演示: {init.error}")
            return self._demo_plan(items, budget=budget, city=city, warnings=warnings)

        tools = self.client.list_tools()
        tool_names = {t.name for t in tools}
        missing = [n for n in EXPECTED_TOOLS if n not in tool_names]
        if missing:
            warnings.append(
                "以下期望工具当前未出现在 tools/list（将跳过）: " + ", ".join(missing)
            )
        present_forbidden = [n for n in FORBIDDEN_DEFAULT_TOOLS if n in tool_names]
        if present_forbidden:
            warnings.append(
                "服务端存在下单/抽奖工具，但本 Skill 默认不会调用: "
                + ", ".join(present_forbidden)
            )

        # Time + campaign
        timeline.append("2. now-time-info / campaign-calendar")
        if self.client.has_tool("now-time-info"):
            r = self.client.safe_call("now-time-info")
            raw["now-time-info"] = extract_text_content(r.data) if r.ok else r.error
        if self.client.has_tool("campaign-calendar"):
            r = self.client.safe_call("campaign-calendar")
            raw["campaign-calendar"] = extract_text_content(r.data) if r.ok else r.error

        # Store
        timeline.append("3. 选门店")
        store: Optional[dict[str, Any]] = None
        store_tool = "delivery-query-stores" if delivery else "query-nearby-stores"
        if self.client.has_tool(store_tool):
            args: dict[str, Any] = {}
            if city:
                args["city"] = city
            r = self.client.safe_call(store_tool, args)
            raw[store_tool] = extract_text_content(r.data) if r.ok else r.error
            store = self._pick_first_store(raw.get(store_tool))
        elif self.client.has_tool("query-nearby-stores"):
            r = self.client.safe_call("query-nearby-stores", {"city": city} if city else {})
            raw["query-nearby-stores"] = extract_text_content(r.data) if r.ok else r.error
            store = self._pick_first_store(raw.get("query-nearby-stores"))

        # Meals
        timeline.append("4. query-meals / query-meal-detail")
        meal_hits: list[Any] = []
        for item in items:
            if self.client.has_tool("query-meals"):
                r = self.client.safe_call("query-meals", {"keyword": item})
                payload = extract_text_content(r.data) if r.ok else None
                raw.setdefault("query-meals", {})[item] = payload or r.error
                meal_hits.append({"item": item, "result": payload})
            if self.client.has_tool("query-meal-detail"):
                r = self.client.safe_call("query-meal-detail", {"name": item})
                raw.setdefault("query-meal-detail", {})[item] = (
                    extract_text_content(r.data) if r.ok else r.error
                )

        # Coupons
        timeline.append("5. 券池：我的券 / 门店券 / 可领券")
        coupons: list[dict[str, Any]] = []
        for tool in ("query-my-coupons", "query-store-coupons", "available-coupons"):
            if not self.client.has_tool(tool):
                continue
            args = {}
            if store and tool == "query-store-coupons":
                args["storeId"] = store.get("id") or store.get("storeId")
            r = self.client.safe_call(tool, args)
            payload = extract_text_content(r.data) if r.ok else None
            raw[tool] = payload if r.ok else r.error
            coupons.extend(self._normalize_coupons(payload, source=tool))

        if bind_coupons and self.client.has_tool("auto-bind-coupons"):
            timeline.append("5b. auto-bind-coupons（可选一键领券）")
            r = self.client.safe_call("auto-bind-coupons", {})
            raw["auto-bind-coupons"] = extract_text_content(r.data) if r.ok else r.error
            # refresh my coupons
            if self.client.has_tool("query-my-coupons"):
                r2 = self.client.safe_call("query-my-coupons", {})
                payload = extract_text_content(r2.data) if r2.ok else None
                raw["query-my-coupons_after_bind"] = payload if r2.ok else r2.error
                coupons.extend(self._normalize_coupons(payload, source="query-my-coupons"))

        # Points + mall (query only)
        timeline.append("6. query-my-account + 积分商城查询")
        points: Optional[dict[str, Any]] = None
        mall_hints: list[dict[str, Any]] = []
        if self.client.has_tool("query-my-account"):
            r = self.client.safe_call("query-my-account", {})
            payload = extract_text_content(r.data) if r.ok else None
            raw["query-my-account"] = payload if r.ok else r.error
            if isinstance(payload, dict):
                points = payload
            elif payload is not None:
                points = {"raw": payload}
        if self.client.has_tool("mall-points-products"):
            r = self.client.safe_call("mall-points-products", {})
            payload = extract_text_content(r.data) if r.ok else None
            raw["mall-points-products"] = payload if r.ok else r.error
            mall_hints = self._normalize_mall(payload)
            # Optional detail for first few coupon-like products
            if self.client.has_tool("mall-product-detail"):
                for hint in mall_hints[:3]:
                    pid = hint.get("id") or hint.get("productId")
                    if not pid:
                        continue
                    rd = self.client.safe_call("mall-product-detail", {"productId": pid})
                    hint["detail"] = extract_text_content(rd.data) if rd.ok else rd.error

        # calculate-price strategies
        timeline.append("7. calculate-price 多组合比价")
        strategies: list[Strategy] = []
        base_products = self._products_payload(items, meal_hits)
        coupon_candidates = coupons[:6]  # limit combinations

        if self.client.has_tool("calculate-price"):
            # no coupon
            strategies.append(
                self._price_via_mcp(base_products, [], label="原价（无券）", raw_bucket=raw)
            )
            # single coupons
            for c in coupon_candidates:
                strategies.append(
                    self._price_via_mcp(
                        base_products,
                        [c],
                        label=f"使用「{c.get('name', c.get('id', '券'))}」",
                        raw_bucket=raw,
                    )
                )
            # pairs
            for a, b in itertools.combinations(coupon_candidates, 2):
                strategies.append(
                    self._price_via_mcp(
                        base_products,
                        [a, b],
                        label=f"组合「{a.get('name', '?')}+{b.get('name', '?')}」",
                        raw_bucket=raw,
                    )
                )
        else:
            warnings.append("calculate-price 不可用，使用本地估算回退。")
            strategies = self._local_estimate_strategies(items, coupon_candidates)

        # Drop failed (payable < 0 sentinel) and sort
        strategies = [s for s in strategies if s.payable >= 0]
        if not strategies:
            strategies = self._local_estimate_strategies(items, coupon_candidates)
            warnings.append("算价未返回有效结果，已用本地估算。")

        base = min((s.payable for s in strategies if not s.coupons_used), default=None)
        if base is None and strategies:
            base = max(s.payable for s in strategies)
        for s in strategies:
            if base is not None:
                s.savings = round(max(0.0, base - s.payable), 2)
        strategies.sort(key=lambda s: s.payable)
        best = strategies[0] if strategies else None

        # Deduplicate coupons by id/name
        uniq: dict[str, dict[str, Any]] = {}
        for c in coupons:
            key = str(c.get("id") or c.get("name") or json.dumps(c, ensure_ascii=False))
            uniq[key] = c

        return PlanReport(
            mode="live",
            items=items,
            budget=budget,
            city=city,
            store=store,
            coupons=list(uniq.values()),
            points=points,
            mall_hints=mall_hints,
            strategies=strategies,
            best=best,
            timeline=timeline,
            warnings=warnings,
            raw_snippets={k: v for k, v in raw.items() if v is not None},
        )

    def _price_via_mcp(
        self,
        products: list[dict[str, Any]],
        coupons: list[dict[str, Any]],
        *,
        label: str,
        raw_bucket: dict[str, Any],
    ) -> Strategy:
        coupon_ids = []
        names = []
        for c in coupons:
            cid = c.get("id") or c.get("couponId") or c.get("code")
            if cid:
                coupon_ids.append(cid)
            names.append(str(c.get("name") or cid or "券"))
        args = {"products": products, "coupons": coupon_ids}
        # Also try common alternate shapes
        r = self.client.safe_call("calculate-price", args)
        if not r.ok:
            # alternate argument keys
            r = self.client.safe_call(
                "calculate-price",
                {
                    "items": products,
                    "couponIds": coupon_ids,
                    "couponList": coupons,
                },
            )
        key = f"calculate-price:{label}"
        payload = extract_text_content(r.data) if r.ok else None
        raw_bucket[key] = payload if r.ok else r.error
        payable = self._extract_payable(payload)
        if payable is None:
            return Strategy(
                name=label,
                payable=-1.0,
                coupons_used=names,
                notes=f"算价失败: {r.error or '无金额字段'}",
                source="live",
            )
        return Strategy(
            name=label,
            payable=float(payable),
            coupons_used=names,
            source="live",
        )

    def _demo_plan(
        self,
        items: list[str],
        *,
        budget: Optional[float],
        city: Optional[str],
        warnings: list[str],
    ) -> PlanReport:
        if not items:
            items = ["巨无霸套餐", "薯条(中)"]
        coupons = list(_DEMO_COUPONS)
        strategies = self._local_estimate_strategies(items, coupons)
        base = next((s.payable for s in strategies if not s.coupons_used), strategies[0].payable)
        for s in strategies:
            s.savings = round(max(0.0, base - s.payable), 2)
            s.source = "demo"
        strategies.sort(key=lambda s: s.payable)
        return PlanReport(
            mode="demo",
            items=items,
            budget=budget,
            city=city,
            store={"name": "示例门店-人民广场餐厅", "id": "demo-store-1"},
            coupons=coupons,
            points={"points": 1200, "note": "示例积分余额"},
            mall_hints=[
                {
                    "name": "示例：800积分兑换「满30减5」券",
                    "pointsCost": 800,
                    "id": "demo-mall-1",
                }
            ],
            strategies=strategies,
            best=strategies[0] if strategies else None,
            timeline=[
                "1. (demo) now-time-info / campaign-calendar",
                "2. (demo) query-nearby-stores",
                "3. (demo) query-meals",
                "4. (demo) query-my-coupons + available-coupons",
                "5. (demo) query-my-account + mall-points-products",
                "6. (demo) calculate-price 组合比价",
            ],
            warnings=warnings,
        )

    def _local_estimate_strategies(
        self, items: list[str], coupons: list[dict[str, Any]]
    ) -> list[Strategy]:
        subtotal = sum(_estimate_item_price(i) for i in items)
        strategies = [
            Strategy(name="原价（无券）", payable=round(subtotal, 2), coupons_used=[], source="estimate")
        ]
        joined = " ".join(items)
        for c in coupons:
            amount = float(c.get("amount") or 0)
            scope = str(c.get("scope") or "")
            min_spend = float(c.get("min_spend") or 0)
            applicable = True
            if scope and scope not in ("整单",) and scope not in joined:
                # still allow demo discount partially
                if not any(scope in i or i in scope for i in items):
                    applicable = False
            if min_spend and subtotal < min_spend:
                applicable = False
            if not applicable or amount <= 0:
                continue
            payable = round(max(0.0, subtotal - amount), 2)
            strategies.append(
                Strategy(
                    name=f"使用「{c.get('name', '券')}」",
                    payable=payable,
                    coupons_used=[str(c.get("name"))],
                    notes="本地估算（示例或 calculate-price 回退）",
                    source="estimate",
                )
            )
        return strategies

    @staticmethod
    def _pick_first_store(payload: Any) -> Optional[dict[str, Any]]:
        if payload is None:
            return None
        if isinstance(payload, dict):
            for key in ("stores", "list", "data", "items"):
                if isinstance(payload.get(key), list) and payload[key]:
                    first = payload[key][0]
                    return first if isinstance(first, dict) else {"name": str(first)}
            if "name" in payload or "storeId" in payload or "id" in payload:
                return payload
        if isinstance(payload, list) and payload:
            first = payload[0]
            return first if isinstance(first, dict) else {"name": str(first)}
        return None

    @staticmethod
    def _normalize_coupons(payload: Any, *, source: str) -> list[dict[str, Any]]:
        rows: list[Any]
        if payload is None:
            return []
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = None
            for key in ("coupons", "list", "data", "items", "availableCoupons"):
                if isinstance(payload.get(key), list):
                    rows = payload[key]
                    break
            if rows is None:
                rows = [payload]
        else:
            return [{"name": str(payload), "source": source}]

        out: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                item = dict(row)
                item.setdefault("source", source)
                if "name" not in item:
                    item["name"] = (
                        item.get("title")
                        or item.get("couponName")
                        or item.get("id")
                        or "未命名券"
                    )
                out.append(item)
            else:
                out.append({"name": str(row), "source": source})
        return out

    @staticmethod
    def _normalize_mall(payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        rows: list[Any]
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = []
            for key in ("products", "list", "data", "items"):
                if isinstance(payload.get(key), list):
                    rows = payload[key]
                    break
            if not rows:
                rows = [payload]
        else:
            return [{"name": str(payload)}]
        out = []
        for row in rows:
            if isinstance(row, dict):
                out.append(row)
            else:
                out.append({"name": str(row)})
        return out

    @staticmethod
    def _products_payload(items: list[str], meal_hits: list[Any]) -> list[dict[str, Any]]:
        products = []
        for i, name in enumerate(items):
            products.append({"name": name, "quantity": 1, "index": i})
        # Attach first hit ids if any
        for hit in meal_hits:
            result = hit.get("result")
            if isinstance(result, dict):
                for key in ("id", "mealId", "productId", "skuId"):
                    if key in result:
                        products[0].setdefault(key, result[key])
                        break
            elif isinstance(result, list) and result and isinstance(result[0], dict):
                first = result[0]
                for key in ("id", "mealId", "productId", "skuId"):
                    if key in first:
                        # match by item name
                        for p in products:
                            if p["name"] == hit.get("item"):
                                p.setdefault(key, first[key])
        return products

    @staticmethod
    def _extract_payable(payload: Any) -> Optional[float]:
        if payload is None:
            return None
        if isinstance(payload, (int, float)):
            return float(payload)
        if isinstance(payload, str):
            try:
                return float(payload.replace("¥", "").strip())
            except ValueError:
                return None
        if isinstance(payload, dict):
            for key in (
                "payable",
                "payPrice",
                "pay_price",
                "totalPrice",
                "total",
                "price",
                "amount",
                "finalPrice",
            ):
                if key in payload and payload[key] is not None:
                    try:
                        return float(payload[key])
                    except (TypeError, ValueError):
                        continue
            # nested data
            for nest in ("data", "result", "priceInfo"):
                if isinstance(payload.get(nest), dict):
                    got = MoneySaver._extract_payable(payload[nest])
                    if got is not None:
                        return got
        return None
