"""
EventSentry Agent — 真实的工具调用型 Agent
流程：用户提问 → LLM 决策调用哪个 iFinD 工具 → 执行真实数据查询 → LLM 基于真实数据回答
所有事实性内容均来自 iFinD MCP（同花顺）实时返回，禁止编造。
"""
import json
import re
from datetime import datetime, timedelta

from ifind_client import IfindClient, IfindError, parse_ifind_records
from llm_client import LLMClient, LLMError

# ─── System Prompt（源自 docs/05-skills/Agent.md 的人格设定） ───
SYSTEM_PROMPT = """你是 EventSentry（事件参谋），一位严谨的投资事件情报分析师。

【最高原则】
1. 你的所有事实性陈述必须来自工具（iFinD/同花顺）返回的真实数据，绝不编造。
2. 如果工具没有返回相关信息，必须明确说"未检索到相关公开信息"，不得推测填充。
3. 每条结论都要标注来源（公告/新闻/研报/行情），让用户可追溯。

【职责】
- 从公开信息中识别、聚合、整理同一投资事件的演化过程
- 区分事实（公告）、观点（研报）、推测、传闻，并标注证据层级：
  * T0 公司公告/交易所披露 — 最高可信度
  * T1 权威媒体（财新、第一财经、证券时报等）
  * T2 券商研报观点
  * T3 市场传闻/股吧 — 必须标注"未证实"
- 维护事件状态判断（未证实传闻 → 媒体验证 → 官方确认 → 落地/否认/过期）
- 呈现事件当前状态、主要风险和下一步关注点

【绝不做】
1. 预测股价或给出买卖建议
2. 使用"一定""必然""稳赚"等绝对化表述
3. 把传闻当作事实陈述
4. 询问用户账户密码、资金量等敏感信息

【工具使用策略】
- 问某公司"有什么大事/公告" → 先 search_notice，必要时补 search_news
- 问"最近热点/行业动态" → search_trending_news
- 问"股价表现/涨跌/影响" → get_stock_performance
- 问"财务/业绩/营收" → get_stock_financials
- 问"公司基本情况/上市时间/市值" → get_stock_info
- 每次可并行调用多个工具，尽量把事实查全再作答

【语言风格】
冷静、克制、结构化。先说状态，再给依据，最后提示风险。对不确定性明确承认。
回复用中文，控制在 400 字以内，条理清晰，适当使用列表。"""

# ─── 工具定义（Anthropic tool-use 格式） ───
TOOLS_SPEC = [
    {
        "name": "search_notice",
        "description": "检索上市公司公告原文片段。用于查询公司正式公告、定期报告、临时公告等权威披露信息（T0 最高可信度）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "查询内容，如 '宁德时代 储能业务'、'比亚迪 销量'"},
                "time_start": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                "time_end": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                "size": {"type": "integer", "description": "返回条数，默认 5，最大 10"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_news",
        "description": "检索财经新闻语义片段。用于查询媒体报道、行业动态、事件报道（T1 权威媒体）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "查询内容，如 '宁德时代 储能订单'"},
                "time_start": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                "time_end": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                "size": {"type": "integer", "description": "返回条数，默认 5"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_trending_news",
        "description": "查询热点事件资讯。用于了解当前市场热点、行业重大动态。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "关键词，如 '智能体'、'固态电池'"},
                "industry_name": {"type": "string", "description": "行业名称，如 '计算机'、'电力设备'"},
                "time_scope": {"type": "string", "description": "时效范围，如 '24小时'、'一周'"},
                "size": {"type": "integer", "description": "返回条数，默认 5"},
            },
            "required": [],
        },
    },
    {
        "name": "get_stock_performance",
        "description": "查询股票日频行情与技术指标（涨跌幅、成交量等）。用于验证事件发生后的市场影响。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "股票简称+指标+时间，如 '宁德时代近5日涨跌幅'"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_stock_financials",
        "description": "查询财务数据与指标（营收、净利润、ROE、毛利率等）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "股票简称+财务指标+财报日期，如 '宁德时代2025年三季度ROE'"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_stock_info",
        "description": "查询股票基本资料（上市时间、所属行业、市值等）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "股票简称+指标，如 '比亚迪 总市值 所属行业'"},
            },
            "required": ["query"],
        },
    },
]

# 工具名 → (server_type, mcp_tool_name)
TOOL_ROUTING = {
    "search_notice": ("news", "search_notice"),
    "search_news": ("news", "search_news"),
    "search_trending_news": ("news", "search_trending_news"),
    "get_stock_performance": ("stock", "get_stock_performance"),
    "get_stock_financials": ("stock", "get_stock_financials"),
    "get_stock_info": ("stock", "get_stock_info"),
}

# 工具 → 证据层级
TIER_MAP = {
    "search_notice": "T0",
    "search_news": "T1",
    "search_trending_news": "T1",
    "get_stock_performance": "行情",
    "get_stock_financials": "财务",
    "get_stock_info": "资料",
}


class EventSentryAgent:
    def __init__(self):
        self.ifind = IfindClient()
        self.llm = LLMClient()
        self.max_iterations = 6

    # ─── 执行单个工具 ───
    def _run_tool(self, name, args):
        if name not in TOOL_ROUTING:
            return {"error": f"unknown tool: {name}"}
        server_type, mcp_name = TOOL_ROUTING[name]

        params = {k: v for k, v in args.items() if v is not None}
        # 默认时间范围：最近 1 年
        if name in ("search_notice", "search_news"):
            params.setdefault("time_start", (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
            params.setdefault("time_end", datetime.now().strftime("%Y-%m-%d"))
            params.setdefault("size", 5)
        if name == "search_trending_news":
            params.setdefault("time_scope", "一周")
            params.setdefault("size", 5)

        try:
            result = self.ifind.call(server_type, mcp_name, params)
            records = parse_ifind_records(result)
            return {"ok": True, "records": records, "raw": result}
        except IfindError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    # ─── 主循环 ───
    def run(self, user_question, history=None):
        """
        执行 Agent 推理循环，返回:
        {
          "answer": str,          # LLM 最终回答
          "citations": [...],     # 真实数据来源（可追溯）
          "tools_used": [...],    # 调用过的工具
          "iterations": int,
        }
        """
        messages = []
        if history:
            for h in history[-6:]:
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": user_question})

        citations = []
        tools_used = []
        iterations = 0
        final_text = ""

        for i in range(self.max_iterations):
            iterations = i + 1
            try:
                resp = self.llm.chat(messages, system=SYSTEM_PROMPT, tools=TOOLS_SPEC)
            except LLMError as e:
                return {
                    "answer": f"抱歉，推理服务暂时不可用（{e}）。请稍后重试。",
                    "citations": citations, "tools_used": tools_used, "iterations": iterations,
                    "error": str(e),
                }

            tool_uses = LLMClient.extract_tool_uses(resp)
            text = LLMClient.extract_text(resp)

            if not tool_uses:
                final_text = text
                break

            # 记录 assistant 的工具调用消息
            messages.append({"role": "assistant", "content": resp.get("content", [])})

            # 执行所有工具调用
            tool_results = []
            for tu in tool_uses:
                name = tu.get("name")
                args = tu.get("input", {})
                tools_used.append({"tool": name, "args": args})

                out = self._run_tool(name, args)

                if out.get("ok") and out.get("records"):
                    for rec in out["records"][:5]:
                        citations.append(self._to_citation(name, rec))
                    summary = json.dumps(out["records"][:5], ensure_ascii=False)[:3000]
                else:
                    summary = json.dumps(out, ensure_ascii=False)[:500]

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.get("id"),
                    "content": summary,
                })

            messages.append({"role": "user", "content": tool_results})

        if not final_text:
            final_text = "已完成数据检索，请查看下方来源。如需进一步分析，请追问。"

        # 去重 citations
        seen = set()
        unique_citations = []
        for c in citations:
            key = (c.get("source"), c.get("date"), (c.get("summary") or "")[:60])
            if key not in seen:
                seen.add(key)
                unique_citations.append(c)

        return {
            "answer": final_text,
            "citations": unique_citations,
            "tools_used": tools_used,
            "iterations": iterations,
        }

    def _to_citation(self, tool_name, rec):
        """把 iFinD 原始记录转成前端可展示的引用（兼容公告/新闻 与 行情/财务 两种格式）"""
        tier = TIER_MAP.get(tool_name, "?")
        if not isinstance(rec, dict):
            return {"tier": tier, "source": "iFinD", "summary": str(rec)[:200],
                    "date": "", "data_source": "iFinD/同花顺"}

        # ── 行情/财务格式：{"answer": "markdown表格"} ──
        if "answer" in rec:
            return {"tier": tier, "source": f"iFinD · {tool_name}",
                    "summary": re.sub(r"\s+", " ", str(rec["answer"]))[:400],
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "data_source": "iFinD/同花顺"}

        # ── 行情快照格式：{"tables": [[表头...],[数据...]]} ──
        if "tables" in rec and rec["tables"]:
            tbl = rec["tables"]
            head = " | ".join(str(x) for x in tbl[0]) if tbl else ""
            body = " | ".join(str(x) for x in tbl[1]) if len(tbl) > 1 else ""
            return {"tier": tier, "source": "iFinD · 实时行情",
                    "summary": f"{head} ‖ {body}"[:400],
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "data_source": "iFinD/同花顺"}

        # ── 公告/新闻格式 ──
        title = (rec.get("公告标题") or rec.get("新闻标题") or rec.get("标题")
                 or rec.get("股票简称") or "")
        snippet = (rec.get("公告片段内容") or rec.get("新闻片段内容") or rec.get("内容")
                   or rec.get("片段内容") or "")
        date = rec.get("日期") or rec.get("公告日期") or rec.get("新闻日期") or rec.get("时间") or ""

        if not snippet:
            snippet = " | ".join(f"{k}:{v}" for k, v in list(rec.items())[:6]
                                 if not isinstance(v, (dict, list)))

        return {
            "tier": tier,
            "source": title or f"iFinD · {tool_name}",
            "summary": re.sub(r"\s+", " ", str(snippet))[:400],
            "date": str(date),
            "data_source": "iFinD/同花顺",
        }


if __name__ == "__main__":
    agent = EventSentryAgent()
    print("=== 测试 Agent ===")
    q = "宁德时代最近有什么重大公告？"
    print("问题:", q)
    r = agent.run(q)
    print("\n回答:", r["answer"])
    print("\n调用工具:", r["tools_used"])
    print("\n引用来源数:", len(r["citations"]))
    for c in r["citations"][:3]:
        print(f"  [{c['tier']}] {c['source']} ({c['date']})")
