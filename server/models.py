import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "db_data", "eventsentry.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _ensure_column(cur, table, column, decl):
    """SQLite 不支持 ADD COLUMN IF NOT EXISTS，手动检查"""
    cur.execute(f"PRAGMA table_info({table})")
    cols = {r[1] for r in cur.fetchall()}
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    # ─── v2.2 新增表：原始消息队列 ───
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            ticker_name TEXT,
            source TEXT,
            source_type TEXT NOT NULL,          -- notice / news / research / trending
            source_tier TEXT,                   -- T0/T1/T2/T3
            title TEXT NOT NULL,
            content TEXT,
            publish_time TEXT,
            crawl_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fingerprint TEXT NOT NULL UNIQUE,
            extract_json TEXT,                  -- 采集 Agent 抽取的要素
            processed INTEGER DEFAULT 0,
            assigned_event_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ─── v2.2 新增表：反思日志 ───
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reflection_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            transitions_reviewed INTEGER DEFAULT 0,
            misjudged INTEGER DEFAULT 0,
            controversial INTEGER DEFAULT 0,
            report_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ─── v2.2 新增表：来源质量（Reflector 校准） ───
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_quality (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL UNIQUE,
            tier TEXT,
            total_predictions INTEGER DEFAULT 0,
            correct_predictions INTEGER DEFAULT 0,
            hit_rate REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 用户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            union_id TEXT UNIQUE,
            name TEXT,
            email TEXT,
            avatar TEXT,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 事件表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            ticker TEXT NOT NULL,
            ticker_name TEXT NOT NULL,
            theme TEXT NOT NULL,
            headline TEXT NOT NULL,
            status TEXT NOT NULL,
            nature TEXT NOT NULL,
            nature_label TEXT NOT NULL,
            event_time TEXT,
            disclosure_time TEXT,
            crawl_time TEXT,
            expires_at TEXT,
            current_version_id INTEGER,
            timeline TEXT NOT NULL DEFAULT '[]',
            evidence TEXT NOT NULL DEFAULT '{}',
            directions TEXT NOT NULL DEFAULT '[]',
            rumors TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 事件版本表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            status TEXT NOT NULL,
            nature TEXT NOT NULL,
            headline TEXT NOT NULL,
            timeline_snapshot TEXT NOT NULL DEFAULT '[]',
            evidence_snapshot TEXT NOT NULL DEFAULT '{}',
            directions_snapshot TEXT NOT NULL DEFAULT '[]',
            change_type TEXT NOT NULL,
            change_reason TEXT,
            created_by TEXT DEFAULT 'analyst',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 时间线节点表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS timeline_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            date TEXT NOT NULL,
            label TEXT NOT NULL,
            summary TEXT NOT NULL,
            tier TEXT NOT NULL,
            is_current INTEGER DEFAULT 0,
            order_index INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 证据项表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evidence_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            date TEXT NOT NULL,
            summary TEXT NOT NULL,
            tier TEXT NOT NULL,
            credibility_score REAL,
            verified INTEGER DEFAULT 0,
            raw_message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 演化方向表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_directions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT NOT NULL,
            probability TEXT NOT NULL,
            supporting TEXT NOT NULL DEFAULT '[]',
            risk TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 持仓表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            ticker_name TEXT NOT NULL,
            cost_price TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 事件订阅表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, event_id)
        )
    """)

    # 用户偏好表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            risk_level TEXT DEFAULT 'moderate',
            notification_enabled INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 通知表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ─── v2.2 为已有表补充字段（状态机 + 证据类型） ───
    _ensure_column(cursor, "raw_messages", "source_url", "TEXT")
    _ensure_column(cursor, "events", "state_code", "TEXT")
    _ensure_column(cursor, "events", "state_label", "TEXT")
    _ensure_column(cursor, "events", "notification_level", "TEXT")
    _ensure_column(cursor, "events", "risk_note", "TEXT")
    _ensure_column(cursor, "events", "confidence", "TEXT")
    _ensure_column(cursor, "events", "confidence_reason", "TEXT")
    _ensure_column(cursor, "events", "last_evidence_at", "TEXT")
    _ensure_column(cursor, "evidence_items", "evidence_type", "TEXT")
    _ensure_column(cursor, "evidence_items", "raw_message_id", "INTEGER")
    _ensure_column(cursor, "event_versions", "notification_level", "TEXT")
    _ensure_column(cursor, "event_versions", "rule_fired", "TEXT")

    conn.commit()
    conn.close()

def seed_events():
    """插入种子数据（仅首次）"""
    conn = get_db()
    cursor = conn.cursor()

    # 检查是否已有数据
    cursor.execute("SELECT COUNT(*) FROM events")
    if cursor.fetchone()[0] > 0:
        conn.close()
        print("[DB] Events already seeded, skipping.")
        return

    events_data = [
        {
            "event_id": "000858_SZ_中秋国庆动销",
            "ticker": "000858.SZ",
            "ticker_name": "五粮液",
            "theme": "中秋国庆动销",
            "headline": "中秋国庆双节动销数据出炉，高端白酒需求稳中有升，库存去化顺利",
            "status": "官方确认",
            "nature": "positive",
            "nature_label": "利好",
            "event_time": "2025-10-01",
            "disclosure_time": "2025-10-05",
            "crawl_time": "2025-10-05",
            "updated_at": "2025-10-05",
            "timeline": [
                {"date": "2025-09", "label": "传闻出现", "summary": "经销商反馈动销良好", "tier": "T3", "is_current": False},
                {"date": "2025-10", "label": "官方确认", "summary": "公司披露双节销售数据", "tier": "T0", "is_current": True}
            ],
            "evidence": {
                "T0": [{"source": "公司公告", "date": "2025-10-05", "summary": "双节期间销售收入同比增长12%，库存周转天数下降", "url": "#"}],
                "T1": [{"source": "酒业家", "date": "2025-10-03", "summary": "高端白酒中秋动销超去年", "url": "#"}],
                "T2": [{"source": "国泰君安研报", "date": "2025-10-06", "summary": "Q4业绩确定性增强", "url": "#"}],
                "T3": []
            },
            "directions": [
                {"probability": "高", "label": "全年业绩稳健增长", "description": "双节动销超预期，全年目标有望达成", "supporting": ["销售数据验证"], "risk": "春节后消费淡季"},
                {"probability": "中", "label": "增速逐季放缓", "description": "消费复苏不及预期", "supporting": ["宏观环境分析"], "risk": "商务消费恢复缓慢"}
            ],
            "rumors": []
        },
        {
            "event_id": "300750_SZ_储能业务扩张",
            "ticker": "300750.SZ",
            "ticker_name": "宁德时代",
            "theme": "储能业务扩张",
            "headline": "公司储能业务持续扩张，海外订单增长明显，但面临地缘政治风险",
            "status": "官方确认",
            "nature": "positive",
            "nature_label": "利好",
            "event_time": "2025-06-30",
            "disclosure_time": "2025-09-15",
            "crawl_time": "2025-09-15",
            "updated_at": "2025-09-15",
            "timeline": [
                {"date": "2025-07", "label": "传闻出现", "summary": "市场传闻宁德时代获海外储能大单", "tier": "T3", "is_current": False},
                {"date": "2025-08", "label": "媒体验证", "summary": "多家媒体报道储能订单增长", "tier": "T1", "is_current": False},
                {"date": "2025-09", "label": "官方确认", "summary": "半年报披露储能业务收入同比增35%", "tier": "T0", "is_current": True}
            ],
            "evidence": {
                "T0": [{"source": "公司公告", "date": "2025-09-15", "summary": "2025年半年报：储能业务收入同比增长35.2%", "url": "#"}],
                "T1": [
                    {"source": "财新网", "date": "2025-08-20", "summary": "宁德时代储能订单海外占比提升至40%", "url": "#"},
                    {"source": "第一财经", "date": "2025-08-22", "summary": "储能业务成第二增长曲线", "url": "#"}
                ],
                "T2": [{"source": "中信证券研报", "date": "2025-09-01", "summary": "储能业务毛利率有望维持在25%以上", "url": "#"}],
                "T3": [{"source": "雪球", "date": "2025-07-10", "summary": "据传获美国某能源公司10GWh订单", "url": "#"}]
            },
            "directions": [
                {"probability": "高", "label": "储能业务成为第二增长极", "description": "海外储能需求爆发，公司产能持续扩张", "supporting": ["半年报数据验证", "媒体交叉报道"], "risk": "地缘政治风险可能影响海外订单交付"},
                {"probability": "中", "label": "增速放缓但仍稳健", "description": "行业竞争加剧，毛利率承压", "supporting": ["研报分析"], "risk": "价格战风险"}
            ],
            "rumors": [{"content": "下周将与特斯拉签署储能独家供应协议", "source": "股吧", "credibility": "低", "note": "尚无官方或权威媒体验证"}]
        },
        {
            "event_id": "688981_SH_先进制程扩产",
            "ticker": "688981.SH",
            "ticker_name": "中芯国际",
            "theme": "先进制程扩产",
            "headline": "先进制程产能持续扩张，设备国产化率提升，受出口管制影响有限",
            "status": "官方确认",
            "nature": "positive",
            "nature_label": "利好",
            "event_time": "2025-06-15",
            "disclosure_time": "2025-09-10",
            "crawl_time": "2025-09-10",
            "updated_at": "2025-09-10",
            "timeline": [
                {"date": "2025-07", "label": "传闻出现", "summary": "传闻扩产计划受阻", "tier": "T3", "is_current": False},
                {"date": "2025-08", "label": "媒体验证", "summary": "报道设备国产化替代加速", "tier": "T1", "is_current": False},
                {"date": "2025-09", "label": "官方确认", "summary": "半年报确认扩产进度正常", "tier": "T0", "is_current": True}
            ],
            "evidence": {
                "T0": [{"source": "公司公告", "date": "2025-09-10", "summary": "半年报：成熟制程产能利用率超90%，新产线按计划推进", "url": "#"}],
                "T1": [
                    {"source": "半导体行业观察", "date": "2025-08-15", "summary": "中芯国际设备国产化率提升至60%", "url": "#"},
                    {"source": "集微网", "date": "2025-08-20", "summary": "新产线投产，月产能增加2万片", "url": "#"}
                ],
                "T2": [{"source": "光大证券研报", "date": "2025-09-05", "summary": "成熟制程供需紧张，涨价预期强", "url": "#"}],
                "T3": [{"source": "匿名来源", "date": "2025-07-05", "summary": "美国将进一步收紧设备出口许可", "url": "#"}]
            },
            "directions": [
                {"probability": "中高", "label": "扩产顺利，产能释放", "description": "国产化替代加速，产能利用率维持高位", "supporting": ["半年报数据", "设备国产化报道"], "risk": "设备交付周期可能延长"},
                {"probability": "中", "label": "出口管制影响超预期", "description": "关键设备受限，扩产进度放缓", "supporting": ["传闻提示"], "risk": "技术升级速度受限"}
            ],
            "rumors": [{"content": "美国将全面禁止ASML对华出口DUV设备", "source": "匿名论坛", "credibility": "低", "note": "尚无权威来源证实"}]
        },
        {
            "event_id": "002594_SZ_高端车型销量突破",
            "ticker": "002594.SZ",
            "ticker_name": "比亚迪",
            "theme": "高端车型销量突破",
            "headline": "仰望系列销量突破，高端品牌战略初见成效，但全年目标完成仍有压力",
            "status": "官方确认",
            "nature": "positive",
            "nature_label": "利好",
            "event_time": "2025-09-01",
            "disclosure_time": "2025-09-20",
            "crawl_time": "2025-09-20",
            "updated_at": "2025-09-20",
            "timeline": [
                {"date": "2025-08", "label": "传闻出现", "summary": "仰望U8月销破千传闻", "tier": "T3", "is_current": False},
                {"date": "2025-09", "label": "官方确认", "summary": "公司披露仰望系列销量数据", "tier": "T0", "is_current": True}
            ],
            "evidence": {
                "T0": [{"source": "公司公告", "date": "2025-09-20", "summary": "9月销量快报：仰望U8月销1200辆，累计破万", "url": "#"}],
                "T1": [{"source": "汽车之家", "date": "2025-09-21", "summary": "仰望U8成为百万级新能源SUV销冠", "url": "#"}],
                "T2": [{"source": "华泰证券研报", "date": "2025-09-25", "summary": "高端化战略提振品牌溢价", "url": "#"}],
                "T3": []
            },
            "directions": [
                {"probability": "高", "label": "高端化战略持续兑现", "description": "仰望系列稳态月销破千，品牌溢价提升", "supporting": ["销量数据验证"], "risk": "全年高端车目标完成度待观察"},
                {"probability": "中", "label": "增速放缓", "description": "竞品增多，市场份额被稀释", "supporting": ["行业竞争分析"], "risk": "价格战压力"}
            ],
            "rumors": []
        },
        {
            "event_id": "00700_HK_微信AI功能上线",
            "ticker": "00700.HK",
            "ticker_name": "腾讯控股",
            "theme": "微信AI功能上线",
            "headline": "微信测试接入AI大模型功能，灰度范围扩大，商业化路径待明确",
            "status": "媒体验证",
            "nature": "positive",
            "nature_label": "利好",
            "event_time": "2025-09-01",
            "disclosure_time": "2025-09-10",
            "crawl_time": "2025-09-12",
            "updated_at": "2025-09-15",
            "timeline": [
                {"date": "2025-08", "label": "传闻出现", "summary": "网传微信将接入DeepSeek", "tier": "T3", "is_current": False},
                {"date": "2025-09", "label": "媒体验证", "summary": "多家科技媒体报道灰度测试", "tier": "T1", "is_current": True}
            ],
            "evidence": {
                "T0": [],
                "T1": [
                    {"source": "36氪", "date": "2025-09-10", "summary": "微信灰度测试AI助手，覆盖搜索和对话场景", "url": "#"},
                    {"source": "界面新闻", "date": "2025-09-12", "summary": "微信AI功能预计Q4全量上线", "url": "#"}
                ],
                "T2": [{"source": "摩根士丹利研报", "date": "2025-09-15", "summary": "AI功能有望提升广告转化率5-10%", "url": "#"}],
                "T3": [{"source": "科技博主", "date": "2025-08-20", "summary": "微信已与多家大模型厂商达成合作", "url": "#"}]
            },
            "directions": [
                {"probability": "中高", "label": "AI功能带动广告收入", "description": "搜索广告和推荐广告受益于AI提升", "supporting": ["研报预测"], "risk": "用户隐私监管趋严"},
                {"probability": "中", "label": "商业化进度慢于预期", "description": "用户体验优先，变现谨慎", "supporting": ["公司历史风格"], "risk": "竞品加速商业化"}
            ],
            "rumors": [{"content": "下周将官宣与DeepSeek独家合作", "source": "微信群聊", "credibility": "很低", "note": "无任何公开来源验证"}]
        },
        {
            "event_id": "300750_SZ_固态电池研发进展",
            "ticker": "300750.SZ",
            "ticker_name": "宁德时代",
            "theme": "固态电池研发进展",
            "headline": "固态电池研发取得阶段性进展，预计2027年量产，技术路线获市场关注",
            "status": "媒体验证",
            "nature": "positive",
            "nature_label": "利好",
            "event_time": "2025-07-15",
            "disclosure_time": "2025-08-10",
            "crawl_time": "2025-08-10",
            "updated_at": "2025-08-10",
            "timeline": [
                {"date": "2025-06", "label": "传闻出现", "summary": "网传固态电池突破", "tier": "T3", "is_current": False},
                {"date": "2025-08", "label": "媒体验证", "summary": "财新报道固态电池中试线投产", "tier": "T1", "is_current": True}
            ],
            "evidence": {
                "T0": [],
                "T1": [{"source": "财新网", "date": "2025-08-10", "summary": "宁德时代固态电池中试线投产，能量密度提升30%", "url": "#"}],
                "T2": [{"source": "中金公司研报", "date": "2025-08-15", "summary": "固态电池量产时间预计2027年，成本仍高", "url": "#"}],
                "T3": [{"source": "自媒体", "date": "2025-06-20", "summary": "固态电池已送样特斯拉测试", "url": "#"}]
            },
            "directions": [
                {"probability": "中高", "label": "2027年如期量产", "description": "技术路线明确，中试进展顺利", "supporting": ["中试线投产报道"], "risk": "量产成本下降速度不确定"},
                {"probability": "中", "label": "量产时间推迟", "description": "工艺复杂度超预期", "supporting": ["研报提示成本仍高"], "risk": "竞争对手抢先量产"}
            ],
            "rumors": [{"content": "已与宝马签署固态电池独家供应协议", "source": "微博", "credibility": "很低", "note": "无权威来源验证"}]
        }
    ]

    for ev in events_data:
        cursor.execute("""
            INSERT OR REPLACE INTO events
            (event_id, ticker, ticker_name, theme, headline, status, nature, nature_label,
             event_time, disclosure_time, crawl_time, updated_at,
             timeline, evidence, directions, rumors)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ev["event_id"], ev["ticker"], ev["ticker_name"], ev["theme"],
            ev["headline"], ev["status"], ev["nature"], ev["nature_label"],
            ev.get("event_time"), ev.get("disclosure_time"), ev.get("crawl_time"), ev["updated_at"],
            json.dumps(ev["timeline"], ensure_ascii=False),
            json.dumps(ev["evidence"], ensure_ascii=False),
            json.dumps(ev["directions"], ensure_ascii=False),
            json.dumps(ev["rumors"], ensure_ascii=False)
        ))

        # 插入初始版本
        cursor.execute("""
            INSERT OR REPLACE INTO event_versions
            (event_id, version, status, nature, headline, timeline_snapshot, evidence_snapshot, directions_snapshot, change_type, change_reason, created_by)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, 'update', '初始事件创建', 'seed')
        """, (
            ev["event_id"], ev["status"], ev["nature"], ev["headline"],
            json.dumps(ev["timeline"], ensure_ascii=False),
            json.dumps(ev["evidence"], ensure_ascii=False),
            json.dumps(ev["directions"], ensure_ascii=False)
        ))

        # 插入时间线节点
        for i, node in enumerate(ev["timeline"]):
            cursor.execute("""
                INSERT OR REPLACE INTO timeline_nodes
                (event_id, date, label, summary, tier, is_current, order_index)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ev["event_id"], node["date"], node["label"], node["summary"],
                node["tier"], 1 if node.get("is_current") else 0, i
            ))

        # 插入证据
        for tier_key, items in ev["evidence"].items():
            for item in items:
                cursor.execute("""
                    INSERT OR REPLACE INTO evidence_items
                    (event_id, source, date, summary, tier, source_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (ev["event_id"], item["source"], item["date"], item["summary"], tier_key, item.get("url", "")))

        # 插入方向
        for dir_item in ev["directions"]:
            cursor.execute("""
                INSERT OR REPLACE INTO event_directions
                (event_id, label, description, probability, supporting, risk)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                ev["event_id"], dir_item["label"], dir_item["description"],
                dir_item["probability"], json.dumps(dir_item["supporting"], ensure_ascii=False), dir_item["risk"]
            ))

    conn.commit()
    conn.close()
    print("[DB] Seeded 6 events.")
