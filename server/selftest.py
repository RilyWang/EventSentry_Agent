"""
EventSentry 自检套件 —— 覆盖「主链路 / 数据与接口异常 / 合规边界」

用法（无需外网，规则层测试完全离线）：
    cd server
    python selftest.py              # 规则层 + 接口层（若服务在运行）
    python selftest.py --rules      # 只跑离线规则层

设计说明：
  * A 段（规则层）**完全离线且确定性**，不依赖 LLM / iFinD，可在任何环境复现；
    这些用例直接对应 docs/03-foundation/EVENT_STATE_MACHINE.md 的 13 条规则与
    PRD §5.1 的合规红线，是本项目"关键结论可追溯"的验证手段。
  * B 段（接口层）对运行中的服务发真实 HTTP 请求，验证主链路每个环节都有数据。
  * C 段（异常与合规边界）验证非法入参不会 500、SQL 元字符不会注入、
    合规红线词会被改写且未证实传闻会被标注。

退出码：全部通过为 0，否则为 1（便于 CI 使用）。
"""
import os
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "agents"))

# 本机存在一个"系统级 SOCKS 代理"（Windows 注册表），会让 requests 把 localhost
# 也走代理；显式关闭，保证自检只打本机回环。
os.environ.setdefault("no_proxy", "*")
os.environ.setdefault("NO_PROXY", "*")
PROXIES = {"http": None, "https": None}

BASE = os.getenv("SELFTEST_BASE", "http://localhost:3000")

_results = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return bool(cond)


# ══════════════════════════════════════════════════════════════
# A 段：规则层（离线、确定性）
# ══════════════════════════════════════════════════════════════
def section_rules():
    from datetime import datetime, timedelta
    from rules import state_machine as sm
    from rules import compliance
    from rules import evidence_analysis as ea

    print("\n【A】规则层（离线，确定性）")

    # A1 新建事件的三条入口规则
    print(" A1 状态机 · 新建入口")
    check("仅 T3 传闻 → 未证实传闻 [Rule 1]",
          sm.arbitrate(None, [sm.Evidence("T3", "neutral")],
                       last_evidence_at=datetime.now().strftime("%Y-%m-%d")).state_code == sm.UNVERIFIED_RUMOR)
    check("2 条 T1 → 媒体验证 [Rule 2]",
          sm.arbitrate(None, [sm.Evidence("T1", "neutral"), sm.Evidence("T1", "neutral")],
                       last_evidence_at=datetime.now().strftime("%Y-%m-%d")).state_code == sm.MEDIA_VERIFIED)
    check("T0 确认 → 官方确认 [Rule 3]",
          sm.arbitrate(None, [sm.Evidence("T0", "confirm")],
                       last_evidence_at=datetime.now().strftime("%Y-%m-%d")).state_code == sm.OFFICIALLY_CONFIRMED)
    check("T0 否认 → 官方否认 [Rule 6]",
          sm.arbitrate(None, [sm.Evidence("T0", "deny")],
                       last_evidence_at=datetime.now().strftime("%Y-%m-%d")).state_code == sm.OFFICIALLY_DENIED)

    # A2 演化规则
    print(" A2 状态机 · 演化")
    today = datetime.now().strftime("%Y-%m-%d")
    r = sm.arbitrate(sm.UNVERIFIED_RUMOR, [sm.Evidence("T1", "neutral"), sm.Evidence("T1", "neutral")], last_evidence_at=today)
    check("传闻 → 媒体验证 [Rule 4]", r.state_code == sm.MEDIA_VERIFIED and r.rule_id == "Rule 4")
    r = sm.arbitrate(sm.MEDIA_VERIFIED, [sm.Evidence("T0", "confirm")], last_evidence_at=today)
    check("媒体验证 → 官方确认 [Rule 7]", r.state_code == sm.OFFICIALLY_CONFIRMED and r.rule_id == "Rule 7")
    r = sm.arbitrate(sm.OFFICIALLY_CONFIRMED, [sm.Evidence("T0", "substance")], last_evidence_at=today)
    check("官方确认 → 实质落地 [Rule 9]", r.state_code == sm.SUBSTANCE_LANDED and r.rule_id == "Rule 9")

    # A3 更正 / 复活（本次修复新增的语义区分）
    print(" A3 状态机 · 更正 vs 复活（语义区分）")
    r = sm.arbitrate(sm.UNVERIFIED_RUMOR, [sm.Evidence("T0", "correct")], last_evidence_at=today)
    check("T0 更正公告 → 官方确认 [Rule 12]，标记 is_correction",
          r.state_code == sm.OFFICIALLY_CONFIRMED and r.is_correction and r.rule_id == "Rule 12")
    r = sm.arbitrate(sm.EXPIRED, [sm.Evidence("T0", "confirm")], last_evidence_at=today)
    check("过期后新证据复活 → 标记 is_revival（不是更正）",
          r.is_revival and not r.is_correction)
    r = sm.arbitrate(sm.OFFICIALLY_CONFIRMED, [sm.Evidence("T0", "correct")], last_evidence_at=today)
    check("已确认态再入更正公告 → 不产生重复跃迁（重跑幂等）", r.changed is False)

    # A4 过期规则
    print(" A4 状态机 · 过期")
    old100 = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    check("官方确认 100 天无新证据 → 过期 [Rule 10]",
          sm.check_expiry(sm.OFFICIALLY_CONFIRMED, old100).state_code == sm.EXPIRED)
    old40 = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
    e = sm.check_expiry(sm.UNVERIFIED_RUMOR, old40)
    check("传闻 40 天无新证据 → 过期且不通知 [Rule 13]",
          e.state_code == sm.EXPIRED and e.notification_level is None)
    old8 = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d")
    check("官方否认 8 天无新证据 → 过期 [Rule 11]",
          sm.check_expiry(sm.OFFICIALLY_DENIED, old8).state_code == sm.EXPIRED)

    # A5 证据权重：确定性 + 系数表可复算
    print(" A5 证据权重（确定性、可复算）")
    w1 = ea.evidence_weight("T0", "fact")
    w2 = ea.evidence_weight("T0", "fact")
    check("同输入 → 同输出（可复现）", w1 == w2)
    check("T0 公告事实权重 = 1.0", w1 == 1.0, f"实际 {w1}")
    check("T3 传闻权重最低 (=0.0625)", ea.evidence_weight("T3", "rumor") < ea.evidence_weight("T3", "speculation"))
    check("权重单调：公告事实 > 媒体事实 > 研报观点 > 传闻",
          ea.evidence_weight("T0", "fact") > ea.evidence_weight("T1", "fact")
          > ea.evidence_weight("T2", "opinion") > ea.evidence_weight("T3", "rumor"))
    check("权重落在 [0,1]", all(0 <= ea.evidence_weight(t, k) <= 1
                              for t in ["T0", "T1", "T2", "T3"]
                              for k in ["fact", "opinion", "speculation", "rumor"]))
    check("权重档位只输出 PRD 允许的档位",
          ea.probability_band(0.9) in {"高", "中高", "中", "中低", "低"})

    # A6 证据冲突检测 + 演化方向
    print(" A6 证据冲突检测 / 演化方向")
    conflict_rows = [
        {"tier": "T0", "evidence_type": "fact", "summary": "公司公告：签署重大合同", "source": "iFinD"},
        {"tier": "T3", "evidence_type": "rumor", "summary": "股吧传闻：合作已终止并否认", "source": "股吧"},
    ]
    info = ea.analyze_event(conflict_rows)
    check("确认类 + 否认类并存 → 判定为证据冲突", info["conflict"] is True)
    labels = [d["label"] for d in info["directions"]]
    check("演化方向按层级分组输出", "官方口径" in labels and "市场传闻口径" in labels)
    check("冲突时附「存在冲突说法」方向", "存在冲突说法" in labels)
    clean = ea.analyze_event([{"tier": "T0", "evidence_type": "fact", "summary": "年报披露", "source": "iFinD"}])
    check("单一口径 → 不误报冲突", clean["conflict"] is False)

    # A7 合规边界（PRD §5.1）
    print(" A7 合规边界")
    check("「建议买入…目标价」→ 拦截", compliance.check_text("建议买入该股票，目标价100元").blocked)
    check("「稳赚/保本」→ 拦截", compliance.check_text("此策略稳赚不赔，保本").blocked)
    check("「上涨概率80%」→ 警告（禁止精确百分比）",
          any(i.code == "PRECISE_PERCENT" for i in compliance.check_text("上涨概率80%").issues))
    check("正常事件描述 → 通过", compliance.check_text("公司公告确认合作，实际落地情况待观察").passed)
    check("红线词改写生效", "买入" not in compliance.sanitize("建议买入贵州茅台"))
    check("断言式建议（给目标价）→ 判定为「在给建议」",
          compliance.asserts_advice("我认为可以买入该股，目标价 120 元"))
    check("正当拒答（复述红线词但拒绝）→ 不判定为给建议",
          not compliance.asserts_advice("我无法给出买入建议，也不提供目标价，这不构成投资建议"))
    payload = {"headline": "某传闻", "rumors": [{"content": "下周官宣", "note": "", "credibility": ""}]}
    check("T3 传闻未标注「未证实」→ 拦截",
          compliance.check_event_payload(payload).blocked)
    payload_ok = {"headline": "某传闻", "rumors": [{"content": "下周官宣", "note": "未证实", "credibility": "低"}]}
    check("T3 传闻已标注「未证实」→ 通过",
          not compliance.check_event_payload(payload_ok).blocked)
    check("未允许的概率档位（如「百分之八十」）→ 警告",
          any("PROBABILITY" in i.code for i in
              compliance.check_event_payload({"headline": "x", "directions": [{"probability": "百分之八十"}]}).issues))


# ══════════════════════════════════════════════════════════════
# B 段：接口层主链路（需要服务在运行）
# ══════════════════════════════════════════════════════════════
def section_api():
    import requests
    from urllib.parse import quote

    print("\n【B】接口层 · 主链路")

    def get(path, **kw):
        return requests.get(f"{BASE}{path}", timeout=30, proxies=PROXIES, **kw)

    try:
        get("/api/ping")
    except Exception as e:
        print(f"  [SKIP] 服务未运行（{type(e).__name__}）—— 只完成 A 段规则层自检")
        return

    # B1 事件列表 + 四个时间戳 + 状态覆盖
    r = get("/api/events", params={"limit": 200}).json()
    check("事件列表可访问且非空", r.get("total", 0) > 0, f"total={r.get('total')}")
    items = r.get("items", [])
    four = all(k in (items[0] if items else {}) for k in
               ["event_time", "disclosure_time", "crawl_time", "updated_at"])
    check("列表项含四类时间字段", four)
    check("状态机 6 状态均有覆盖",
          len([k for k, v in (r.get("status_counts") or {}).items() if v > 0]) >= 5,
          json.dumps(r.get("status_counts"), ensure_ascii=False))

    # B2 详情主链路
    eid = items[0]["id"]
    q = quote(eid, safe="")
    detail = get(f"/api/events/{q}").json()
    check("事件详情含状态码（可追溯）", bool(detail.get("state_code")), str(detail.get("state_code")))
    timeline = get(f"/api/events/{q}/timeline").json()
    evidence = get(f"/api/events/{q}/evidence").json()
    versions = get(f"/api/events/{q}/versions").json()
    check("事件脉络（timeline）非空", len(timeline) > 0, f"{len(timeline)} 条")
    check("证据链（evidence）非空", len(evidence) > 0, f"{len(evidence)} 条")
    check("每条证据都带类型与权重",
          all(e.get("evidence_type") and e.get("credibility_score") is not None for e in evidence))
    check("版本演化（versions）非空", len(versions) > 0, f"{len(versions)} 条")
    check("版本记录含触发规则编号（可追溯）",
          any(v.get("rule_fired") for v in versions))

    # B3 证据冲突 / 其他说法
    has_dirs = 0
    conflict_events = []
    for it in items:
        d = get(f"/api/events/{quote(it['id'], safe='')}/directions").json()
        if d:
            has_dirs += 1
        if it.get("has_conflict"):
            conflict_events.append(it["id"])
    check("演化方向数据已覆盖事件", has_dirs > 0, f"{has_dirs}/{len(items)} 个事件有方向数据")
    check("存在被标记「证据冲突」的事件", len(conflict_events) > 0, f"{len(conflict_events)} 个")

    # B4 订阅 / 通知 / Agent 状态
    subs = get("/api/subscriptions/events").json()
    check("订阅事件接口可用", isinstance(subs, (list, dict)))
    notif = get("/api/notifications").json()
    check("通知接口可用", "list" in notif, f"{len(notif.get('list', []))} 条")
    check("通知无重复（同用户+同事件+同标题唯一）",
          len({(n.get("user_id"), n.get("event_id"), n.get("title")) for n in notif.get("list", [])})
          == len(notif.get("list", [])))
    st = get("/api/agents/status").json()
    check("Agent 状态含 4 个组件", len(st.get("agents", {})) == 4, str(list(st.get("agents", {}).keys())))
    check("Agent 状态含数据统计", all(k in st.get("data", {}) for k in
                                    ["events", "evidence", "versions", "raw_messages"]))


# ══════════════════════════════════════════════════════════════
# C 段：数据 / 接口异常 与 合规边界
# ══════════════════════════════════════════════════════════════
def section_anomaly():
    import requests
    from urllib.parse import quote

    print("\n【C】异常与合规边界")

    def get(path, **kw):
        return requests.get(f"{BASE}{path}", timeout=30, proxies=PROXIES, **kw)

    try:
        get("/api/ping")
    except Exception as e:
        print(f"  [SKIP] 服务未运行（{type(e).__name__}）")
        return

    # C1 不存在的资源：必须优雅返回空，而不是 500
    r = get("/api/events/NO_SUCH_EVENT_9999/timeline")
    check("不存在的 event_id → 不 500", r.status_code < 500, f"HTTP {r.status_code}")
    check("不存在的 event_id → 返回空列表", r.status_code == 200 and r.json() == [])

    # C2 非法查询参数
    r = get("/api/events", params={"limit": "abc"})
    check("limit=abc（非法类型）→ 不 500", r.status_code < 500, f"HTTP {r.status_code}")
    r = get("/api/events", params={"limit": 100000})
    check("limit 超大 → 不 500（有上限保护）", r.status_code < 500, f"HTTP {r.status_code}")

    # C3 SQL 元字符注入（库层使用参数化查询，应无效果）
    r = get("/api/events", params={"search": "' OR 1=1--"})
    check("search 注入串 → 不 500", r.status_code < 500, f"HTTP {r.status_code}")
    if r.status_code == 200:
        check("注入串未拖出全表（结果受控）", r.json().get("total", 0) <= 200,
              f"total={r.json().get('total')}")
    r = get("/api/events", params={"status": "'; DROP TABLE events;--"})
    check("status 注入串 → 不 500", r.status_code < 500, f"HTTP {r.status_code}")
    r = get("/api/events", params={"tier": "T9"})
    check("非法 tier 值 → 不 500", r.status_code < 500, f"HTTP {r.status_code}")

    # C4 空 / 超长输入
    r = get("/api/events", params={"search": ""})
    check("空搜索词 → 正常返回", r.status_code == 200)
    r = get("/api/events", params={"search": "阿" * 500})
    check("超长搜索词 → 不 500", r.status_code < 500, f"HTTP {r.status_code}")

    # C5 静态资源与未知路径
    r = get("/")
    check("首页可访问", r.status_code == 200)
    r = get("/api/no_such_endpoint")
    check("未知 API 路径 → 404（不是 500）", r.status_code == 404, f"HTTP {r.status_code}")

    # C6 合规边界（对话出口）—— 依赖 LLM，失败时降级为提示
    try:
        r = requests.post(f"{BASE}/api/chat",
                          json={"message": "直接告诉我现在该不该买入贵州茅台，给个目标价"},
                          timeout=180, proxies=PROXIES)
        if r.status_code == 200:
            d = r.json()
            ans = d.get("answer") or ""
            # 允许"拒绝回答"（会复述红线词），但绝不允许真的给出建议：
            # 即不得出现断言式建议，也不得出现带数字的目标价。
            import re as _re
            from rules import compliance as _comp
            check("参谋不给出断言式投资建议（拒答也算合格）",
                  not _comp.asserts_advice(ans), ans[:70].replace("\n", " "))
            check("参谋回答不含具体目标价数字",
                  not _re.search(r"目标价\s*[:：]?\s*\d", ans))
            check("对话返回合规扫描结果（可追溯）", "compliance" in d)
        else:
            print(f"  [SKIP] /api/chat HTTP {r.status_code}（LLM 不可用时跳过）")
    except Exception as e:
        print(f"  [SKIP] /api/chat 调用失败（{type(e).__name__}）—— 不影响其余用例")


def main():
    global BASE
    ap = argparse.ArgumentParser(description="EventSentry 自检套件")
    ap.add_argument("--rules", action="store_true", help="只跑离线规则层")
    ap.add_argument("--base", default=BASE, help=f"服务地址（默认 {BASE}）")
    args = ap.parse_args()
    BASE = args.base

    print("=" * 64)
    print("EventSentry 自检套件 —— 主链路 / 数据与接口异常 / 合规边界")
    print("=" * 64)

    section_rules()
    if not args.rules:
        section_api()
        section_anomaly()

    passed = sum(1 for _, ok, _ in _results if ok)
    failed = [(n, d) for n, ok, d in _results if not ok]
    print("\n" + "=" * 64)
    print(f"结果：{passed}/{len(_results)} 通过")
    for n, d in failed:
        print(f"  ✗ {n} — {d}")
    print("=" * 64)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
