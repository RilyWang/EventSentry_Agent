"""
分析 Agent（Analyst）— 核心语义判断 Agent
模型：GLM-4.6（强模型）
职责：
  1. 消息语义分析（主题 / 事实-观点-推测-传闻区分 / 确认-否认-落地语义 / 来源分级）
  2. 同一事件聚类（判断消息归属哪个已有事件，或新建事件）
  3. 卡片生成（headline / 方向 / 风险 / 置信度）
  4. 调用规则层做状态裁决（LLM 只"看懂"，裁决交给规则）
  5. 版本快照 + 合规扫描 + 通知触发

边界：本 Agent 不做状态裁决、不做合规判定 —— 这两件事由 rules/ 层的确定性代码负责。
"""
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_client import LLMClient
from models import get_db, init_db
from rules import state_machine as sm
from rules import compliance
from rules import evidence_analysis as ea

# 「更正公告」的确定性识别（LLM 漏判时的兜底，也用于状态机 Rule 12）。
# 只认明确措辞：更正公告 / 更正说明 / 补充更正 / 更正并致歉。
# 刻意不匹配「修订《公司章程》」——那是常规治理事项，不是对既有结论的更正。
CORRECTION_PAT = re.compile(r"(更正公告|更正说明|补充更正|更正并致歉)")


def _extract_json(text: str):
    """从 LLM 回复中稳健提取 JSON（容忍 markdown 代码围栏 / 前后缀）"""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    # 找第一个 { 或 [
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        i = t.find(open_ch)
        j = t.rfind(close_ch)
        if i >= 0 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                continue
    try:
        return json.loads(t)
    except Exception:
        return None


# 规范化主题表 —— 强制收敛，避免同一事件被拆成"一季报/二季报/中期公告"多条
CANONICAL_THEMES = [
    "定期报告", "业绩预告", "并购重组", "股份回购", "分红派息",
    "股东增减持", "股权激励", "对外担保", "战略合作", "重大合同订单",
    "产能扩张", "技术进展", "销量数据", "监管问询", "公司治理",
    "ESG", "投资者关系", "融资行动", "其他经营动态",
]

ANALYZE_SYSTEM = f"""你是投资事件情报分析员。你的任务是从原始消息中提取结构化要素。

对每条消息，输出以下字段：
- theme: 事件主题。**必须从下列规范主题表中选一个最贴切的**（不要自创）：
  {json.dumps(CANONICAL_THEMES, ensure_ascii=False)}
  例如：年报/半年报/季报/中期报告 → "定期报告"；收购/重组/股权转让 → "并购重组"；
  增持/减持 → "股东增减持"；董事会/章程修订 → "公司治理"。
- evidence_type: 证据类型，取值 fact(事实陈述) / opinion(观点判断) / speculation(推测) / rumor(传闻)
  * 公司公告、交易所披露 → fact
  * 券商研报、分析师观点 → opinion
  * "可能""预计""有望"等推断 → speculation
  * 股吧、传言、匿名爆料、无来源的说法 → rumor
- semantics: 对事件状态的作用，取值 confirm(确认) / deny(否认) / substance(实质落地) / correct(更正) / neutral(中性补充)
  * 公司公告披露 → confirm
  * 明确否认/澄清"不存在" → deny
  * 合同签署、产品上线、业绩兑现等实质结果 → substance
  * **明确写有"更正公告""补充更正"的公告（修正此前已披露口径）→ correct**
    （注意：仅"修订《公司章程》"不属于更正，应归为 neutral）
  * 其他补充信息 → neutral
- tier: 来源层级 T0(公司公告/监管) / T1(权威媒体) / T2(研报) / T3(传闻)
- event_time: 消息中提到的"事件实际发生日期"(YYYY-MM-DD)，没有则 null

只输出 JSON 数组，不要任何解释文字。格式：
[{{"id":1,"theme":"定期报告","evidence_type":"fact","semantics":"confirm","tier":"T0","event_time":null}}]"""

# 保留旧变量名兼容（未使用规范表的场景）
_LEGACY_ANALYZE_SYSTEM = """你是投资事件情报分析员。你的任务是从原始消息中提取结构化要素。

对每条消息，输出以下字段：
- theme: 事件主题（4-8字，如"股份回购""储能扩张""业绩预告"）
- evidence_type: 证据类型，取值 fact(事实陈述) / opinion(观点判断) / speculation(推测) / rumor(传闻)
  * 公司公告、交易所披露 → fact
  * 券商研报、分析师观点 → opinion
  * "可能""预计""有望"等推断 → speculation
  * 股吧、传言、匿名爆料、无来源的说法 → rumor
- semantics: 对事件状态的作用，取值 confirm(确认) / deny(否认) / substance(实质落地) / neutral(中性补充)
  * 明确证实某事存在 → confirm
  * 明确否认/澄清"不存在"→ deny
  * 合同签署、产品上线、业绩兑现等实质结果 → substance
  * 其他补充信息 → neutral
- tier: 来源层级 T0(公司公告/监管) / T1(权威媒体) / T2(研报) / T3(传闻)
- event_time: 消息中提到的"事件实际发生日期"(YYYY-MM-DD)，没有则 null

只输出 JSON 数组，不要任何解释文字。格式：
[{"id":1,"theme":"...","evidence_type":"...","semantics":"...","tier":"...","event_time":null}]"""

CLUSTER_SYSTEM = f"""你是事件聚类分析员。判断消息是否属于已有事件。

**核心原则：优先归入已有事件，避免过度拆分。**
判断标准：同一标的 + 同一主题 = 同一事件。
- 主题已在"已有事件"列表中出现（哪怕是同义表述）→ **必须归入该事件**（assign="existing"）
  例：已有"定期报告"，新消息是"一季报/二季报/中期报告" → 全部归入"定期报告"
  例：已有"并购重组"，新消息是"收购剩余股权/重组审核/重组核查" → 全部归入"并购重组"
- 只有当主题在已有事件中**完全不存在**时，才新建（assign="new"）
- 新事件的 theme 也必须从规范主题表中选：
  {json.dumps(CANONICAL_THEMES, ensure_ascii=False)}
- 主题偏移（如"收购A公司"vs"收购B公司"且已有事件就是A）才需拆分

只输出 JSON 数组，不要解释。格式：
[{{"id":1,"assign":"existing","event_id":"已有的event_id"}}] 或
[{{"id":1,"assign":"new","theme":"新事件主题"}}]"""

CARD_SYSTEM = """你是投资事件情报分析师，为事件生成"判断卡片"。要求：

- headline: 一句话概括（≤50字），格式"核心动作 + 关键结论"，不含投资建议
- nature: positive(利好) / negative(利空) / neutral(中性) / risk(风险)
- risk_note: 主要风险点（≤40字）
- focus_node: 建议关注的下一个节点（≤30字），若无可填 null
- confidence: 高 / 中高 / 中 / 低
- confidence_reason: 置信度理由（≤50字），须说明有几条什么层级的证据
- directions: 2-3 个可能的演化方向，每个含
    - probability: 只能是 高 / 中高 / 中 / 中低 / 低
    - label: 方向标题（≤15字）
    - description: 方向描述（≤50字）
    - supporting: 支撑依据数组
    - risk: 该方向的风险点

【严格禁止】出现"买入/卖出/加仓/减仓/目标价/必涨/稳赚"等词；禁止精确百分比（如"80%概率"），概率只用"高/中/低"。

只输出 JSON 对象，不要解释。"""


class AnalystAgent:
    name = "Analyst"

    def __init__(self, model: str = None):
        self.llm = LLMClient(model=model or "glm-4.6")

    # ═══ 主入口：消费未处理消息 ═══
    def process_batch(self, limit: int = 40) -> dict:
        init_db()
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            SELECT * FROM raw_messages WHERE processed = 0
            ORDER BY publish_time ASC LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            db.close()
            return {"processed": 0, "events_touched": 0, "transitions": [], "message": "无未处理消息"}

        # 按标的分组
        by_ticker = {}
        for r in rows:
            by_ticker.setdefault(r["ticker"], []).append(r)

        total_transitions = []
        events_touched = set()

        failed_tickers = set()
        for ticker, msgs in by_ticker.items():
            try:
                result = self._process_ticker(cur, ticker, msgs)
                total_transitions.extend(result["transitions"])
                events_touched.update(result["events"])
                db.commit()   # 每个标的处理完即提交，释放锁
            except Exception as e:
                print(f"[Analyst] {ticker} 处理失败: {type(e).__name__}: {e}")
                db.rollback()
                failed_tickers.add(ticker)   # 失败标的的消息不标记为已处理，留待下轮重试
                continue

        # 仅标记**成功处理**的标的的消息
        ids = [r["id"] for r in rows if r["ticker"] not in failed_tickers]
        if ids:
            cur.execute(
                f"UPDATE raw_messages SET processed = 1 WHERE id IN ({','.join('?' * len(ids))})", ids)
        db.commit()
        db.close()

        return {
            "processed": len(rows),
            "events_touched": len(events_touched),
            "transitions": total_transitions,
        }

    def _process_ticker(self, cur, ticker: str, msgs: list) -> dict:
        ticker_name = msgs[0].get("ticker_name") or ticker

        # ── 1. LLM 语义分析（每条消息） ──
        analyzed = self._analyze_messages(ticker_name, msgs)

        # ── 2. 拉取已有事件，LLM 聚类 ──
        existing = self._load_existing_events(cur, ticker)
        assignments = self._assign_events(ticker_name, analyzed, existing)

        # ── 3. 按事件归组 ──
        # 合法 event_id 集合 —— LLM 可能返回非法值（如行号 "276"），必须校验后再用
        valid_ids = {e["event_id"] for e in existing}
        groups = {}   # event_id -> list of analyzed msg
        for a in analyzed:
            asg = next((x for x in assignments if x.get("id") == a["id"]), None)
            if not asg:
                # LLM 漏项时**不能静默丢弃**：这些消息随后会被整体标记 processed=1，
                # 丢弃即永久丢失且不可重试。兜底按主题新建事件，保证"零丢失"。
                theme = a.get("theme") or "公司动态"
                a["_new_theme"] = theme
                groups.setdefault(self._make_event_id(ticker, theme), []).append(a)
                continue
            claimed = asg.get("event_id")
            if asg.get("assign") == "existing" and claimed in valid_ids:
                groups.setdefault(claimed, []).append(a)
            else:
                # LLM 返回的 event_id 非法（或本就要求新建）→ 按规范主题新建事件
                if asg.get("assign") == "existing" and claimed not in valid_ids:
                    print(f"[Analyst] 忽略非法 event_id={claimed!r}（{ticker_name}），改为新建事件")
                theme = asg.get("theme") or a.get("theme") or "公司动态"
                eid = self._make_event_id(ticker, theme)
                a["_new_theme"] = theme
                groups.setdefault(eid, []).append(a)

        # ── 4. 每个事件：规则裁决 + 卡片生成 + 落库 ──
        transitions = []
        touched = []
        for eid, items in groups.items():
            try:
                t = self._process_event(cur, ticker, ticker_name, eid, items)
                touched.append(eid)
                if t:
                    transitions.append(t)
            except Exception as e:
                print(f"[Analyst] 事件 {eid} 失败: {type(e).__name__}: {e}")

        return {"transitions": transitions, "events": touched}

    # ═══ 步骤 1：语义分析 ═══
    def _analyze_messages(self, ticker_name: str, msgs: list) -> list:
        payload = [
            {"id": m["id"], "title": m["title"], "content": (m["content"] or "")[:300],
             "source": m["source"], "source_type": m["source_type"]}
            for m in msgs
        ]
        user = f"标的：{ticker_name}\n\n待分析消息：\n{json.dumps(payload, ensure_ascii=False)}"
        try:
            resp = self.llm.chat([{"role": "user", "content": user}],
                                 system=ANALYZE_SYSTEM, max_tokens=3000, temperature=0.1, thinking=False)
            arr = _extract_json(LLMClient.extract_text(resp)) or []
            # LLM 偶尔返回字符串数组，过滤掉非 dict 元素
            arr = [x for x in arr if isinstance(x, dict)]
        except Exception as e:
            print(f"[Analyst] 语义分析失败: {e}")
            arr = []

        # 合并回原始消息（LLM 漏项时用规则兜底）
        out = []
        for m in msgs:
            hit = next((x for x in arr if x.get("id") == m["id"]), None) or {}
            out.append({
                "id": m["id"],
                "ticker": m["ticker"],
                "ticker_name": ticker_name,
                "title": m["title"],
                "content": m["content"],
                "source": m["source"],
                "source_type": m["source_type"],
                "source_url": m.get("source_url"),
                "publish_time": m["publish_time"],
                "theme": hit.get("theme") or self._rule_theme(m["title"]),
                "evidence_type": hit.get("evidence_type") or self._rule_evidence_type(m),
                "semantics": hit.get("semantics") or self._rule_semantics(m["title"]),
                "tier": hit.get("tier") or m.get("source_tier") or "T1",
                "event_time": hit.get("event_time"),
            })
        return out

    # ═══ 步骤 2：聚类 ═══
    def _assign_events(self, ticker_name: str, analyzed: list, existing: list) -> list:
        ex_brief = [{"event_id": e["event_id"], "theme": e["theme"], "status": e["status"],
                     "headline": (e["headline"] or "")[:60]} for e in existing]
        msgs_brief = [{"id": a["id"], "theme": a["theme"], "title": a["title"][:80]} for a in analyzed]
        user = (f"标的：{ticker_name}\n\n已有事件：\n{json.dumps(ex_brief, ensure_ascii=False)}\n\n"
                f"新消息：\n{json.dumps(msgs_brief, ensure_ascii=False)}")
        try:
            resp = self.llm.chat([{"role": "user", "content": user}],
                                 system=CLUSTER_SYSTEM, max_tokens=1500, temperature=0.1, thinking=False)
            arr = _extract_json(LLMClient.extract_text(resp)) or []
            arr = [x for x in arr if isinstance(x, dict)]
        except Exception as e:
            print(f"[Analyst] 聚类失败: {e}")
            arr = []
        if not arr:
            # 兜底：全部按主题新建
            arr = [{"id": a["id"], "assign": "new", "theme": a["theme"]} for a in analyzed]
        return arr

    # ═══ 步骤 4：单事件处理（裁决 + 卡片 + 落库） ═══
    def _process_event(self, cur, ticker, ticker_name, eid, items) -> dict:
        cur.execute("SELECT * FROM events WHERE event_id = ?", (eid,))
        row = cur.fetchone()
        existing = dict(row) if row else None
        theme = items[0].get("_new_theme") or (existing["theme"] if existing else items[0]["theme"])

        # 新证据 → Evidence 对象（供规则层）
        evidences = [
            sm.Evidence(
                tier=a["tier"], semantics=a["semantics"], evidence_type=a["evidence_type"],
                publish_time=a["publish_time"] or "", source=a["source"], summary=a["title"],
            ) for a in items
        ]

        # last_evidence_at 必须单调递增：取「历史值」与「本批最大值」中的较大者，
        # 否则一批旧消息会把时间拉回过去，导致 Rule 10/11 误判过期。
        batch_last = max((a["publish_time"] or "" for a in items), default="")
        prev_last = (existing or {}).get("last_evidence_at") or ""
        last_at = max(batch_last, prev_last)
        cur_state = existing.get("state_code") if existing else None

        # ★ 规则层裁决（确定性）
        tr = sm.arbitrate(cur_state, evidences, last_evidence_at=last_at)

        # ── 写证据（含类型）—— 按 raw_message_id 去重，支持安全重跑 ──
        for a in items:
            cur.execute(
                "SELECT 1 FROM evidence_items WHERE event_id = ? AND raw_message_id = ?",
                (eid, a["id"]))
            if cur.fetchone():
                continue
            cur.execute("""
                INSERT INTO evidence_items
                (event_id, source, date, summary, tier, evidence_type, credibility_score,
                 source_url, raw_message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (eid, a["source"], a["publish_time"], a["title"][:200],
                  a["tier"], a["evidence_type"],
                  ea.evidence_weight(a["tier"], a["evidence_type"]),
                  a.get("source_url") or "#", a["id"]))

        # ── 时间线节点 ──
        cur.execute("SELECT COALESCE(MAX(order_index), -1) FROM timeline_nodes WHERE event_id = ?", (eid,))
        next_idx = cur.fetchone()[0] + 1
        for i, a in enumerate(items):
            cur.execute("""
                INSERT INTO timeline_nodes
                (event_id, date, label, summary, tier, is_current, order_index)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (eid, (a["publish_time"] or "")[:7], self._node_label(a),
                  a["title"][:150], a["tier"], 0, next_idx + i))

        # ── 卡片生成（LLM）──
        # 性能优化：仅在「新建事件」或「发生状态跃迁」时调用 LLM 生成卡片；
        # 仅追加证据而无跃迁时，复用已有卡片，避免每个事件每次都调 LLM。
        if existing is None or tr.changed:
            card = self._generate_card(ticker_name, theme, tr, evidences, existing)
        else:
            card = {
                "headline": existing.get("headline") or items[0]["title"][:120],
                "nature": existing.get("nature") or "neutral",
                "risk_note": existing.get("risk_note"),
                "focus_node": None,
                "confidence": existing.get("confidence"),
                "confidence_reason": existing.get("confidence_reason"),
                "directions": self._safe_json(existing.get("directions"), []),
            }
        # ── 确定性证据分析（权重 / 冲突 / 演化方向）—— 对事件全量证据复算 ──
        cur.execute("""SELECT tier, evidence_type, summary, source, date, credibility_score
                       FROM evidence_items WHERE event_id = ?""", (eid,))
        analysis = ea.analyze_event([dict(r) for r in cur.fetchall()])

        # ── 合规扫描（PRD §5.1）：把真实 T3 传闻传进去，
        #     未标注「未证实」会命中 blocking 规则；红线词会被改写后才落库 ──
        rumors = [{
            "content": a["title"][:120], "credibility": "低",
            "note": "未证实：T3 来源，无权威渠道背书",
        } for a in items
            if (a["tier"] or "").upper() == "T3" or a["evidence_type"] == "rumor"]
        comp = compliance.check_event_payload({
            "headline": card.get("headline", ""),
            "risk_note": card.get("risk_note", ""),
            "directions": analysis["directions"],
            "rumors": rumors,
        })
        compliance_note = "" if comp.passed else "；".join(
            f"[{i.level}] {i.message}" for i in comp.issues)

        # 合规层生效：红线词强制改写；未证实传闻必须在标题显著标注
        headline = compliance.sanitize(card.get("headline") or items[0]["title"][:120])
        if tr.state_code == sm.UNVERIFIED_RUMOR and "未证实" not in headline:
            headline = f"【未证实·传闻】{headline}"

        # ── 四类时间（语义严格区分，每次摄入都刷新）──
        #   event_time       事件发生时间：证据中最早的出现时刻，一旦确定不再回退
        #   disclosure_time  披露时间    ：最新来源对外披露的时刻（单调递增）
        #   crawl_time       抓取时间    ：本次系统抓取入库的日期
        #   updated_at       更新时间    ：本次结论重算的时刻
        today = datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        first_time = min((a.get("event_time") or a["publish_time"] or "" for a in items), default="")
        event_time = (existing or {}).get("event_time") or first_time
        disclosure_time = max(batch_last, (existing or {}).get("disclosure_time") or "")
        nature = card.get("nature") or (existing or {}).get("nature") or "neutral"
        directions_json = json.dumps(analysis["directions"], ensure_ascii=False)

        # ── 落库：新建或更新事件 ──
        if existing is None:
            cur.execute("""
                INSERT INTO events
                (event_id, ticker, ticker_name, theme, headline, status, state_code, state_label,
                 nature, nature_label, event_time, disclosure_time, crawl_time, updated_at,
                 last_evidence_at, notification_level, risk_note, confidence, confidence_reason,
                 weight_avg, has_conflict, compliance_note, timeline, evidence, directions, rumors)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '{}', ?, '[]')
            """, (eid, ticker, ticker_name, theme, headline, tr.card_tag, tr.state_code, tr.state_label,
                  nature, self._nature_label(nature),
                  event_time, disclosure_time, today, now_str,
                  last_at, tr.notification_level, card.get("risk_note"), card.get("confidence"),
                  card.get("confidence_reason"),
                  analysis["avg_weight"], 1 if analysis["conflict"] else 0, compliance_note,
                  directions_json))
        else:
            cur.execute("""
                UPDATE events SET headline=?, status=?, state_code=?, state_label=?, nature=?,
                  nature_label=?, event_time=?, disclosure_time=?, crawl_time=?, updated_at=?,
                  last_evidence_at=?, notification_level=?, risk_note=?, confidence=?,
                  confidence_reason=?, weight_avg=?, has_conflict=?, compliance_note=?,
                  directions=?
                WHERE event_id=?
            """, (headline, tr.card_tag, tr.state_code, tr.state_label,
                  nature, self._nature_label(nature),
                  event_time, disclosure_time, today, now_str,
                  last_at, tr.notification_level, card.get("risk_note"),
                  card.get("confidence"), card.get("confidence_reason"),
                  analysis["avg_weight"], 1 if analysis["conflict"] else 0, compliance_note,
                  directions_json, eid))

        # ── 演化方向 / 证据冲突 落表（供「其他说法」面板与 /directions 接口）──
        cur.execute("DELETE FROM event_directions WHERE event_id = ?", (eid,))
        for d in analysis["directions"]:
            cur.execute("""
                INSERT INTO event_directions
                (event_id, label, description, probability, supporting, risk)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, d["label"], d["description"], d["probability"],
                  json.dumps(d["supporting"], ensure_ascii=False), d["risk"]))

        # ── 版本快照 ──
        # 依据文档：每次**状态跃迁**记录一个版本；新建事件记录初始版本。
        # 仅追加证据而无跃迁时不生成版本（也保证了重跑的幂等性）。
        if existing is None or tr.changed:
            cur.execute("SELECT COALESCE(MAX(version), 0) FROM event_versions WHERE event_id = ?", (eid,))
            ver = cur.fetchone()[0] + 1
            cur.execute("""
                INSERT INTO event_versions
                (event_id, version, status, nature, headline, timeline_snapshot, evidence_snapshot,
                 directions_snapshot, change_type, change_reason, created_by, notification_level, rule_fired)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'analyst', ?, ?)
            """, (eid, ver, tr.state_label, card.get("nature", "neutral"), headline,
                  json.dumps([{"title": a["title"], "tier": a["tier"]} for a in items], ensure_ascii=False),
                  "{}", directions_json,
                  self._change_type(tr), f"[{tr.rule_id}] {tr.reason}",
                  tr.notification_level, tr.rule_id))

        # ── 通知（仅跃迁时） ──
        if tr.changed and tr.notification_level:
            self._notify(cur, eid, tr)

        return {
            "event_id": eid, "rule": tr.rule_id, "from": cur_state,
            "to": tr.state_code, "changed": tr.changed,
            "compliance_blocked": comp.blocked,
            "compliance_issues": [i.to_dict() for i in comp.issues],
        } if tr.changed else None

    # ═══ 卡片生成 ═══
    def _generate_card(self, ticker_name, theme, tr, evidences, existing) -> dict:
        ev_brief = [{"tier": e.tier, "type": e.evidence_type, "date": e.publish_time,
                     "summary": e.summary[:100]} for e in evidences]
        user = (f"标的：{ticker_name}\n主题：{theme}\n"
                f"当前状态：{tr.state_label}（{tr.state_code}）\n"
                f"状态说明：{tr.reason}\n"
                f"证据：{json.dumps(ev_brief, ensure_ascii=False)}\n\n"
                f"请生成判断卡片。")
        try:
            resp = self.llm.chat([{"role": "user", "content": user}],
                                 system=CARD_SYSTEM, max_tokens=1500, temperature=0.2)
            card = _extract_json(LLMClient.extract_text(resp))
            # LLM 可能返回数组包裹的对象，或返回了数组本体 —— 归一化为 dict
            if isinstance(card, list):
                card = next((x for x in card if isinstance(x, dict)), None) or {}
            if not isinstance(card, dict):
                card = {}
        except Exception as e:
            print(f"[Analyst] 卡片生成失败: {e}")
            card = {}
        if not card:
            card = {
                "headline": (evidences[0].summary if evidences else theme)[:50],
                "nature": "neutral", "risk_note": "", "focus_node": None,
                "confidence": "中", "confidence_reason": "自动兜底生成", "directions": [],
            }
        return card

    # ═══ 通知 ═══
    def _notify(self, cur, eid, tr):
        """
        只推送给「真正关心该事件」的用户：
          ① 订阅了该事件的用户
          ② 持仓 / 关注了该事件所属标的的用户
        不再对无人订阅的事件默认推给用户 1 —— 那会产生大量无关通知。
        """
        cur.execute("SELECT ticker FROM events WHERE event_id = ?", (eid,))
        row = cur.fetchone()
        ticker = row[0] if row else None

        # ① 事件订阅者
        cur.execute("SELECT user_id FROM event_subscriptions WHERE event_id = ?", (eid,))
        targets = {r[0] for r in cur.fetchall()}

        # ② 持仓 / 关注该标的的用户
        if ticker:
            cur.execute("SELECT user_id FROM holdings WHERE ticker = ?", (ticker,))
            targets |= {r[0] for r in cur.fetchall()}
            cur.execute("SELECT user_id FROM ticker_subscriptions WHERE ticker = ?", (ticker,))
            targets |= {r[0] for r in cur.fetchall()}

        subs = sorted(targets)
        if not subs:
            return   # 无人关心该事件 → 不产生通知
        for uid in subs:
            title = f"[{tr.notification_level}] {tr.state_label}"
            content = f"{tr.card_tag}：{tr.reason}"
            # 幂等：同一用户 + 同一事件 + 同一文案只推一次，
            # 避免重跑流水线或"分析 Agent / 通知同步"双写产生重复通知。
            cur.execute("""
                SELECT 1 FROM notifications
                WHERE user_id = ? AND event_id = ? AND title = ? AND content = ?
                LIMIT 1
            """, (uid, eid, title, content))
            if cur.fetchone():
                continue
            cur.execute("""
                INSERT INTO notifications (user_id, event_id, type, title, content)
                VALUES (?, ?, ?, ?, ?)
            """, (uid, eid, self._notif_type(tr), title, content))

    # ═══ 规则兜底小函数（LLM 失败时用） ═══
    @staticmethod
    def _rule_theme(title):
        for kw, name in [("回购", "股份回购"), ("业绩", "业绩披露"), ("财报", "定期报告"),
                         ("储能", "储能业务"), ("销量", "销量数据"), ("扩产", "产能扩张"),
                         ("担保", "对外担保"), ("分红", "利润分配"), ("减持", "股东减持"),
                         ("增持", "股东增持"), ("合作", "战略合作"), ("订单", "订单获取")]:
            if title and kw in title:
                return name
        return "公司动态"

    @staticmethod
    def _rule_evidence_type(msg):
        if msg.get("source_type") == "notice":
            return "fact"
        if msg.get("source_type") == "research":
            return "opinion"
        return "speculation"

    @staticmethod
    def _rule_semantics(title):
        t = title or ""
        if CORRECTION_PAT.search(t):
            return "correct"
        if any(w in t for w in ["澄清", "否认", "不存在", "不实"]):
            return "deny"
        if any(w in t for w in ["进展", "完成", "签署", "上线", "中标", "落地"]):
            return "substance"
        if any(w in t for w in ["公告", "报告", "披露"]):
            return "confirm"
        return "neutral"

    @staticmethod
    def _node_label(a):
        return {("T0", "fact"): "官方披露", ("T1", "fact"): "媒体报道"}.get(
            (a["tier"], a["evidence_type"]), "信息更新")

    @staticmethod
    def _nature_label(nature):
        return {"positive": "利好", "negative": "利空", "risk": "风险", "neutral": "中性"}.get(nature, "中性")

    @staticmethod
    def _change_type(tr):
        if tr.is_correction:
            return "correct"
        if tr.state_code == sm.OFFICIALLY_DENIED:
            return "deny"
        if tr.state_code == sm.EXPIRED:
            return "expire"
        if tr.is_revival:
            return "revive"
        return "update"

    @staticmethod
    def _notif_type(tr):
        if tr.state_code == sm.OFFICIALLY_DENIED:
            return "denial"
        if tr.is_correction:
            return "correction"
        if tr.state_code == sm.EXPIRED:
            return "expiry"
        return "state_transition"

    def _load_existing_events(self, cur, ticker):
        cur.execute("SELECT * FROM events WHERE ticker = ?", (ticker,))
        return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def _safe_json(v, default):
        try:
            return json.loads(v) if v else default
        except Exception:
            return default

    @staticmethod
    def _make_event_id(ticker, theme):
        slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (theme or "公司动态")).strip("_")[:40]
        return f"{ticker.replace('.', '_')}_{slug or '公司动态'}"


if __name__ == "__main__":
    agent = AnalystAgent()
    r = agent.process_batch(limit=500)
    print("=== 分析 Agent 运行结果 ===")
    print(json.dumps(r, ensure_ascii=False, indent=2)[:2000])
