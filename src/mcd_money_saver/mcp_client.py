"""Minimal Streamable HTTP MCP client for https://mcp.mcd.cn.

Auth: Authorization: Bearer ${MCD_MCP_TOKEN}
Never hardcodes tokens. Falls back to discovery helpers used by MoneySaver.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

DEFAULT_MCP_URL = "https://mcp.mcd.cn"

# Official money-saving related tool names (discover live via tools/list).
EXPECTED_TOOLS = (
    "query-my-coupons",
    "query-store-coupons",
    "available-coupons",
    "auto-bind-coupons",
    "query-my-account",
    "mall-points-products",
    "mall-product-detail",
    "query-nearby-stores",
    "delivery-query-stores",
    "query-meals",
    "query-meal-detail",
    "calculate-price",
    "campaign-calendar",
    "now-time-info",
)

# Never call these in the default money-saver advisor flow.
FORBIDDEN_DEFAULT_TOOLS = (
    "create-order",
    "mall-create-order",
    "draw-lottery",
)


@dataclass
class McpTool:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class McpCallResult:
    ok: bool
    data: Any = None
    error: Optional[str] = None
    raw: Any = None


class McdMcpClient:
    """JSON-RPC client over streamable HTTP with Bearer auth."""

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        demo_mode: bool = False,
    ) -> None:
        self.base_url = (base_url or os.environ.get("MCD_MCP_URL") or DEFAULT_MCP_URL).rstrip(
            "/"
        )
        self.token = token if token is not None else os.environ.get("MCD_MCP_TOKEN")
        self.timeout = timeout
        self.demo_mode = demo_mode or not bool(self.token)
        self._request_id = 0
        self._tools_cache: Optional[list[McpTool]] = None
        self._initialized = False

    @classmethod
    def from_env(cls, *, force_demo: bool = False) -> "McdMcpClient":
        token = os.environ.get("MCD_MCP_TOKEN")
        return cls(token=token, demo_mode=force_demo or not bool(token))

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _parse_streamable_body(self, text: str) -> Any:
        """Parse plain JSON or SSE-style `data:` lines from streamable HTTP."""
        text = text.strip()
        if not text:
            return None
        if text.startswith("{") or text.startswith("["):
            return json.loads(text)
        # SSE / streamable: collect data: payloads
        payloads: list[Any] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                payloads.append(json.loads(chunk))
            except json.JSONDecodeError:
                payloads.append(chunk)
        if not payloads:
            # last non-empty attempt
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw_text": text}
        if len(payloads) == 1:
            return payloads[0]
        return payloads

    def _rpc(self, method: str, params: Optional[dict[str, Any]] = None) -> McpCallResult:
        if self.demo_mode:
            return McpCallResult(ok=False, error="demo_mode: live RPC skipped")

        if httpx is None:
            return McpCallResult(
                ok=False,
                error="httpx not installed; run: pip install -r requirements.txt",
            )

        body = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self.base_url,
                    headers=self._headers(),
                    content=json.dumps(body, ensure_ascii=False),
                )
            parsed = self._parse_streamable_body(resp.text)
            if resp.status_code >= 400:
                return McpCallResult(
                    ok=False,
                    error=f"HTTP {resp.status_code}: {resp.text[:400]}",
                    raw=parsed,
                )
            if isinstance(parsed, dict) and parsed.get("error"):
                err = parsed["error"]
                msg = err if isinstance(err, str) else json.dumps(err, ensure_ascii=False)
                return McpCallResult(ok=False, error=msg, raw=parsed)
            result = parsed.get("result") if isinstance(parsed, dict) else parsed
            return McpCallResult(ok=True, data=result, raw=parsed)
        except Exception as exc:  # noqa: BLE001 — surface to caller
            return McpCallResult(ok=False, error=str(exc))

    def initialize(self) -> McpCallResult:
        if self.demo_mode:
            self._initialized = True
            return McpCallResult(ok=True, data={"mode": "demo", "protocolVersion": "demo"})
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcd-money-saver", "version": "0.1.0"},
            },
        )
        if result.ok:
            self._initialized = True
            # Best-effort initialized notification (ignore failures)
            self._rpc("notifications/initialized", {})
        return result

    def list_tools(self, *, refresh: bool = False) -> list[McpTool]:
        if self._tools_cache is not None and not refresh:
            return self._tools_cache

        if self.demo_mode:
            self._tools_cache = [
                McpTool(name=n, description=f"(demo) {n}") for n in EXPECTED_TOOLS
            ]
            return self._tools_cache

        if not self._initialized:
            self.initialize()

        result = self._rpc("tools/list", {})
        tools: list[McpTool] = []
        if result.ok and result.data:
            raw_tools = result.data.get("tools") if isinstance(result.data, dict) else result.data
            if isinstance(raw_tools, list):
                for t in raw_tools:
                    if not isinstance(t, dict):
                        continue
                    tools.append(
                        McpTool(
                            name=str(t.get("name", "")),
                            description=str(t.get("description") or ""),
                            input_schema=t.get("inputSchema") or t.get("input_schema") or {},
                        )
                    )
        self._tools_cache = tools
        return tools

    def has_tool(self, name: str) -> bool:
        names = {t.name for t in self.list_tools()}
        return name in names

    def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> McpCallResult:
        if name in FORBIDDEN_DEFAULT_TOOLS:
            return McpCallResult(
                ok=False,
                error=f"tool '{name}' is forbidden in default money-saver flow",
            )
        if self.demo_mode:
            return McpCallResult(
                ok=False,
                error="demo_mode",
                data={"tool": name, "arguments": arguments or {}},
            )
        if not self._initialized:
            init = self.initialize()
            if not init.ok:
                return init
        return self._rpc(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )

    def safe_call(self, name: str, arguments: Optional[dict[str, Any]] = None) -> McpCallResult:
        """Call only if tools/list exposes the name; otherwise soft-fail."""
        if self.demo_mode:
            return McpCallResult(ok=False, error="demo_mode")
        try:
            available = {t.name for t in self.list_tools()}
        except Exception as exc:  # noqa: BLE001
            return McpCallResult(ok=False, error=f"tools/list failed: {exc}")
        if name not in available:
            return McpCallResult(ok=False, error=f"tool not available: {name}")
        return self.call_tool(name, arguments)


def extract_text_content(data: Any) -> Any:
    """Normalize MCP tools/call content payloads when present."""
    if data is None:
        return None
    if isinstance(data, dict) and "content" in data:
        parts = []
        for item in data.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            else:
                parts.append(item)
        if len(parts) == 1:
            text = parts[0]
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
            return text
        return parts
    return data
