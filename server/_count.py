import os, json
os.environ["no_proxy"] = "*"
from models import get_db
db = get_db(); c = db.cursor()
for t in ["events","raw_messages","evidence_items","event_versions","notifications"]:
    c.execute(f"SELECT COUNT(*) FROM {t}"); print(f"{t}: {c.fetchone()[0]}")
c.execute("SELECT status, COUNT(*) FROM events GROUP BY status ORDER BY 2 DESC")
print("状态:", json.dumps({r[0]: r[1] for r in c.fetchall()}, ensure_ascii=False))
db.close()
