"""
媒体 / 传闻自动采集器 —— 补齐 T1（媒体）/ T2（研报）/ T3（传闻）三层证据
数据来源：Serper（Google Search API），由后端自动调用，无需人工核实。

与 collector_agent（走 iFinD 公告，T0）互补：
  collector_agent      → iFinD MCP 公告  → T0
  media_search_collector → Serper 搜索   → T1 / T2 / T3

写入同一张 raw_messages 表，由分析 Agent 统一消费。
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import get_db, init_db
from websearch_client import WebSearchClient, classify_domain
from agents.collector_agent import TRACKED_TICKERS


def fingerprint(ticker: str, title: str, date: str) -> str:
    return hashlib.sha256(f"web|{ticker}|{title}|{date}".encode("utf-8")).hexdigest()[:48]


def parse_date(s: str):
    """解析 Serper 返回的各种日期格式 → YYYY-MM-DD；失败返回 None"""
    if not s:
        return None
    s = str(s).strip()
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d+)\s*(小时|分钟|天|周|个月)前", s)
    if m:
        n = int(m.group(1)); unit = m.group(2)
        delta = {"小时": timedelta(hours=n), "分钟": timedelta(minutes=n),
                 "天": timedelta(days=n), "周": timedelta(weeks=n),
                 "个月": timedelta(days=n * 30)}[unit]
        return (datetime.now() - delta).strftime("%Y-%m-%d")
    return None


class MediaSearchCollector:
    name = "MediaSearchCollector"

    def __init__(self, api_key: str = None):
        self.search = WebSearchClient(api_key)

    def collect(self, days: int = 180, tickers: list = None, per_ticker: int = 8) -> dict:
        init_db()
        targets = tickers or TRACKED_TICKERS
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        db = get_db()
        cur = db.cursor()
        stats = {"fetched": 0, "new": 0, "duplicated": 0, "filtered": 0, "by_tier": {}}

        for ticker_name, ticker_code in targets:
            items = []
            queries = [
                (f"{ticker_name} 传闻 澄清", "search"),
                (f"{ticker_name} 传闻", "news"),
            ]
            for q, kind in queries:
                try:
                    if kind == "search":
                        res = self.search.search(q, num=per_ticker, tbs="qdr:y")
                    else:
                        res = self.search.news(q, num=per_ticker)
                except Exception as e:
                    print(f"[MediaSearch] {ticker_name} 搜索失败({kind}): {str(e)[:80]}")
                    continue

                for r in res:
                    stats["fetched"] += 1
                    title = (r.get("title") or "").strip()
                    snippet = (r.get("snippet") or "").strip()
                    link = (r.get("link") or "").strip()
                    date = parse_date(r.get("date")) or datetime.now().strftime("%Y-%m-%d")

                    # 相关性：标题或摘要必须提到该公司/代码
                    if ticker_name not in title and ticker_name not in snippet:
                        stats["filtered"] += 1
                        continue
                    # 时效性
                    if date < cutoff:
                        stats["filtered"] += 1
                        continue
                    # 排除公告原文（那属于 T0，由 iFinD 负责），避免重复
                    if classify_domain(link, r.get("source", "")) == "T0":
                        stats["filtered"] += 1
                        continue

                    tier = classify_domain(link, r.get("source", ""))
                    items.append({
                        "ticker": ticker_code, "ticker_name": ticker_name,
                        "source": r.get("source") or (link.split("/")[2] if "//" in link else "网络媒体"),
                        "source_type": "news" if tier in ("T1", "T2") else "rumor",
                        "source_tier": tier,
                        "title": title[:300],
                        "content": re.sub(r"\s+", " ", snippet)[:800],
                        "publish_time": date,
                        "source_url": link,
                        "fingerprint": fingerprint(ticker_code, title, date),
                    })

            # 去重（库内 + 本批内）
            fresh = []
            seen = set()
            for it in items:
                if it["fingerprint"] in seen:
                    continue
                seen.add(it["fingerprint"])
                cur.execute("SELECT 1 FROM raw_messages WHERE fingerprint = ?", (it["fingerprint"],))
                if cur.fetchone():
                    stats["duplicated"] += 1
                else:
                    fresh.append(it)

            for it in fresh:
                cur.execute("""
                    INSERT OR IGNORE INTO raw_messages
                    (ticker, ticker_name, source, source_type, source_tier, title, content,
                     publish_time, source_url, fingerprint, processed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (it["ticker"], it["ticker_name"], it["source"], it["source_type"],
                      it["source_tier"], it["title"], it["content"], it["publish_time"],
                      it["source_url"], it["fingerprint"]))
                if cur.rowcount > 0:
                    stats["new"] += 1
                    stats["by_tier"][it["source_tier"]] = stats["by_tier"].get(it["source_tier"], 0) + 1

            db.commit()
            print(f"[MediaSearch] {ticker_name}: 命中 {len(fresh)} 条")

        db.close()
        return stats


if __name__ == "__main__":
    c = MediaSearchCollector()
    r = c.collect(days=180)
    print(json.dumps(r, ensure_ascii=False, indent=2))
