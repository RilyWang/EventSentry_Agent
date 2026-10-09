"""只读检查脚本 —— 严禁任何 DELETE/UPDATE（上一次误删事件就是因为此脚本含 DELETE + LIKE 通配符）"""
import os
os.environ["no_proxy"] = "*"
from models import get_db

db = get_db()
c = db.cursor()

c.execute("SELECT event_id, ticker_name, theme, state_code, status, confidence FROM events ORDER BY updated_at DESC")
print("=== 事件列表 ===")
rows = c.fetchall()
for r in rows:
    print(f"  {r['event_id']:30} | {r['ticker_name']:6} | {r['theme']:8} | {r['state_code']} | {r['confidence']}")
print(f"  合计 {len(rows)} 个事件")

c.execute("SELECT evidence_type, COUNT(*) FROM evidence_items GROUP BY evidence_type")
print("\n证据类型分布:", [(r[0], r[1]) for r in c.fetchall()])

c.execute("SELECT tier, COUNT(*) FROM evidence_items GROUP BY tier")
print("证据层级分布:", [(r[0], r[1]) for r in c.fetchall()])

c.execute("SELECT COUNT(*) FROM raw_messages")
raw = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM raw_messages WHERE processed=0")
pending = c.fetchone()[0]
print(f"\n原始消息: {raw}（待处理 {pending}）")

c.execute("SELECT event_id, version, change_type, rule_fired FROM event_versions ORDER BY id DESC LIMIT 10")
print("\n=== 版本快照（最近10条）===")
for r in c.fetchall():
    print(f"  {r[0]:30} v{r[1]} | {r[2]:8} | {r[3]}")

c.execute("SELECT COUNT(*) FROM notifications")
print("\n通知数:", c.fetchone()[0])

db.close()
