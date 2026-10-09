"""
事件状态机 — 纯规则引擎，无 LLM 参与
严格实现 docs/03-foundation/EVENT_STATE_MACHINE.md 的 6 状态 13 规则
保证：可复现、可追溯（每次跃迁都记录触发的规则编号）

设计边界：
- 本模块只做"裁决"，不做"理解"。
- "这条消息是确认还是否认"由分析 Agent（LLM）判断后，以 semantics 字段传入。
- 裁决过程纯确定性代码，无随机、无模型调用。
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

# ─── 状态编码（对应文档第二节） ───
UNVERIFIED_RUMOR = "UNVERIFIED_RUMOR"
MEDIA_VERIFIED = "MEDIA_VERIFIED"
OFFICIALLY_CONFIRMED = "OFFICIALLY_CONFIRMED"
OFFICIALLY_DENIED = "OFFICIALLY_DENIED"
SUBSTANCE_LANDED = "SUBSTANCE_LANDED"
EXPIRED = "EXPIRED"

STATE_META = {
    UNVERIFIED_RUMOR:     {"label": "传闻待证实", "color": "gray",    "card_tag": "未证实传闻"},
    MEDIA_VERIFIED:       {"label": "媒体验证中", "color": "orange",  "card_tag": "媒体验证"},
    OFFICIALLY_CONFIRMED: {"label": "官方已确认", "color": "green",   "card_tag": "官方确认"},
    OFFICIALLY_DENIED:    {"label": "官方已否认", "color": "red",     "card_tag": "官方否认"},
    SUBSTANCE_LANDED:     {"label": "实质已落地", "color": "deepgreen","card_tag": "实质落地"},
    EXPIRED:              {"label": "事件已过期", "color": "lightgray","card_tag": "已过期"},
}

# ─── 通知优先级映射（对应文档第五节） ───
NOTIFICATION_LEVEL = {
    OFFICIALLY_CONFIRMED: "P0",
    OFFICIALLY_DENIED: "P0",
    SUBSTANCE_LANDED: "P1",
    MEDIA_VERIFIED: "P1",
    EXPIRED: "P1",
    UNVERIFIED_RUMOR: "P2",
}

# ─── 时效阈值（对应文档规则 10/11/13） ───
EXPIRY_UNVERIFIED_DAYS = 30   # Rule 13
EXPIRY_CONFIRMED_DAYS = 90    # Rule 10
EXPIRY_DENIED_DAYS = 7        # Rule 11

TIER_WEIGHT = {"T0": 4, "T1": 3, "T2": 2, "T3": 1}


@dataclass
class Evidence:
    """传入裁决的单个证据（由分析 Agent 从原始消息转换而来）"""
    tier: str                    # T0/T1/T2/T3
    semantics: str               # confirm / deny / substance / correct / neutral
    evidence_type: str = "fact"  # fact / opinion / speculation / rumor
    publish_time: str = ""
    source: str = ""
    summary: str = ""


@dataclass
class TransitionResult:
    state_code: str
    state_label: str
    card_tag: str
    color: str
    rule_id: Optional[str]           # 触发的规则编号，无跃迁时为 None
    changed: bool                    # 是否发生跃迁
    notification_level: Optional[str]
    reason: str
    is_correction: bool = False      # 是否为"更正"（Rule 12 / Case 1）
    is_controversy: bool = False     # 官方否认但仍有 T3 传闻
    is_revival: bool = False         # 过期事件被新证据重新激活（≠ 更正）


def _days_since(date_str: str, now: datetime) -> int:
    if not date_str:
        return 0
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return (now - d).days
    except Exception:
        return 0


def count_by(evidence: List[Evidence], tier: str) -> int:
    return sum(1 for e in evidence if e.tier == tier)


def has_t0(evidence: List[Evidence], semantics: str) -> bool:
    return any(e.tier == "T0" and e.semantics == semantics for e in evidence)


def latest_t0(evidence: List[Evidence]) -> Optional[Evidence]:
    """取最新的 T0（时间最新的 T0 为准，对应文档冲突处理）"""
    t0s = [e for e in evidence if e.tier == "T0"]
    if not t0s:
        return None
    return sorted(t0s, key=lambda e: e.publish_time)[-1]


def authoritative_t0(evidence: List[Evidence]) -> Optional[Evidence]:
    """
    取"权威 T0"：即最新的一条**明确确认性** T0 披露。

    依据文档第二节：OFFICIALLY_CONFIRMED = 「有 T0 公告或监管文件**明确确认**」。

    注意区分两类 T0：
      - semantics = confirm / substance （明确确认或实质进展）→ 构成官方确认
      - semantics = neutral（如互动易上"请参考公开信息"的回避性回应）
        → **不构成确认**，只作为证据补充，不改变状态
    """
    t0s = [e for e in evidence if e.tier == "T0" and e.semantics in ("confirm", "substance")]
    if not t0s:
        return None
    return sorted(t0s, key=lambda e: e.publish_time)[-1]


def arbitrate(
    current_state: Optional[str],
    evidence: List[Evidence],
    last_evidence_at: str = "",
    now: Optional[datetime] = None,
) -> TransitionResult:
    """
    状态裁决主函数（确定性）。
    - current_state 为 None 表示事件新建（START）
    - 返回 TransitionResult（含触发的规则编号）
    """
    now = now or datetime.now()

    # ═══ 新建事件：Rule 1 / 2 / 3 ═══
    if current_state is None:
        t0 = latest_t0(evidence)
        if t0 and t0.semantics == "deny":
            return _r("Rule 6", OFFICIALLY_DENIED, "T0 公告明确否认，事件创建即官方否认", True)
        if authoritative_t0(evidence):
            return _r("Rule 3", OFFICIALLY_CONFIRMED, "存在 T0 公告披露，事件创建即官方确认", True)
        if count_by(evidence, "T1") >= 2:
            return _r("Rule 2", MEDIA_VERIFIED, "≥2 条 T1 权威媒体交叉验证，无 T0", True)
        return _r("Rule 1", UNVERIFIED_RUMOR, "仅有 T3 传闻或匿名消息，无 T1/T0 验证", True)

    # ═══ 已过期事件：新证据可重新激活 ═══
    if current_state == EXPIRED:
        t0 = latest_t0(evidence)
        if t0 and t0.semantics == "confirm":
            return _r("Rule 3", OFFICIALLY_CONFIRMED, "过期事件出现新 T0 确认，重新激活",
                      True, is_revival=True)
        if t0 and t0.semantics == "deny":
            return _r("Rule 6", OFFICIALLY_DENIED, "过期事件出现新 T0 否认", True)
        if count_by(evidence, "T1") >= 2:
            return _r("Rule 2", MEDIA_VERIFIED, "过期事件出现 ≥2 条 T1，重新激活",
                      True, is_revival=True)
        return _no_change(current_state, "过期事件新增 T3/T2，不改变状态")

    # ═══ Rule 12：更正公告推翻既有结论 ═══
    # 「更正」与「否认」不同：官方不是全盘否定，而是修正此前口径，结论随之改写。
    # 只有「更正公告 / 补充更正」这类明确措辞才判定为更正（"修订《公司章程》"属常规事项，不算）。
    # 单条 T0 更正在监管语境下即为决定性证据，故不要求 ≥2 条 T1 前置条件。
    # 已在确认/落地态时不重复触发，保证重跑幂等。
    correction_t0 = next((e for e in evidence
                          if e.tier == "T0" and e.semantics == "correct"), None)
    if correction_t0 and current_state not in (OFFICIALLY_CONFIRMED, SUBSTANCE_LANDED):
        return _r("Rule 12", OFFICIALLY_CONFIRMED,
                  f"出现 T0 更正公告（{correction_t0.summary[:40]}），推翻既有口径",
                  True, is_correction=True)

    # ═══ Rule 9/10/12：官方确认 / 官否 的特殊跃迁 ═══
    if current_state == OFFICIALLY_CONFIRMED:
        if any(e.semantics == "substance" for e in evidence):
            return _r("Rule 9", SUBSTANCE_LANDED, "出现实质进展证据（合同/产品/业绩兑现）", True)
        if _days_since(last_evidence_at, now) > EXPIRY_CONFIRMED_DAYS:
            return _r("Rule 10", EXPIRED, f"官方确认后超过 {EXPIRY_CONFIRMED_DAYS} 天无新证据", True)
        return _no_change(current_state, "官方确认状态下新增证据，仅更新证据列表")

    if current_state == OFFICIALLY_DENIED:
        # Rule 12：否认被推翻（≥2 条 T1 + 新 T0 更正）
        t0 = authoritative_t0(evidence)
        t1_count = count_by(evidence, "T1")
        if t0 and t1_count >= 2:
            return _r("Rule 12", OFFICIALLY_CONFIRMED, "官方否认后被新 T0 更正为确认（否认被推翻）", True, is_correction=True)
        if t1_count >= 2:
            return _r("Rule 12", MEDIA_VERIFIED, "官方否认后出现 ≥2 条 T1 指向同一主题", True, is_correction=True)
        if _days_since(last_evidence_at, now) > EXPIRY_DENIED_DAYS:
            return _r("Rule 11", EXPIRED, f"官方否认后超过 {EXPIRY_DENIED_DAYS} 天无新 T0/T1 证据", True)
        still_rumor = any(e.tier == "T3" for e in evidence)
        res = _no_change(current_state, "官方否认状态下新增证据，不改变状态")
        res.is_controversy = still_rumor
        return res

    # ═══ Rule 4/5/6：未证实传闻的跃迁 ═══
    if current_state == UNVERIFIED_RUMOR:
        t0 = latest_t0(evidence)
        if t0 and t0.semantics == "deny":
            return _r("Rule 6", OFFICIALLY_DENIED, "T0 公告明确否认", True)
        if authoritative_t0(evidence):
            return _r("Rule 5", OFFICIALLY_CONFIRMED, "出现 T0 公告披露", True)
        if count_by(evidence, "T1") >= 2:
            return _r("Rule 4", MEDIA_VERIFIED, "≥2 条 T1 权威媒体交叉验证", True)
        if _days_since(last_evidence_at, now) > EXPIRY_UNVERIFIED_DAYS:
            res = _r("Rule 13", EXPIRED, f"超过 {EXPIRY_UNVERIFIED_DAYS} 天无新证据，静默归档", True)
            res.notification_level = None  # Rule 13 不触发通知
            return res
        return _no_change(current_state, "未证实传闻状态下新增证据")

    # ═══ Rule 7/8：媒体验证的跃迁 ═══
    if current_state == MEDIA_VERIFIED:
        t0 = latest_t0(evidence)
        if t0 and t0.semantics == "deny":
            return _r("Rule 8", OFFICIALLY_DENIED, "T0 公告明确否认", True)
        if authoritative_t0(evidence):
            return _r("Rule 7", OFFICIALLY_CONFIRMED, "出现 T0 公告披露", True)
        return _no_change(current_state, "媒体验证状态下新增证据")

    # 兜底
    return _no_change(current_state, "无匹配规则")


def check_expiry(current_state: Optional[str], last_evidence_at: str,
                 now: Optional[datetime] = None) -> Optional[TransitionResult]:
    """独立的过期检查（定时任务调用，无新证据时也能触发 Rule 10/11/13）"""
    if not current_state or not last_evidence_at:
        return None
    now = now or datetime.now()
    days = _days_since(last_evidence_at, now)

    if current_state == UNVERIFIED_RUMOR and days > EXPIRY_UNVERIFIED_DAYS:
        res = _r("Rule 13", EXPIRED, f"超过 {EXPIRY_UNVERIFIED_DAYS} 天无新证据", True)
        res.notification_level = None
        return res
    if current_state == OFFICIALLY_CONFIRMED and days > EXPIRY_CONFIRMED_DAYS:
        return _r("Rule 10", EXPIRED, f"官方确认后超过 {EXPIRY_CONFIRMED_DAYS} 天无新证据", True)
    if current_state == OFFICIALLY_DENIED and days > EXPIRY_DENIED_DAYS:
        return _r("Rule 11", EXPIRED, f"官方否认后超过 {EXPIRY_DENIED_DAYS} 天无新证据", True)
    return None


def _r(rule_id, code, reason, changed, is_correction=False, is_revival=False) -> TransitionResult:
    meta = STATE_META[code]
    return TransitionResult(
        state_code=code, state_label=meta["label"], card_tag=meta["card_tag"],
        color=meta["color"], rule_id=rule_id, changed=changed,
        notification_level=NOTIFICATION_LEVEL.get(code), reason=reason,
        is_correction=is_correction, is_revival=is_revival,
    )


def _no_change(current_state, reason) -> TransitionResult:
    meta = STATE_META.get(current_state, STATE_META[UNVERIFIED_RUMOR])
    return TransitionResult(
        state_code=current_state, state_label=meta["label"], card_tag=meta["card_tag"],
        color=meta["color"], rule_id=None, changed=False,
        notification_level=None, reason=reason,
    )


# ─── 自测 ───
if __name__ == "__main__":
    print("=== 状态机规则自测 ===")
    cases = [
        ("新建-T3",     None, [Evidence("T3", "neutral")]),
        ("新建-2×T1",   None, [Evidence("T1", "neutral"), Evidence("T1", "neutral")]),
        ("新建-T0确认", None, [Evidence("T0", "confirm")]),
        ("新建-T0否认", None, [Evidence("T0", "deny")]),
        ("传闻→媒体",   UNVERIFIED_RUMOR, [Evidence("T1", "neutral"), Evidence("T1", "neutral")]),
        ("传闻→确认",   UNVERIFIED_RUMOR, [Evidence("T0", "confirm")]),
        ("媒体→否认",   MEDIA_VERIFIED, [Evidence("T0", "deny")]),
        ("确认→落地",   OFFICIALLY_CONFIRMED, [Evidence("T0", "substance")]),
        ("否认被推翻",  OFFICIALLY_DENIED, [Evidence("T0", "confirm"), Evidence("T1", "neutral"), Evidence("T1", "neutral")]),
        ("T0更正公告",  UNVERIFIED_RUMOR, [Evidence("T0", "correct")]),
        ("过期后复活",  EXPIRED, [Evidence("T0", "confirm")]),
    ]
    for name, cur, ev in cases:
        r = arbitrate(cur, ev, last_evidence_at=datetime.now().strftime("%Y-%m-%d"))
        print(f"  {name:14} → {r.state_code:22} [{r.rule_id}] {r.reason[:36]}")

    # 过期测试
    old = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    r = check_expiry(OFFICIALLY_CONFIRMED, old)
    print(f"  {'确认→过期(100d)':14} → {r.state_code:22} [{r.rule_id}]")
    old2 = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
    r = check_expiry(UNVERIFIED_RUMOR, old2)
    print(f"  {'传闻→过期(40d)':14} → {r.state_code:22} [{r.rule_id}] 通知={r.notification_level}")
