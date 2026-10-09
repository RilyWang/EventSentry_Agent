"""
清理「非法 event_id」产生的脏数据

背景：分析 Agent 早期版本直接采信 LLM 聚类返回的 event_id，
      而 LLM 偶尔返回纯数字（如 "276"），导致生成 event_id 为纯数字的脏事件。
      修复后 Agent 已会校验 event_id 合法性；本脚本清理历史脏数据。

安全措施：使用 GLOB 精确匹配「全部字符均为数字」的 event_id，
         不使用 SQL LIKE（其 `_`/`%` 是通配符，曾导致误删事故）。
可重复运行（幂等）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import get_db, init_db

# 正常 event_id 形如 300750_SZ_股份回购 —— 必含字母/下划线/中文
# 脏数据 = 全部字符都是数字
NUMERIC_ID = "event_id GLOB '[0-9]*' AND event_id NOT GLOB '*[^0-9]*'"


def run(dry_run: bool = False):
    init_db()
    db = get_db()
    cur = db.cursor()

    # 先取出待清理的 id 列表（用于关联表清理）
    cur.execute(f"SELECT event_id FROM events WHERE {NUMERIC_ID}")
    bad_ids = [r["event_id"] for r in cur.fetchall()]

    if not bad_ids:
        print("未发现非法 event_id，无需清理 ✅")
        db.close()
        return {"events": 0}

    print(f"发现非法 event_id 事件: {len(bad_ids)} 个")
    print(f"  样例: {bad_ids[:8]}")

    counts = {}
    placeholders = ",".join("?" * len(bad_ids))

    for tbl in ["event_versions", "timeline_nodes", "evidence_items",
                "event_directions", "notifications", "event_subscriptions"]:
        cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE event_id IN ({placeholders})", bad_ids)
        counts[tbl] = cur.fetchone()[0]

    if dry_run:
        print("\n[DRY RUN] 将删除：")
        for k, v in counts.items():
            print(f"  {k}: {v}")
        print(f"  events: {len(bad_ids)}")
        db.close()
        return counts

    for tbl in ["event_versions", "timeline_nodes", "evidence_items",
                "event_directions", "notifications", "event_subscriptions"]:
        cur.execute(f"DELETE FROM {tbl} WHERE event_id IN ({placeholders})", bad_ids)
    cur.execute(f"DELETE FROM events WHERE {NUMERIC_ID}")
    db.commit()

    print("\n已清理：")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"  events: {len(bad_ids)}")

    # 复查
    cur.execute(f"SELECT COUNT(*) FROM events WHERE {NUMERIC_ID}")
    left = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM events")
    total = cur.fetchone()[0]
    print(f"\n复查：脏事件残留 {left} | 剩余事件 {total}")
    db.close()
    return counts


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
