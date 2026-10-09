"""
反思任务（Reflector）— 定时批处理，非 Agent
设计依据：docs/05-skills/Agent.md 第六节「反思循环」
职责：
  1. 回溯昨日/近期状态跃迁，与今日新证据比对，识别可能误判
  2. 统计各来源命中率 → 更新 source_quality 权重表
  3. 标记高争议事件（官方否认但市场仍有传闻）
  4. 触发过期检查（Rule 10/11/13）
  5. 产出校准报告

为何不做成独立 LLM Agent：
  统计与比对是确定性计算；仅"争议判定"需少量语义，用一次轻量调用即可。
  独立常驻 Agent 属过度设计，不增加效果。
"""
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import get_db, init_db
from rules import state_machine as sm


class Reflector:
    name = "Reflector"

    def run(self) -> dict:
        init_db()
        db = get_db()
        cur = db.cursor()
        now = datetime.now()
        run_date = now.strftime("%Y-%m-%d")

        report = {
            "run_date": run_date,
            "expired_transitions": [],
            "misjudged": [],
            "controversial": [],
            "source_quality": [],
        }

        # ── 1. 过期检查（Rule 10 / 11 / 13） ──
        cur.execute("SELECT event_id, state_code, last_evidence_at FROM events WHERE state_code IS NOT NULL")
        for row in cur.fetchall():
            tr = sm.check_expiry(row["state_code"], row["last_evidence_at"], now)
            if tr:
                cur.execute("""
                    UPDATE events SET state_code=?, state_label=?, status=?, updated_at=?
                    WHERE event_id=?
                """, (tr.state_code, tr.state_label, tr.card_tag, run_date, row["event_id"]))
                cur.execute("SELECT COALESCE(MAX(version),0)+1 FROM event_versions WHERE event_id=?",
                            (row["event_id"],))
                ver = cur.fetchone()[0]
                cur.execute("""
                    INSERT INTO event_versions
                    (event_id, version, status, nature, headline, timeline_snapshot, evidence_snapshot,
                     directions_snapshot, change_type, change_reason, created_by, notification_level, rule_fired)
                    VALUES (?, ?, ?, 'neutral', '', '[]', '{}', '[]', 'expire', ?, 'reflector', ?, ?)
                """, (row["event_id"], ver, tr.state_label, f"[{tr.rule_id}] {tr.reason}",
                      tr.notification_level, tr.rule_id))
                report["expired_transitions"].append({
                    "event_id": row["event_id"], "rule": tr.rule_id, "reason": tr.reason})
                if tr.notification_level:
                    self._notify(cur, row["event_id"], tr, run_date)

        # ── 2. 来源命中率统计 ──
        # 口径：某来源的证据所在事件最终未被"官方否认"，即视为该来源判断有效
        cur.execute("""
            SELECT e.source, e.tier, e.event_id, ev.state_code
            FROM evidence_items e
            LEFT JOIN events ev ON ev.event_id = e.event_id
        """)
        stats = {}
        for r in cur.fetchall():
            key = (r["source"] or "未知", r["tier"] or "T3")
            s = stats.setdefault(key, {"total": 0, "correct": 0})
            s["total"] += 1
            if r["state_code"] != sm.OFFICIALLY_DENIED:
                s["correct"] += 1

        for (source, tier), s in stats.items():
            hit = round(s["correct"] / s["total"], 4) if s["total"] else 0
            cur.execute("""
                INSERT INTO source_quality (source_name, tier, total_predictions, correct_predictions, hit_rate, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                  tier=excluded.tier, total_predictions=excluded.total_predictions,
                  correct_predictions=excluded.correct_predictions,
                  hit_rate=excluded.hit_rate, updated_at=excluded.updated_at
            """, (source, tier, s["total"], s["correct"], hit, run_date))
            report["source_quality"].append(
                {"source": source, "tier": tier, "hit_rate": hit, "total": s["total"]})

        # ── 3. 高争议事件：官方否认但仍有 T3 传闻 ──
        cur.execute("SELECT event_id, ticker_name, theme FROM events WHERE state_code = ?",
                    (sm.OFFICIALLY_DENIED,))
        for r in cur.fetchall():
            cur.execute("""
                SELECT COUNT(*) FROM evidence_items WHERE event_id = ? AND tier = 'T3'
            """, (r["event_id"],))
            if cur.fetchone()[0] > 0:
                report["controversial"].append(
                    {"event_id": r["event_id"], "ticker_name": r["ticker_name"], "theme": r["theme"]})

        # ── 4. 误判回溯：曾判 deny 但后来出现 confirm（Rule 12） ──
        cur.execute("""
            SELECT event_id, rule_fired, created_at FROM event_versions
            WHERE created_at >= ? AND change_type = 'correct'
        """, ((now - timedelta(days=7)).strftime("%Y-%m-%d"),))
        for r in cur.fetchall():
            report["misjudged"].append({"event_id": r["event_id"], "rule": r["rule_fired"]})

        # ── 5. 落库反思日志 ──
        cur.execute("""
            INSERT INTO reflection_logs (run_date, transitions_reviewed, misjudged, controversial, report_json)
            VALUES (?, ?, ?, ?, ?)
        """, (run_date, len(report["expired_transitions"]), len(report["misjudged"]),
              len(report["controversial"]), json.dumps(report, ensure_ascii=False)))

        db.commit()
        db.close()
        return report

    @staticmethod
    def _notify(cur, event_id, tr, run_date):
        cur.execute("SELECT user_id FROM event_subscriptions WHERE event_id = ?", (event_id,))
        subs = [r[0] for r in cur.fetchall()] or [1]
        for uid in subs:
            cur.execute("""
                INSERT INTO notifications (user_id, event_id, type, title, content)
                VALUES (?, ?, 'expiry', ?, ?)
            """, (uid, event_id, f"[{tr.notification_level}] {tr.state_label}", tr.reason))


if __name__ == "__main__":
    r = Reflector().run()
    print("=== 反思报告 ===")
    print(json.dumps(r, ensure_ascii=False, indent=2)[:2500])
