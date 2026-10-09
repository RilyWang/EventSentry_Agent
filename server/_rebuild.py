"""清空事件层，保留原始消息，重置为待处理，供流水线重建"""
import os
os.environ["no_proxy"] = "*"
from models import get_db

db = get_db()
c = db.cursor()

c.execute("SELECT COUNT(*) FROM raw_messages")
before = c.fetchone()[0]

c.execute("DELETE FROM events")
c.execute("DELETE FROM event_versions")
c.execute("DELETE FROM timeline_nodes")
c.execute("DELETE FROM evidence_items")
c.execute("DELETE FROM notifications")
c.execute("UPDATE raw_messages SET processed = 0, assigned_event_id = NULL")

db.commit()

c.execute("SELECT COUNT(*) FROM raw_messages")
after = c.fetchone()[0]
db.close()

print(f"原始消息: {before} -> {after}（保留，重置为待处理）")
print("事件层已清空，可重新运行分析 Agent 重建")
