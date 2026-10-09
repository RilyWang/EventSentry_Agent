"""
LLM 客户端 — 智谱 BigModel (GLM-4.6)，Anthropic 兼容接口
用于 Agent 推理：意图理解 + 工具调用决策 + 结果分析
"""
import os
os.environ.setdefault("no_proxy", "*")
os.environ.setdefault("NO_PROXY", "*")

import json
import warnings
import requests

warnings.filterwarnings("ignore")

# 从 .env 读取（python-dotenv 可选；无则用环境变量）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

DEFAULT_BASE = "https://open.bigmodel.cn/api/anthropic"
DEFAULT_MODEL = "glm-4.6"


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or os.getenv("LLM_API_KEY") or ""
        if not self.api_key:
            raise LLMError(
                "缺少 LLM_API_KEY。请在 server/.env 中配置，或设置同名环境变量。"
            )
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL") or DEFAULT_MODEL

    def chat(self, messages, system=None, tools=None, max_tokens=2000,
             temperature=0.3, thinking=True):
        """
        调用 LLM，返回原始响应 dict。
        thinking=False 可关闭 GLM 的思考模式 —— 结构化抽取类任务无需思考，
        实测延迟由 ~8.4s 降至 ~3.0s（约 3 倍提速）。
        """
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools
        if not thinking:
            body["thinking"] = {"type": "disabled"}

        resp = requests.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
            verify=False,
            timeout=120,
            proxies={"http": None, "https": None},
        )
        if resp.status_code != 200:
            raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    @staticmethod
    def extract_text(response):
        """从响应中提取纯文本（忽略 thinking 块）"""
        parts = []
        for block in response.get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts).strip()

    @staticmethod
    def extract_tool_uses(response):
        """提取工具调用请求"""
        return [b for b in response.get("content", []) if b.get("type") == "tool_use"]


if __name__ == "__main__":
    c = LLMClient()
    r = c.chat([{"role": "user", "content": "用一句话说明你是谁"}])
    print("模型:", c.model)
    print("回复:", c.extract_text(r))
