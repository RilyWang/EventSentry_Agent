"""
iFinD MCP 客户端 — 真实调用同花顺金融数据服务
数据来源：https://api-mcp.51ifind.com（iFinD / 同花顺 MCP）
"""
import os
# 绕过系统 SOCKS 代理（该代理不支持 MCP 端点直连）
os.environ.setdefault("no_proxy", "*")
os.environ.setdefault("NO_PROXY", "*")

import json
import math
import warnings
from pathlib import Path

import requests

warnings.filterwarnings("ignore")

MCP_CONFIG_PATH = Path(r"C:\Users\DELL\.zcode\skills\ifind-finance-data\mcp_config.json")

BASE = "https://api-mcp.51ifind.com:8643/ds-mcp-servers"
SERVERS = {
    "stock": f"{BASE}/hexin-ifind-ds-stock-mcp",
    "fund": f"{BASE}/hexin-ifind-ds-fund-mcp",
    "edb": f"{BASE}/hexin-ifind-ds-edb-mcp",
    "news": f"{BASE}/hexin-ifind-ds-news-mcp",
    "bond": f"{BASE}/hexin-ifind-ds-bond-mcp",
    "global_stock": f"{BASE}/hexin-ifind-ds-global-stock-mcp",
    "index": f"{BASE}/hexin-ifind-ds-index-mcp",
    "future": f"{BASE}/hexin-ifind-ds-futures-mcp",
}

BLOCKED_KEYS = {"__proto__", "prototype", "constructor"}


class IfindError(Exception):
    pass


class IfindClient:
    """iFinD MCP 客户端（带会话管理 + 代理绕过）"""

    def __init__(self, token: str = None):
        if token is None:
            if not MCP_CONFIG_PATH.exists():
                raise IfindError(f"iFinD 密钥配置不存在: {MCP_CONFIG_PATH}")
            token = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))["auth_token"]
        self.token = token
        self._sessions = {}
        self._req_ids = {}
        self._tool_sets = {}

    # ─── 内部 ───
    def _next_id(self, t):
        self._req_ids[t] = self._req_ids.get(t, 0) + 1
        return self._req_ids[t]

    def _headers(self, t=None):
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": self.token,
        }
        if t in self._sessions:
            h["Mcp-Session-Id"] = self._sessions[t]
        return h

    def _post(self, t, payload, timeout=60):
        resp = requests.post(
            SERVERS[t], json=payload, headers=self._headers(t),
            verify=False, timeout=timeout, proxies={"http": None, "https": None},
        )
        data = None
        if resp.text.strip():
            try:
                data = resp.json()
            except Exception:
                data = resp.text
        return resp, data

    def _init(self, t):
        if t in self._sessions:
            return
        payload = {
            "jsonrpc": "2.0", "id": self._next_id(t), "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "eventsentry-agent", "version": "2.0.0"},
            },
        }
        resp, data = self._post(t, payload, timeout=30)
        resp.raise_for_status()
        sid = resp.headers.get("Mcp-Session-Id")
        if not sid:
            raise IfindError(f"initialize 未返回 Mcp-Session-Id: {data}")
        self._sessions[t] = sid
        self._post(t, {"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=10)

    def _validate(self, params):
        if not isinstance(params, dict):
            raise TypeError("params must be dict")

        def walk(v):
            if v is None:
                return
            if isinstance(v, list):
                for i in v:
                    walk(i)
                return
            if isinstance(v, dict):
                for k, i in v.items():
                    if k in BLOCKED_KEYS:
                        raise TypeError("blocked field")
                    walk(i)
                return
            if isinstance(v, float) and not math.isfinite(v):
                raise TypeError("invalid number")
            if not isinstance(v, (str, int, float, bool)):
                raise TypeError("unsupported type")
        walk(params)
        json.dumps(params, allow_nan=False)

    def _tool_set(self, server_type):
        if server_type in self._tool_sets:
            return self._tool_sets[server_type]
        tools = self.list_tools(server_type)
        s = {t.get("name") for t in tools if isinstance(t, dict) and t.get("name")}
        self._tool_sets[server_type] = s
        return s

    # ─── 公开 API ───
    def list_tools(self, server_type):
        if server_type not in SERVERS:
            raise IfindError(f"unknown server_type: {server_type}")
        self._init(server_type)
        payload = {"jsonrpc": "2.0", "id": self._next_id(server_type), "method": "tools/list", "params": {}}
        resp, data = self._post(server_type, payload)
        if isinstance(data, dict) and "error" in data:
            raise IfindError(f"tools/list error: {data['error']}")
        resp.raise_for_status()
        return data.get("result", {}).get("tools", [])

    def call(self, server_type, tool_name, params):
        """调用 iFinD MCP 工具，返回解析后的 Python 对象"""
        if server_type not in SERVERS:
            raise IfindError(f"unknown server_type: {server_type}")
        self._validate(params)

        allowed = self._tool_set(server_type)
        if tool_name not in allowed:
            raise IfindError(f"工具不可用: {server_type}/{tool_name}（可用: {sorted(allowed)}）")

        self._init(server_type)
        payload = {
            "jsonrpc": "2.0", "id": self._next_id(server_type), "method": "tools/call",
            "params": {"name": tool_name, "arguments": params},
        }
        resp, data = self._post(server_type, payload)
        if isinstance(data, dict) and "error" in data:
            raise IfindError(f"{tool_name} error: {data['error']}")
        resp.raise_for_status()

        # 解析 MCP 返回的 text 内容
        try:
            content = data["result"]["content"]
            texts = [c["text"] for c in content if c.get("type") == "text"]
            raw = texts[0] if texts else ""
            parsed = json.loads(raw)
            return parsed
        except Exception as e:
            return {"_raw": data, "_parse_error": str(e)}


# ─── 便捷函数：把 iFinD 返回的 data 字段解析成结构化记录 ───
def parse_ifind_records(result):
    """
    iFinD 各服务的返回格式不同，需兼容三种：
      1) 新闻/公告服务：{code, msg, data: "[{...}]"}   —— data 是 JSON 字符串
      2) 股票/行情服务：{code, msg, data: {"answer": "markdown表格", "indicators_params": {...}}}
      3) 极少数情况 data 直接是 list
    """
    if not isinstance(result, dict):
        return []
    raw = result.get("data")
    if raw is None:
        return []

    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
            return [{"_value": parsed}]
        except Exception:
            # 非 JSON 的纯文本（例如 markdown 表格）
            return [{"_text": s}]

    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        # 股票服务：把 answer 表格转成可读记录
        if "answer" in raw:
            return [raw]
        return [raw]
    return []


if __name__ == "__main__":
    c = IfindClient()
    print("news 工具:", [t["name"] for t in c.list_tools("news")])
    print("stock 工具:", [t["name"] for t in c.list_tools("stock")])
