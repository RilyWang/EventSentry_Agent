#!/usr/bin/env python3
"""
iFinD 数据采集脚本
调用同花顺 iFinD Python SDK 获取公告、新闻、研报等原始数据
输出标准化 JSON，可直接写入 MySQL raw_messages 表

环境要求：
  pip install iFinDApi mysql-connector-python python-dotenv

使用方式：
  python ifind_collector.py --ticker 300750.SZ --days 30
  python ifind_collector.py --config tickers.json --days 7
"""

import argparse
import csv
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# 尝试导入 iFinD SDK
try:
    from iFinDApi import *
except ImportError:
    print("[WARN] iFinDApi not installed. Running in MOCK mode.")
    # Mock 模式：用于开发和测试
    IFIND_MOCK = True
else:
    IFIND_MOCK = False

# 数据库连接
try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False


def get_db_connection():
    """从环境变量获取数据库连接"""
    url = os.getenv("DATABASE_URL", "")
    # 解析 mysql://user:pass@host:port/db
    if url.startswith("mysql://"):
        url = url[8:]
    if "@" in url:
        creds, hostpart = url.split("@", 1)
        user, password = creds.split(":", 1) if ":" in creds else (creds, "")
        if "/" in hostpart:
            hostport, db = hostpart.split("/", 1)
        else:
            hostport, db = hostpart, "eventsentry"
        if ":" in hostport:
            host, port = hostport.split(":", 1)
            port = int(port)
        else:
            host, port = hostport, 3306
    else:
        user = os.getenv("DB_USER", "root")
        password = os.getenv("DB_PASSWORD", "")
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "3306"))
        db = os.getenv("DB_NAME", "eventsentry")

    if not MYSQL_AVAILABLE:
        return None
    return mysql.connector.connect(
        host=host, port=port, user=user, password=password, database=db
    )


def simhash_fingerprint(text: str) -> str:
    """简单指纹去重（生产环境建议用 simhash）"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def parse_ifind_csv(csv_text: str) -> List[Dict]:
    """解析 iFinD 返回的 CSV 字符串"""
    if not csv_text or csv_text.strip() == "":
        return []
    f = io.StringIO(csv_text)
    reader = csv.DictReader(f)
    return [row for row in reader]


def mock_announcements(ticker: str, start_date: str, end_date: str) -> List[Dict]:
    """Mock 数据：用于无 iFinD SDK 时的开发测试"""
    return [
        {
            "reportDate": end_date,
            "reportTitle": f"{ticker} 关于日常经营情况的公告",
            "reportType": "日常公告",
        },
        {
            "reportDate": start_date,
            "reportTitle": f"{ticker} 2025年半年度报告摘要",
            "reportType": "定期报告",
        },
    ]


def fetch_announcements(ticker: str, start_date: str, end_date: str) -> List[Dict]:
    """获取公司公告"""
    if IFIND_MOCK:
        return mock_announcements(ticker, start_date, end_date)

    # iFinD API: 获取公司公告
    # THS_AnnouncementInfo 是 iFinD 的公告查询函数
    result = THS_AnnouncementInfo(
        ticker,
        f"startDate={start_date};endDate={end_date};reportType=ALL",
        "reportDate:Y,reportTitle:Y,reportType:Y"
    )
    if result and result.errorcode == 0:
        return parse_ifind_csv(result.to_csv())
    print(f"[ERROR] iFinD announcements error: {result.errormsg if result else 'None'}")
    return []


def fetch_news(ticker: str, start_date: str, end_date: str) -> List[Dict]:
    """获取新闻"""
    if IFIND_MOCK:
        return [
            {"publishTime": end_date, "title": f"{ticker} 获机构关注", "source": "证券时报"},
        ]

    result = THS_NewsInfo(
        ticker,
        f"startDate={start_date};endDate={end_date}",
        "publishTime:Y,title:Y,source:Y"
    )
    if result and result.errorcode == 0:
        return parse_ifind_csv(result.to_csv())
    return []


def fetch_research(ticker: str, start_date: str, end_date: str) -> List[Dict]:
    """获取研报"""
    if IFIND_MOCK:
        return [
            {"publishDate": end_date, "title": f"{ticker} 深度研究", "orgName": "中信证券"},
        ]

    result = THS_ResearchReport(
        ticker,
        f"startDate={start_date};endDate={end_date}",
        "publishDate:Y,title:Y,orgName:Y"
    )
    if result and result.errorcode == 0:
        return parse_ifind_csv(result.to_csv())
    return []


def to_raw_message(ticker: str, item: Dict, msg_type: str) -> Optional[Dict]:
    """将 iFinD 原始数据转换为 raw_messages 表结构"""
    title = item.get("reportTitle") or item.get("title") or ""
    if not title:
        return None

    date_str = (
        item.get("reportDate")
        or item.get("publishTime")
        or item.get("publishDate")
        or datetime.now().strftime("%Y-%m-%d")
    )

    source = item.get("source") or item.get("orgName") or item.get("reportType") or "iFinD"
    content = item.get("content") or title

    fingerprint = simhash_fingerprint(f"{ticker}:{title}:{date_str}")

    return {
        "ticker": ticker,
        "source": source,
        "sourceType": msg_type,
        "sourceUrl": "",
        "title": title,
        "content": content[:500],
        "publishTime": date_str,
        "fingerprint": fingerprint,
        "processed": False,
    }


def save_to_db(messages: List[Dict]) -> int:
    """将消息写入 MySQL raw_messages 表，返回插入数量"""
    if not messages:
        return 0

    conn = get_db_connection()
    if not conn:
        # 无数据库时输出到 JSON 文件
        out_path = os.path.join(os.path.dirname(__file__), "../data/raw_messages.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        print(f"[DB SKIP] Saved {len(messages)} messages to {out_path}")
        return len(messages)

    cursor = conn.cursor()
    inserted = 0
    for msg in messages:
        try:
            cursor.execute(
                """
                INSERT INTO rawMessages
                (ticker, source, sourceType, sourceUrl, title, content, publishTime, fingerprint, processed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                source = VALUES(source), content = VALUES(content)
                """,
                (
                    msg["ticker"], msg["source"], msg["sourceType"],
                    msg.get("sourceUrl", ""), msg["title"], msg["content"],
                    msg["publishTime"], msg["fingerprint"], msg["processed"]
                )
            )
            if cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            print(f"[DB ERROR] {e}")
    conn.commit()
    cursor.close()
    conn.close()
    return inserted


def collect(ticker: str, days: int = 30) -> int:
    """采集单个标的的数据"""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    print(f"[Collector] {ticker} | {start_date} ~ {end_date}")

    all_messages = []

    # 1. 公告
    announcements = fetch_announcements(ticker, start_date, end_date)
    for item in announcements:
        msg = to_raw_message(ticker, item, "announcement")
        if msg:
            all_messages.append(msg)
    print(f"  Announcements: {len(announcements)}")

    # 2. 新闻
    news = fetch_news(ticker, start_date, end_date)
    for item in news:
        msg = to_raw_message(ticker, item, "news")
        if msg:
            all_messages.append(msg)
    print(f"  News: {len(news)}")

    # 3. 研报
    research = fetch_research(ticker, start_date, end_date)
    for item in research:
        msg = to_raw_message(ticker, item, "research")
        if msg:
            all_messages.append(msg)
    print(f"  Research: {len(research)}")

    # 写入数据库
    inserted = save_to_db(all_messages)
    print(f"  Inserted/Updated: {inserted}")
    return inserted


def main():
    parser = argparse.ArgumentParser(description="iFinD Data Collector")
    parser.add_argument("--ticker", help="Single ticker to collect")
    parser.add_argument("--config", help="JSON config file with ticker list")
    parser.add_argument("--days", type=int, default=30, help="Lookback days")
    parser.add_argument("--mock", action="store_true", help="Force mock mode")
    args = parser.parse_args()

    global IFIND_MOCK
    if args.mock:
        IFIND_MOCK = True

    # 登录 iFinD（非 mock 模式）
    if not IFIND_MOCK:
        key = os.getenv("IFIND_API_KEY", "")
        if not key:
            print("[ERROR] IFIND_API_KEY not set")
            sys.exit(1)
        login_result = THS_iFinDLogin(key, "")
        if login_result != 0:
            print(f"[ERROR] iFinD login failed: {login_result}")
            sys.exit(1)
        print("[iFinD] Login success")

    tickers = []
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            tickers = json.load(f)
    elif args.ticker:
        tickers = [args.ticker]
    else:
        # 默认标的
        tickers = ["300750.SZ", "002594.SZ", "688981.SH", "000858.SZ", "00700.HK"]

    total = 0
    for ticker in tickers:
        total += collect(ticker, args.days)

    print(f"\n[Done] Total messages: {total}")

    if not IFIND_MOCK:
        THS_iFinDLogout()


if __name__ == "__main__":
    main()
