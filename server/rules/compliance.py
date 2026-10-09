"""
合规审查规则 — 纯规则，无 LLM
严格实现 docs/04-prd/PRD.md §5.1 的合规红线
所有用户可见文案必须过此检查，违规即阻塞上线。
"""
import re
from typing import List, Dict

# ─── 红线词（PRD §5.1 明确列出） ───
BLOCKING_WORDS = [
    "买入", "卖出", "持有建议", "加仓", "减仓", "目标价",
    "必涨", "稳赚", "抄底", "逃顶", "强烈推荐", "建议买", "建议卖",
    "保证收益", "无风险", "保本",
]

# ─── 警告词（绝对化表述，Agent.md 禁止） ───
WARNING_WORDS = ["一定", "必然", "肯定会", "百分之百", "绝对", "必定"]

# ─── 精确百分比概率（V1 只允许 高/中高/中/低） ───
# 同时匹配「80%概率」和「概率80%」两种语序
PERCENT_PATTERN = re.compile(
    r"(\d{1,3}\s*%\s*(概率|可能性|几率))|((概率|可能性|几率)\s*\d{1,3}\s*%)"
)

DISCLAIMER_KEYWORDS = ["不构成投资建议", "投资有风险", "仅供参考", "非投资建议"]

ALLOWED_PROBABILITY = {"高", "中高", "中", "中低", "低"}


class ComplianceIssue:
    def __init__(self, level: str, code: str, message: str, snippet: str = ""):
        self.level = level      # blocking / warning
        self.code = code
        self.message = message
        self.snippet = snippet

    def to_dict(self):
        return {"level": self.level, "code": self.code, "message": self.message, "snippet": self.snippet}


class ComplianceResult:
    def __init__(self, issues: List[ComplianceIssue]):
        self.issues = issues

    @property
    def blocked(self) -> bool:
        return any(i.level == "blocking" for i in self.issues)

    @property
    def passed(self) -> bool:
        return not self.issues

    def to_dict(self):
        return {
            "passed": self.passed,
            "blocked": self.blocked,
            "issues": [i.to_dict() for i in self.issues],
        }


def check_text(text: str) -> ComplianceResult:
    """检查任意用户可见文本"""
    issues = []
    if not text:
        return ComplianceResult(issues)

    for w in BLOCKING_WORDS:
        if w in text:
            issues.append(ComplianceIssue(
                "blocking", "INVESTMENT_ADVICE",
                f"含投资建议红线词「{w}」", _snippet(text, w)))

    for w in WARNING_WORDS:
        if w in text:
            issues.append(ComplianceIssue(
                "warning", "ABSOLUTE_WORD",
                f"含绝对化表述「{w}」", _snippet(text, w)))

    m = PERCENT_PATTERN.search(text)
    if m:
        issues.append(ComplianceIssue(
            "warning", "PRECISE_PERCENT",
            "使用了精确百分比概率（V1 仅允许 高/中高/中/低）", m.group(0).strip()))

    return ComplianceResult(issues)


def check_event_payload(payload: dict) -> ComplianceResult:
    """检查事件卡片全量字段（headline / directions / rumors / risk_note）"""
    issues = []

    def scan(text, code_prefix):
        r = check_text(text or "")
        for i in r.issues:
            i.code = f"{code_prefix}.{i.code}"
            issues.append(i)

    scan(payload.get("headline", ""), "headline")
    scan(payload.get("risk_note", ""), "risk_note")

    for idx, d in enumerate(payload.get("directions", []) or []):
        scan(d.get("description", ""), f"directions[{idx}]")
        scan(d.get("risk", ""), f"directions[{idx}]")
        prob = (d.get("probability") or "").strip()
        if prob and prob not in ALLOWED_PROBABILITY:
            issues.append(ComplianceIssue(
                "warning", f"directions[{idx}].PROBABILITY",
                f"概率表述「{prob}」不在允许集合 {sorted(ALLOWED_PROBABILITY)} 内", prob))

    for idx, r in enumerate(payload.get("rumors", []) or []):
        scan(r.get("content", ""), f"rumors[{idx}]")
        # T3 传闻必须标注"未证实"
        note = (r.get("note") or "") + (r.get("credibility") or "")
        if "未证实" not in note and "未验证" not in note and "无权威" not in note:
            issues.append(ComplianceIssue(
                "blocking", f"rumors[{idx}].NO_UNVERIFIED_TAG",
                "T3 传闻未标注「未证实」", (r.get("content") or "")[:40]))

    return ComplianceResult(issues)


def sanitize(text: str) -> str:
    """自动替换红线词（用于 LLM 输出兜底）"""
    out = text or ""
    for w in BLOCKING_WORDS:
        out = out.replace(w, "〔已移除的合规敏感词〕")
    return out


# ─── 「是否在给出建议」的判定 ───
# 单纯命中红线词不足以判定违规：模型**拒绝**回答时也会复述"买入/目标价"等词
# （例："我无法给出买入建议或目标价"）。盲目改写会把正当的拒答改成病句。
# 因此只在"出现了红线词、且没有拒绝类表述"时，才认定为在给建议。
REFUSAL_MARKERS = [
    "无法", "不能", "不提供", "不建议", "不予", "不做", "拒绝",
    "违反", "不构成", "非投资建议", "仅供参考", "不预测", "不设",
]


def asserts_advice(text: str) -> bool:
    """
    判断文本是否**在给出**投资建议（而非在拒绝给出建议）。
    返回 True 表示需要改写；返回 False 表示只是提及/拒绝，无需改写。
    """
    t = text or ""
    if not any(w in t for w in BLOCKING_WORDS):
        return False
    if any(m in t for m in REFUSAL_MARKERS):
        return False
    return True


def has_disclaimer(text: str) -> bool:
    return any(k in (text or "") for k in DISCLAIMER_KEYWORDS)


def _snippet(text: str, word: str, radius: int = 12) -> str:
    i = text.find(word)
    if i < 0:
        return ""
    return text[max(0, i - radius): i + len(word) + radius]


# ─── 自测 ───
if __name__ == "__main__":
    print("=== 合规规则自测 ===")
    tests = [
        ("建议买入该股票，目标价100元", "应阻塞"),
        ("该事件可能带来一定影响", "应警告(一定)"),
        ("上涨概率80%", "应警告(精确百分比)"),
        ("公司公告确认合作，实际落地情况待观察", "应通过"),
    ]
    for text, expect in tests:
        r = check_text(text)
        status = "BLOCK" if r.blocked else ("WARN" if r.issues else "PASS")
        print(f"  [{status:5}] {expect:16} | {text}")

    payload = {
        "headline": "微信接入大模型",
        "rumors": [{"content": "下周官宣合作", "note": "尚无官方验证", "credibility": "低"}],
    }
    r = check_event_payload(payload)
    print(f"  payload 检查: {'BLOCK' if r.blocked else 'OK'}")
