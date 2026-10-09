"""
确定性证据分析 —— 无 LLM，可复算、可追溯

回答需求中的两个硬指标：
  1. 「证据权重」—— 每条证据给出 0~1 的可计算权重，而不是只有层级标签；
  2. 「证据冲突」—— 在同一事件内检测互相矛盾的说法，并推导演化方向。

设计原则：**同一份证据输入，必然得到同一份输出**。
所有系数都在下方常量表里写死，任何数字都能被人工复算（满足"关键数字必须可追溯"）。

权重公式：
    权重 = tier 基础权重 × 类型系数 × 来源质量系数(可选)

    tier 基础权重：T0 公告 1.00 / T1 权威媒体 0.70 / T2 研报观点 0.50 / T3 传闻 0.25
    类型系数    ：事实 1.00 / 观点 0.65 / 推测 0.40 / 传闻 0.25
    来源质量系数：0.6 + 0.4 × hit_rate（命中率来自 source_quality 表，缺省不参与计算）

例：T0 公告中的事实       = 1.00 × 1.00 = 1.000
    T1 媒体的报道(事实)   = 0.70 × 1.00 = 0.700
    T3 股吧传闻           = 0.25 × 0.25 = 0.063
"""
import re

# ─── 系数表（可追溯的基石，勿随意调整；调整需同步 docs） ───
TIER_BASE = {"T0": 1.00, "T1": 0.70, "T2": 0.50, "T3": 0.25}
TYPE_FACTOR = {"fact": 1.00, "opinion": 0.65, "speculation": 0.40, "rumor": 0.25}
TYPE_LABEL = {"fact": "事实", "opinion": "观点", "speculation": "推测", "rumor": "传闻"}
TIER_LABEL = {"T0": "官方公告", "T1": "权威媒体", "T2": "研报观点", "T3": "市场传闻"}

# 概率档位（PRD 规定只允许 高/中高/中/中低/低，禁止精确百分比）
PROB_BANDS = [(0.70, "高"), (0.50, "中高"), (0.35, "中"), (0.20, "中低"), (0.00, "低")]

# ─── 冲突检测词表（口语化对立表述） ───
POSITIVE_WORDS = ["签署", "中标", "完成", "落地", "投产", "获批", "回购", "增长",
                  "超预期", "上调", "达成", "上线", "通过", "扩张", "增持"]
NEGATIVE_WORDS = ["否认", "澄清", "不实", "谣言", "终止", "失败", "下调", "亏损",
                  "下滑", "减持", "问询", "处罚", "违规", "延期", "取消", "未予证实"]


def evidence_weight(tier, evidence_type, source_quality=None) -> float:
    """
    计算单条证据的权重（0~1）。输入相同则输出恒定。
    source_quality 为该来源的历史命中率(0~1)，缺省(None)时不参与计算。
    """
    base = TIER_BASE.get((tier or "T1").upper(), 0.50)
    tf = TYPE_FACTOR.get(evidence_type or "speculation", 0.40)
    w = base * tf
    if source_quality is not None:
        w *= 0.6 + 0.4 * max(0.0, min(1.0, float(source_quality)))
    return round(w, 3)


def weight_label(w: float) -> str:
    """把权重映射为可读强度标签"""
    if w >= 0.85:
        return "强"
    if w >= 0.60:
        return "较强"
    if w >= 0.35:
        return "中等"
    if w >= 0.15:
        return "较弱"
    return "弱"


def probability_band(w: float) -> str:
    for threshold, label in PROB_BANDS:
        if w >= threshold:
            return label
    return "低"


def evidence_type_label(evidence_type) -> str:
    return TYPE_LABEL.get(evidence_type or "", "未分类")


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else 0.0


def detect_conflict(rows) -> tuple:
    """
    在同一事件的证据集合内检测「互相矛盾的说法」。
    判定（确定性，两条任一即可）：
      A. 证据标题同时命中「正向落地类」与「反向否认类」词表；
      B. 同时存在 T3 传闻 与 T0/T1 权威口径，且 T3 标题命中否认类词表。
    返回 (是否存在冲突, 说明文字, 冲突证据摘要列表)
    """
    if not rows:
        return False, "", []

    pos_hits, neg_hits = [], []
    for r in rows:
        txt = (r.get("summary") or "") + " " + (r.get("source") or "")
        if any(w in txt for w in POSITIVE_WORDS):
            pos_hits.append(r)
        if any(w in txt for w in NEGATIVE_WORDS):
            neg_hits.append(r)

    tiers = {(r.get("tier") or "").upper() for r in rows}
    rumor_neg = [r for r in neg_hits if (r.get("tier") or "").upper() == "T3"]
    authority = {"T0", "T1"} & tiers

    if pos_hits and neg_hits:
        note = (f"存在 {len(pos_hits)} 条「确认/落地」类证据与 "
                f"{len(neg_hits)} 条「否认/风险」类证据并存，结论存在冲突")
        evidence = pos_hits[:2] + neg_hits[:2]
        return True, note, evidence

    if rumor_neg and authority:
        note = f"市场传闻（T3）出现否认性表述，但与 {sorted(authority)} 权威口径并存，需以权威口径为准"
        return True, note, rumor_neg[:2]

    return False, "", []


def derive_directions(rows) -> list:
    """
    由证据结构确定性推导"演化方向 / 其他说法"。
    按证据层级分组（官方口径 / 媒体研报 / 市场传闻），每组一个方向，
    给出代表说法、支撑证据、概率档位与风险提示。
    """
    if not rows:
        return []

    groups = [
        ("官方口径", {"T0"}, "已披露的公告/定期报告所代表的官方表述"),
        ("媒体研报口径", {"T1", "T2"}, "权威媒体与券商研报的解读视角"),
        ("市场传闻口径", {"T3"}, "股吧/自媒体等未经权威证实的说法"),
    ]
    out = []
    for label, tiers, desc in groups:
        grp = [r for r in rows if (r.get("tier") or "").upper() in tiers]
        if not grp:
            continue
        ws = [r.get("credibility_score") if r.get("credibility_score") is not None
              else evidence_weight(r.get("tier"), r.get("evidence_type")) for r in grp]
        avg = _avg(ws)
        rep = max(grp, key=lambda r: (r.get("credibility_score") or 0))
        out.append({
            "label": label,
            "description": (rep.get("summary") or "")[:160],
            "probability": probability_band(avg),
            "supporting": [{"source": r.get("source"), "date": r.get("date"),
                            "tier": r.get("tier"), "type": r.get("evidence_type"),
                            "title": (r.get("summary") or "")[:100]} for r in grp[:5]],
            "risk": f"该口径共 {len(grp)} 条证据，平均权重 {avg}（{weight_label(avg)}）；"
                    f"仅代表「{TIER_LABEL.get(sorted(tiers)[0], '')}」层级的信息强度，非投资结论。",
            "evidence_count": len(grp),
            "avg_weight": avg,
        })

    conflict, note, _ = detect_conflict(rows)
    if conflict:
        out.append({
            "label": "存在冲突说法",
            "description": note,
            "probability": "中",
            "supporting": [{"source": r.get("source"), "date": r.get("date"),
                            "tier": r.get("tier"),
                            "title": (r.get("summary") or "")[:100]} for r in rows
                           if any(w in ((r.get("summary") or "") + (r.get("source") or ""))
                                  for w in POSITIVE_WORDS + NEGATIVE_WORDS)][:5],
            "risk": "证据之间存在方向性矛盾，当前结论的确定性下降，建议等待权威口径更新。",
            "evidence_count": 0,
            "avg_weight": 0.0,
        })
    return out


def analyze_event(rows) -> dict:
    """
    对单个事件的证据集合做完整确定性分析。
    rows: [{'tier','evidence_type','summary','source','date','credibility_score'}]
    返回: {'avg_weight','max_weight','evidence_count','conflict','conflict_note',
           'type_counts','tier_counts','directions'}
    """
    rows = rows or []
    weights = [r.get("credibility_score") if r.get("credibility_score") is not None
               else evidence_weight(r.get("tier"), r.get("evidence_type")) for r in rows]
    conflict, note, _ = detect_conflict(rows)

    type_counts, tier_counts = {}, {}
    for r in rows:
        t = r.get("evidence_type") or "unclassified"
        type_counts[t] = type_counts.get(t, 0) + 1
        tr = (r.get("tier") or "?").upper()
        tier_counts[tr] = tier_counts.get(tr, 0) + 1

    return {
        "avg_weight": _avg(weights),
        "max_weight": round(max(weights), 3) if weights else 0.0,
        "evidence_count": len(rows),
        "conflict": conflict,
        "conflict_note": note,
        "type_counts": type_counts,
        "tier_counts": tier_counts,
        "directions": derive_directions(rows),
    }


# ─── 自测 ───
if __name__ == "__main__":
    print("=== 权重表（可人工复算） ===")
    for tier in ["T0", "T1", "T2", "T3"]:
        for et in ["fact", "opinion", "speculation", "rumor"]:
            w = evidence_weight(tier, et)
            print(f"  {tier} {TYPE_LABEL[et]:<4} -> {w:<6} {weight_label(w)}")

    print("\n=== 冲突检测 ===")
    demo = [
        {"tier": "T0", "evidence_type": "fact", "summary": "公司公告：签署重大合同", "source": "iFinD"},
        {"tier": "T3", "evidence_type": "rumor", "summary": "股吧传闻：合作已终止，公司澄清不实", "source": "股吧"},
    ]
    info = analyze_event(demo)
    print("  conflict =", info["conflict"], "|", info["conflict_note"])
    print("  directions =", [d["label"] for d in info["directions"]])
