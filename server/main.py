from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import threading

from models import get_db, init_db
from agent import EventSentryAgent          # 参谋 Agent（对话）
from scheduler import scheduler             # 调度器（定时触发采集/反思）
from agents.collector_agent import CollectorAgent, TRACKED_TICKERS
from agents.analyst_agent import AnalystAgent
from reflector import Reflector

app = FastAPI(title="EventSentry API", version="2.2.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

init_db()

# 全局 Agent 实例（惰性初始化）
_agent = None
_collecting = {"running": False, "last": None}


def get_agent():
    global _agent
    if _agent is None:
        _agent = EventSentryAgent()
    return _agent


# ─── 基础 ───

@app.get("/api/ping")
def ping():
    import time
    return {"ok": True, "ts": time.time()}


# ─── Agent 对话（真实 LLM + 真实 iFinD 数据） ───

class ChatRequest(BaseModel):
    message: str
    history: list | None = None


@app.post("/api/chat")
def chat(req: ChatRequest):
    """
    真实 Agent 对话：
    1. LLM 理解意图并决定调用哪些 iFinD 工具
    2. 执行真实数据查询（iFinD MCP / 同花顺）
    3. LLM 基于真实数据生成回答
    返回 answer + citations（可追溯来源）
    """
    if not req.message.strip():
        raise HTTPException(400, "message is required")
    try:
        result = get_agent().run(req.message.strip(), history=req.history)
        return result
    except Exception as e:
        return {
            "answer": f"推理过程出错：{type(e).__name__}: {e}",
            "citations": [], "tools_used": [], "iterations": 0, "error": str(e),
        }


# ─── 事件（来自 iFinD 真实采集） ───

@app.get("/api/events")
def list_events(nature: str = None, status: str = None, search: str = None,
                followed: bool = False, limit: int = 50, offset: int = 0):
    conn = get_db()
    cursor = conn.cursor()

    # 已关注标的集合（用于标记 & 过滤）
    cursor.execute("SELECT ticker FROM ticker_subscriptions WHERE user_id = 1")
    followed_set = {r[0] for r in cursor.fetchall()}

    sql = "SELECT * FROM events WHERE 1=1"
    params = []
    if nature:
        sql += " AND nature = ?"
        params.append(nature)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if search:
        sql += " AND (ticker_name LIKE ? OR theme LIKE ? OR headline LIKE ? OR ticker LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like, like])
    if followed and followed_set:
        sql += f" AND ticker IN ({','.join('?' * len(followed_set))})"
        params.extend(sorted(followed_set))
    # 先统计过滤后的总数（用同一组筛选条件）
    count_sql = sql.replace("SELECT *", "SELECT COUNT(*)")
    cursor.execute(count_sql, params)
    total = cursor.fetchone()[0]

    # 状态分布（供前端筛选栏展示计数）
    cursor.execute("SELECT status, COUNT(*) FROM events GROUP BY status")
    status_counts = {r[0]: r[1] for r in cursor.fetchall()}

    sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    cursor.execute(sql, params + [limit, offset])
    rows = cursor.fetchall()
    conn.close()

    items = []
    for r in rows:
        ev = row_to_event(dict(r))
        ev["followed"] = ev["ticker"] in followed_set   # 该标的是否已关注
        items.append(ev)

    return {
        "items": items,
        "total": total,
        "status_counts": status_counts,
        "followed_tickers": sorted(followed_set),
    }


@app.get("/api/events/{event_id}")
def get_event(event_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Event not found")
    return row_to_event(dict(row))


@app.get("/api/events/{event_id}/timeline")
def get_timeline(event_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM timeline_nodes WHERE event_id = ? ORDER BY order_index", (event_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/events/{event_id}/evidence")
def get_evidence(event_id: str, tier: str = None):
    conn = get_db()
    cursor = conn.cursor()
    sql = "SELECT * FROM evidence_items WHERE event_id = ?"
    params = [event_id]
    if tier:
        sql += " AND tier = ?"
        params.append(tier)
    sql += " ORDER BY date DESC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/events/{event_id}/directions")
def get_directions(event_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM event_directions WHERE event_id = ?", (event_id,))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["supporting"] = json.loads(d.get("supporting", "[]") or "[]")
        result.append(d)
    return result


@app.get("/api/events/{event_id}/versions")
def get_versions(event_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM event_versions WHERE event_id = ? ORDER BY version DESC", (event_id,))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        for key in ["timeline_snapshot", "evidence_snapshot", "directions_snapshot"]:
            try:
                d[key] = json.loads(d.get(key, "[]") or "[]")
            except Exception:
                d[key] = []
        result.append(d)
    return result


# ─── 采集控制（真实拉取 iFinD 数据） ───

# ─── 流水线控制（采集 Agent → 分析 Agent） ───

class PipelineRequest(BaseModel):
    days: int = 30


@app.post("/api/pipeline/run")
def run_pipeline(req: PipelineRequest = None):
    """手动触发完整流水线：采集 Agent → 分析 Agent"""
    if scheduler.state["collector"]["running"]:
        return {"ok": False, "message": "流水线正在运行中"}

    days = req.days if req else 30

    def _run():
        from agents.collector_agent import CollectorAgent as CA
        from agents.analyst_agent import AnalystAgent as AA
        from media_search_collector import MediaSearchCollector
        scheduler.state["collector"]["running"] = True
        try:
            cres = CA().collect(days=days)
            # 媒体 / 传闻层（T1/T2/T3）
            mres = {}
            if os.getenv("ENABLE_MEDIA_SEARCH", "1") == "1":
                try:
                    mres = MediaSearchCollector().collect(days=max(days, 180))
                except Exception as e:
                    print(f"[Pipeline] 媒体搜索失败: {str(e)[:120]}")
            scheduler.state["collector"]["last_run"] = __import__("datetime").datetime.now().isoformat()
            scheduler.state["collector"]["last_result"] = {"ifind": cres, "websearch": mres}
            scheduler.state["analyst"]["running"] = True
            ares = AA().process_batch(limit=60)
            scheduler.state["analyst"]["last_run"] = __import__("datetime").datetime.now().isoformat()
            scheduler.state["analyst"]["last_result"] = ares
        finally:
            scheduler.state["collector"]["running"] = False
            scheduler.state["analyst"]["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": f"已启动流水线（回溯 {days} 天）"}


@app.post("/api/reflect/run")
def run_reflect():
    """手动触发反思任务"""
    def _run():
        Reflector().run()
    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "已启动反思任务"}


@app.get("/api/agents/status")
def agents_status():
    """多 Agent 运行状态"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM events")
    events = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM evidence_items")
    evidence = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM raw_messages")
    raw = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM raw_messages WHERE processed = 0")
    pending = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM event_versions")
    versions = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM notifications")
    notifs = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM source_quality")
    sources = cursor.fetchone()[0]
    cursor.execute("SELECT MAX(created_at) FROM events")
    last = cursor.fetchone()[0]
    conn.close()

    return {
        "agents": {
            "Collector": {
                "model": "glm-4-flash（不可用时降级 glm-4.6）",
                "role": "抓取 iFinD 原始消息 / 去重 / 要素预抽取",
                "schedule": "每 30 分钟",
                **scheduler.state["collector"],
            },
            "Analyst": {
                "model": "glm-4.6",
                "role": "语义分析 / 聚类 / 事实观点传闻区分 / 规则裁决 / 卡片生成",
                "schedule": "采集后触发 + 事件驱动",
                **scheduler.state["analyst"],
            },
            "Conversation": {
                "model": "glm-4.6",
                "role": "参谋对话（工具调用）",
                "schedule": "实时",
                "running": False, "last_run": None, "last_result": None,
            },
            "Reflector": {
                "model": "无（确定性统计）",
                "role": "命中率校准 / 争议标记 / 过期检查",
                "schedule": "每日 02:00",
                **scheduler.state["reflector"],
            },
        },
        "data": {
            "events": events, "evidence": evidence, "versions": versions,
            "raw_messages": raw, "pending_messages": pending,
            "notifications": notifs, "sources_tracked": sources,
            "last_updated": last,
        },
        "tracked": [{"name": n, "code": c} for n, c in TRACKED_TICKERS],
    }


@app.get("/api/collect/status")
def collect_status():
    """兼容旧接口"""
    return agents_status()


# ─── 用户 ───

@app.get("/api/me")
def get_me():
    return {"id": 1, "name": "测试用户", "role": "user", "avatar": None}


@app.get("/api/holdings")
def get_holdings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM holdings WHERE user_id = 1 ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/holdings")
def create_holding(body: dict):
    """添加持仓 —— 同时自动「关注该标的」，后续该标的的新事件会进发现页"""
    conn = get_db()
    cursor = conn.cursor()
    ticker = body["ticker"]
    ticker_name = body["ticker_name"]

    cursor.execute(
        "INSERT INTO holdings (user_id, ticker, ticker_name, cost_price) VALUES (1, ?, ?, ?)",
        (ticker, ticker_name, body.get("cost_price")))
    new_id = cursor.lastrowid

    # 自动关注该标的（幂等）
    cursor.execute(
        "INSERT OR IGNORE INTO ticker_subscriptions (user_id, ticker, ticker_name) VALUES (1, ?, ?)",
        (ticker, ticker_name))
    newly_followed = cursor.rowcount > 0

    # 统计该标的当前有多少事件（用于提示语）
    cursor.execute("SELECT COUNT(*) FROM events WHERE ticker = ?", (ticker,))
    event_count = cursor.fetchone()[0]

    conn.commit()
    conn.close()
    return {
        "id": new_id,
        "ticker": ticker,
        "ticker_name": ticker_name,
        "followed": True,
        "newly_followed": newly_followed,
        "event_count": event_count,
    }


@app.get("/api/tickers")
def get_followed_tickers():
    """已关注标的列表"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ticker, ticker_name, created_at FROM ticker_subscriptions
        WHERE user_id = 1 ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@app.delete("/api/holdings/{holding_id}")
def delete_holding(holding_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM holdings WHERE id = ? AND user_id = 1", (holding_id,))
    conn.commit()
    conn.close()
    return {"success": True}


# ─── 订阅 ───

@app.get("/api/subscriptions")
def get_subscriptions():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT event_id FROM event_subscriptions WHERE user_id = 1")
    rows = cursor.fetchall()
    conn.close()
    return [r["event_id"] for r in rows]


@app.get("/api/subscriptions/events")
def get_subscribed_events():
    """返回已订阅事件的完整信息 + 关注股票数（供「我的」页展示）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.* FROM events e
        JOIN event_subscriptions s ON s.event_id = e.event_id
        WHERE s.user_id = 1
        ORDER BY e.updated_at DESC
    """)
    rows = cursor.fetchall()
    items = [row_to_event(dict(r)) for r in rows]

    # 关注股票 = 订阅事件涉及的**去重标的** ∪ 自选持仓标的
    tickers = {e["ticker"] for e in items}
    cursor.execute("SELECT DISTINCT ticker FROM holdings WHERE user_id = 1")
    tickers |= {r[0] for r in cursor.fetchall()}

    conn.close()
    return {
        "items": items,
        "total": len(items),
        "ticker_count": len(tickers),
    }


@app.post("/api/subscriptions")
def subscribe_event(body: dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO event_subscriptions (user_id, event_id) VALUES (1, ?)",
                   (body.get("event_id"),))
    conn.commit()
    conn.close()
    return {"success": True, "event_id": body.get("event_id")}


@app.delete("/api/subscriptions/{event_id}")
def unsubscribe_event(event_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM event_subscriptions WHERE user_id = 1 AND event_id = ?", (event_id,))
    conn.commit()
    conn.close()
    return {"success": True}


# ─── 偏好 ───

@app.get("/api/preferences")
def get_preferences():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_preferences WHERE user_id = 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {"user_id": 1, "risk_level": "moderate", "notification_enabled": 1}


@app.post("/api/preferences")
def update_preferences(body: dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_preferences (user_id, risk_level, notification_enabled)
        VALUES (1, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
        risk_level = excluded.risk_level, notification_enabled = excluded.notification_enabled
    """, (body.get("risk_level", "moderate"), 1 if body.get("notification_enabled") else 0))
    conn.commit()
    conn.close()
    return {"success": True}


# ─── 通知 ───

@app.get("/api/notifications")
def get_notifications(unread_only: bool = False):
    """
    通知中心 —— 只返回与用户**订阅事件**或**关注/持仓标的**相关的通知。
    与用户无关的推送不展示（避免噪音）。
    """
    conn = get_db()
    cursor = conn.cursor()
    sql = """
        SELECT n.* FROM notifications n
        WHERE n.user_id = 1
          AND (
            EXISTS (SELECT 1 FROM event_subscriptions s
                    WHERE s.user_id = 1 AND s.event_id = n.event_id)
            OR EXISTS (SELECT 1 FROM events e
                       WHERE e.event_id = n.event_id
                         AND (
                           EXISTS (SELECT 1 FROM ticker_subscriptions t
                                   WHERE t.user_id = 1 AND t.ticker = e.ticker)
                           OR EXISTS (SELECT 1 FROM holdings h
                                      WHERE h.user_id = 1 AND h.ticker = e.ticker)
                         ))
          )
    """
    if unread_only:
        sql += " AND n.read = 0"
    sql += " ORDER BY n.created_at DESC"
    cursor.execute(sql)
    rows = cursor.fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    return {"list": items, "unread_count": sum(1 for r in items if not r["read"])}


@app.post("/api/notifications/{notif_id}/read")
def mark_read(notif_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET read = 1 WHERE id = ? AND user_id = 1", (notif_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.post("/api/notifications/read-all")
def mark_all_read():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET read = 1 WHERE user_id = 1")
    conn.commit()
    conn.close()
    return {"success": True}


# ─── 辅助 ───

def row_to_event(row: dict) -> dict:
    return {
        "id": row["event_id"],
        "ticker": row["ticker"],
        "ticker_name": row["ticker_name"],
        "theme": row["theme"],
        "headline": row["headline"],
        "status": row["status"],
        "nature": row["nature"],
        "nature_label": row["nature_label"],
        "event_time": row.get("event_time"),
        "disclosure_time": row.get("disclosure_time"),
        "crawl_time": row.get("crawl_time"),
        "updated_at": row["updated_at"],
        "timeline": _safe_json(row.get("timeline"), []),
        "evidence": _safe_json(row.get("evidence"), {}),
        "directions": _safe_json(row.get("directions"), []),
        "rumors": _safe_json(row.get("rumors"), []),
    }


def _safe_json(v, default):
    try:
        return json.loads(v) if v else default
    except Exception:
        return default


# ─── 静态文件 ───
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/", StaticFiles(directory=static_path, html=True), name="static")

@app.on_event("startup")
def _start_scheduler():
    if os.getenv("ENABLE_SCHEDULER", "1") == "1":
        scheduler.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3000, reload=False)
