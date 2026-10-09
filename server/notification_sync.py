"""
通知同步 —— 按「用户订阅事件 ∪ 持仓/关注标的」重建通知

背景：早期 _notify 在无人订阅时会默认推给用户 1，产生大量无关通知。
本脚本：
  1. 删除与用户订阅/持仓无关的通知
  2. 从 event_versions 版本历史重建相关通知（每条跃迁一条）
     —— 与状态机的通知分级（P0/P1/P2）保持一致
可重复运行（幂等：按 event_id + version 去重）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import get_db, init_db

USER_ID = 1

# 需要通知的跃迁类型 → 通知类型
NOTIF_OF_CHANGE = {
    "deny": "denial",
    "correct": "correction",
    "expire": "expiry",
    "update": "state_transition",
}


def relevant_events(cur):
    """用户关心的标的对应的事件 id 集合"""
    cur.execute("SELECT ticker FROM ticker_subscriptions WHERE user_id = ?", (USER_ID,))
    tickers = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT ticker FROM holdings WHERE user_id = ?", (USER_ID,))
    tickers |= {r[0] for r in cur.fetchall()}

    cur.execute("SELECT event_id FROM event_subscriptions WHERE user_id = ?", (USER_ID,))
    events = {r[0] for r in cur.fetchall()}

    if tickers:
        q = f"SELECT event_id FROM events WHERE ticker IN ({','.join('?' * len(tickers))})"
        cur.execute(q, sorted(tickers))
        events |= {r[0] for r in cur.fetchall()}
    return events, tickers


def run():
    init_db()
    db = get_db()
    cur = db.cursor()

    events, tickers = relevant_events(cur)
    print(f"用户关心的标的: {sorted(tickers) or '无'}")
    print(f"用户关心的事件: {len(events)} 个")

    # ─── 1. 删除无关通知 ───
    cur.execute("SELECT id, event_id FROM notifications WHERE user_id = ?", (USER_ID,))
    all_notifs = cur.fetchall()
    to_delete = [n["id"] for n in all_notifs if n["event_id"] not in events]
    if to_delete:
        cur.execute(
            f"DELETE FROM notifications WHERE id IN ({','.join('?' * len(to_delete))})",
            to_delete)
    print(f"删除无关通知: {len(to_delete)} 条（保留 {len(all_notifs) - len(to_delete)} 条）")

    # ─── 2. 从版本历史重建相关通知 ───
    created = 0
    for eid in sorted(events):
        # 已有通知的 version（幂等去重靠 event_id+title 近似）
        cur.execute("SELECT title, content FROM notifications WHERE user_id = ? AND event_id = ?",
                    (USER_ID, eid))
        existing = {(r["title"], r["content"]) for r in cur.fetchall()}

        cur.execute("""
            SELECT version, status, change_type, rule_fired, notification_level, change_reason
            FROM event_versions WHERE event_id = ? ORDER BY version ASC
        """, (eid,))
        for v in cursor_rows(cur):
            lvl = v["notification_level"]
            if not lvl:
                continue
            title = f"[{lvl}] {v['status']}"
            content = f"{v['rule_fired'] or '——'}：{v['change_reason'] or ''}"
            if (title, content) in existing:
                continue
            cur.execute("""
                INSERT INTO notifications (user_id, event_id, type, title, content)
                VALUES (?, ?, ?, ?, ?)
            """, (USER_ID, eid,
                  NOTIF_OF_CHANGE.get(v["change_type"], "state_transition"),
                  title, content[:300]))
            created += 1

    db.commit()

    # ─── 3. 汇总 ───
    cur.execute("""
        SELECT COUNT(*) FROM notifications n WHERE n.user_id = 1
          AND (EXISTS (SELECT 1 FROM event_subscriptions s WHERE s.user_id=1 AND s.event_id=n.event_id)
            OR EXISTS (SELECT 1 FROM events e WHERE e.event_id=n.event_id
                       AND (EXISTS (SELECT 1 FROM ticker_subscriptions t WHERE t.user_id=1 AND t.ticker=e.ticker)
                         OR EXISTS (SELECT 1 FROM holdings h WHERE h.user_id=1 AND h.ticker=e.ticker))))
    """)
    total = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM notifications n WHERE n.user_id = 1 AND n.read = 0
          AND (EXISTS (SELECT 1 FROM event_subscriptions s WHERE s.user_id=1 AND s.event_id=n.event_id)
            OR EXISTS (SELECT 1 FROM events e WHERE e.event_id=n.event_id
                       AND (EXISTS (SELECT 1 FROM ticker_subscriptions t WHERE t.user_id=1 AND t.ticker=e.ticker)
                         OR EXISTS (SELECT 1 FROM holdings h WHERE h.user_id=1 AND h.ticker=e.ticker))))
    """)
    unread = cur.fetchone()[0]

    print(f"新建通知: {created} 条")
    print(f"最终：相关通知 {total} 条（未读 {unread}）")
    db.close()
    return {"total": total, "unread": unread, "created": created, "deleted": len(to_delete)}


def cursor_rows(cur):
    return cur.fetchall()


if __name__ == "__main__":
    run()
