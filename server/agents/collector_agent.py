"""
采集 Agent（Collector）— 感知层，轻量 Agent
模型：glm-4-flash（小模型，高吞吐低判断）
职责：
  1. 从 iFinD MCP 抓取公告 / 新闻
  2. 指纹去重
  3. 要素预抽取（主题 / 方向 / 是否事件相关）—— 用 LLM，但是轻量判断
  4. 写入 raw_messages 队列，供分析 Agent 消费

边界：不做状态裁决、不做卡片生成（那些是分析 Agent 的活）。
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ifind_client import IfindClient, parse_ifind_records
from llm_client import LLMClient
from models import get_db, init_db

# 跟踪标的池 —— 覆盖 A 股各行业龙头 + 港股龙头，用于扩充发现页信息流
TRACKED_TICKERS = [
    # 新能源 / 电池
    ("宁德时代", "300750.SZ"), ("比亚迪", "002594.SZ"), ("隆基绿能", "601012.SH"),
    ("通威股份", "600438.SH"), ("阳光电源", "300274.SZ"),
    # 半导体 / 科技
    ("中芯国际", "688981.SH"), ("北方华创", "002371.SZ"), ("韦尔股份", "603501.SH"),
    ("海康威视", "002415.SZ"), ("立讯精密", "002475.SZ"), ("京东方A", "000725.SZ"),
    # 消费 / 白酒 / 食品
    ("贵州茅台", "600519.SH"), ("五粮液", "000858.SZ"), ("山西汾酒", "600809.SH"),
    ("泸州老窖", "000568.SZ"), ("伊利股份", "600887.SH"), ("中国中免", "601888.SH"),
    ("美的集团", "000333.SZ"), ("格力电器", "000651.SZ"), ("海尔智家", "600690.SH"),
    # 金融
    ("招商银行", "600036.SH"), ("中国平安", "601318.SH"), ("中信证券", "600030.SH"),
    ("东方财富", "300059.SZ"),
    # 医药
    ("恒瑞医药", "600276.SH"), ("药明康德", "603259.SH"), ("迈瑞医疗", "300760.SZ"),
    # 资源 / 化工 / 制造
    ("紫金矿业", "601899.SH"), ("万华化学", "600309.SH"), ("三一重工", "600031.SH"),
    ("牧原股份", "002714.SZ"), ("长江电力", "600900.SH"),
    # 港股
    ("腾讯控股", "00700.HK"), ("美团", "03690.HK"), ("小米集团", "01810.HK"),
]

# 来源分级规则表（确定性，优先级高于 LLM）
T1_SOURCES = ["财新", "第一财经", "证券时报", "上海证券报", "界面", "36氪", "每日经济新闻", "e公司"]
T2_SOURCES = ["证券", "研报", "中金", "中信", "华泰", "国泰君安", "招商", "光大", "东方"]


def classify_tier(source: str, source_type: str) -> str:
    if source_type == "notice":
        return "T0"
    if any(s in source for s in T2_SOURCES):
        return "T2"
    if any(s in source for s in T1_SOURCES):
        return "T1"
    if source_type == "news":
        return "T1"
    return "T3"


def fingerprint(ticker: str, title: str, date: str) -> str:
    return hashlib.sha256(f"{ticker}|{title}|{date}".encode("utf-8")).hexdigest()[:48]


PRESCREEN_SYSTEM = """你是金融信息预筛员。对每条消息判断：

- is_event_relevant: 是否为"投资事件相关"信息（true/false）
  * 是：公司经营、业绩、重大合同、股权变动、产品进展、监管处罚等有信息价值的事件
  * 否：纯格式化公告（如"股份发行人的证券变动月报表""董事名单"）、无实质内容的模板文件
- theme: 事件主题（4-8字），如"股份回购""储能扩张""业绩预告""对外担保"
- direction: positive(利好) / negative(利空) / neutral(中性)

只输出 JSON 数组，不要解释。格式：
[{"id":1,"is_event_relevant":true,"theme":"股份回购","direction":"positive"}]"""


class CollectorAgent:
    name = "Collector"

    def __init__(self, model: str = None):
        self.ifind = IfindClient()
        # 采集用轻量模型；若小模型不可用，回落强模型
        self.llm = LLMClient(model=model or "glm-4-flash")
        self.fallback_llm = LLMClient(model="glm-4.6")

    # ═══ 主入口 ═══
    def collect(self, days: int = 30, tickers: list = None) -> dict:
        init_db()
        targets = tickers or TRACKED_TICKERS
        time_end = datetime.now().strftime("%Y-%m-%d")
        time_start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        db = get_db()
        cur = db.cursor()
        stats = {"fetched": 0, "new": 0, "duplicated": 0, "filtered_out": 0, "per_ticker": {}}

        for ticker_name, ticker_code in targets:
            items = []
            # 公告（T0）
            try:
                res = self.ifind.call("news", "search_notice", {
                    "query": ticker_name, "time_start": time_start,
                    "time_end": time_end, "size": 10})
                for rec in parse_ifind_records(res):
                    items.append(self._normalize(rec, "notice", ticker_name, ticker_code))
            except Exception as e:
                print(f"[Collector] {ticker_name} 公告失败: {e}")
            # 新闻（T1）
            try:
                res = self.ifind.call("news", "search_news", {
                    "query": ticker_name, "time_start": time_start,
                    "time_end": time_end, "size": 10})
                for rec in parse_ifind_records(res):
                    items.append(self._normalize(rec, "news", ticker_name, ticker_code))
            except Exception as e:
                print(f"[Collector] {ticker_name} 新闻失败: {e}")

            items = [i for i in items if i["title"]]
            stats["fetched"] += len(items)

            # 去重（库内已存在的跳过）
            fresh = []
            for it in items:
                cur.execute("SELECT 1 FROM raw_messages WHERE fingerprint = ?", (it["fingerprint"],))
                if cur.fetchone():
                    stats["duplicated"] += 1
                else:
                    fresh.append(it)

            # LLM 预筛（轻量）
            if fresh:
                screened = self._prescreen(ticker_name, fresh)
                for it, s in zip(fresh, screened):
                    if not s.get("is_event_relevant", True):
                        stats["filtered_out"] += 1
                        continue
                    it["extract_json"] = json.dumps(
                        {"theme": s.get("theme"), "direction": s.get("direction")}, ensure_ascii=False)
                    cur.execute("""
                        INSERT OR IGNORE INTO raw_messages
                        (ticker, ticker_name, source, source_type, source_tier, title, content,
                         publish_time, fingerprint, extract_json, processed)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """, (it["ticker"], it["ticker_name"], it["source"], it["source_type"],
                          it["source_tier"], it["title"], it["content"], it["publish_time"],
                          it["fingerprint"], it["extract_json"]))
                    if cur.rowcount > 0:
                        stats["new"] += 1

            stats["per_ticker"][ticker_name] = len(fresh)
            print(f"[Collector] {ticker_name}: 抓取 {len(items)}，新增 {len(fresh)}")

        db.commit()
        db.close()
        return stats

    # ═══ 归一化 iFinD 返回 ═══
    @staticmethod
    def _normalize(rec: dict, source_type: str, ticker_name: str, ticker_code: str) -> dict:
        title = (rec.get("公告标题") or rec.get("新闻标题") or rec.get("标题") or "").strip()
        content = (rec.get("公告片段内容") or rec.get("新闻片段内容") or rec.get("片段内容") or "").strip()
        date = str(rec.get("日期") or rec.get("公告日期") or rec.get("新闻日期") or "")[:10]
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        source = "公司公告" if source_type == "notice" else (rec.get("来源") or "财经媒体")
        return {
            "ticker": ticker_code,
            "ticker_name": ticker_name,
            "source": source,
            "source_type": source_type,
            "source_tier": classify_tier(source, source_type),
            "title": title[:300],
            "content": re.sub(r"\s+", " ", content)[:800],
            "publish_time": date,
            "fingerprint": fingerprint(ticker_code, title, date),
        }

    # ═══ LLM 预筛（带降级） ═══
    def _prescreen(self, ticker_name: str, items: list) -> list:
        payload = [{"id": i, "title": it["title"][:120]} for i, it in enumerate(items)]
        user = f"标的：{ticker_name}\n\n消息列表：\n{json.dumps(payload, ensure_ascii=False)}"
        for llm in (self.llm, self.fallback_llm):
            try:
                resp = llm.chat([{"role": "user", "content": user}],
                                system=PRESCREEN_SYSTEM, max_tokens=2000, temperature=0.1, thinking=False)
                arr = _extract_json(LLMClient.extract_text(resp)) or []
                if arr:
                    # 对齐回 items（按 id）
                    out = []
                    for i, it in enumerate(items):
                        hit = next((x for x in arr if x.get("id") == i), None) or {}
                        out.append({
                            "is_event_relevant": hit.get("is_event_relevant", True),
                            "theme": hit.get("theme") or self._rule_theme(it["title"]),
                            "direction": hit.get("direction") or "neutral",
                        })
                    return out
            except Exception as e:
                print(f"[Collector] 预筛失败({llm.model}): {e}，尝试降级")
        # 完全兜底：规则
        return [{"is_event_relevant": not self._is_format_only(it["title"]),
                 "theme": self._rule_theme(it["title"]), "direction": "neutral"} for it in items]

    @staticmethod
    def _is_format_only(title: str) -> bool:
        return any(w in title for w in ["月报表", "董事名单", "通函", "公司章程", "英文版"])

    @staticmethod
    def _rule_theme(title: str) -> str:
        for kw, name in [("回购", "股份回购"), ("业绩", "业绩披露"), ("财报", "定期报告"),
                         ("储能", "储能业务"), ("销量", "销量数据"), ("扩产", "产能扩张"),
                         ("担保", "对外担保"), ("分红", "利润分配"), ("减持", "股东减持"),
                         ("增持", "股东增持"), ("合作", "战略合作"), ("订单", "订单获取")]:
            if kw in (title or ""):
                return name
        return "公司动态"


def _extract_json(text: str):
    if not text:
        return None
    t = re.sub(r"^```(?:json)?\s*", "", text.strip())
    t = re.sub(r"\s*```$", "", t)
    for o, c in (("[", "]"), ("{", "}")):
        i, j = t.find(o), t.rfind(c)
        if i >= 0 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                continue
    return None


if __name__ == "__main__":
    agent = CollectorAgent()
    r = agent.collect(days=30)
    print(json.dumps(r, ensure_ascii=False, indent=2))
