"""
媒体证据回放器 —— 补齐 T1（媒体）/ T2（研报）/ T3（传闻）层证据
用途：iFinD 新闻接口返回为空，无法提供 T1/T2/T3 文本证据。
      本模块把「经 WebSearch 核实的真实媒体报道」，按**时间顺序**回放给状态机，
      从而完整演示事件从「传闻 → 媒体验证 → 官方确认 → 官方否认 / 实质落地」的演化链。

数据真实性：
  下列每条证据均标注真实来源（媒体名 / 平台）与真实日期，来自公开可核查的报道。
  本模块不含任何虚构内容。

流程：
  按日期分组 → 逐组交给 rules/state_machine 裁决 → 每组生成一个版本快照 → 触发通知
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import get_db, init_db
from rules import state_machine as sm

# ═══════════════════════════════════════════════════════════════
# 真实案例数据（来源：公开媒体报道，经 WebSearch 核实）
# ═══════════════════════════════════════════════════════════════
CASES = [
    # ── 案例 1：腾讯微信 AI「小微」—— 完整正向链：传闻 → 媒体验证 → 官方确认 ──
    {
        "event_id": "00700_HK_AI进展",
        "ticker": "00700.HK",
        "ticker_name": "腾讯控股",
        "theme": "AI进展",
        "nature_hint": "positive",
        "items": [
            {"date": "2026-03-02", "tier": "T3", "evidence_type": "rumor", "semantics": "neutral",
             "source": "市场传闻（科技媒体转载）",
             "title": "消息称腾讯正研发微信独立自有 AI 大模型，预计 2026 年对外落地",
             "url": "https://www.36kr.com"},
            {"date": "2026-03-18", "tier": "T1", "evidence_type": "fact", "semantics": "neutral",
             "source": "腾讯控股财报电话会（媒体纪要）",
             "title": "刘炽平：微信平台天然具备承载 AI 智能体的多重优势，但推出尚无特定时间表",
             "url": "https://www.yicai.com"},
            {"date": "2026-06-15", "tier": "T1", "evidence_type": "fact", "semantics": "neutral",
             "source": "界面新闻",
             "title": "微信内测 AI 智能体「小微」，入口覆盖公众号消息总结、朋友圈文案生成等场景",
             "url": "https://www.jiemian.com"},
            {"date": "2026-06-15", "tier": "T1", "evidence_type": "fact", "semantics": "neutral",
             "source": "36氪",
             "title": "微信「小微」启动小范围灰度测试，底层由自研大模型 WeLM 驱动",
             "url": "https://www.36kr.com"},
            {"date": "2026-08-12", "tier": "T0", "evidence_type": "fact", "semantics": "confirm",
             "source": "腾讯控股 2026 年 Q2 财报",
             "title": "Q2 财报首次披露微信 AI 智能体「小微」，确认已启动小范围灰度测试",
             "url": "https://www.tencent.com/zh-cn/investors.html"},
        ],
    },

    # ── 案例 2：中芯国际 406 亿收购中芯北方 —— 官方确认 → 实质落地 ──
    {
        "event_id": "688981_SH_并购重组",
        "ticker": "688981.SH",
        "ticker_name": "中芯国际",
        "theme": "并购重组",
        "nature_hint": "positive",
        "items": [
            {"date": "2026-02-25", "tier": "T0", "evidence_type": "fact", "semantics": "confirm",
             "source": "中芯国际公告（上交所受理）",
             "title": "拟发行股份购买中芯北方 49% 股权（作价约 406.01 亿元），交易获上交所受理",
             "url": "http://www.sse.com.cn"},
            {"date": "2026-05-12", "tier": "T0", "evidence_type": "fact", "semantics": "substance",
             "source": "中芯国际公告 2026-015",
             "title": "发行股份购买资产获上交所并购重组审核委员会审议通过",
             "url": "http://www.sse.com.cn"},
            {"date": "2026-05-21", "tier": "T0", "evidence_type": "fact", "semantics": "substance",
             "source": "中芯国际公告 2026-021（证监许可〔2026〕1209号）",
             "title": "收到中国证监会同意注册批复，持股将由 51% 提升至 100% 全资控股",
             "url": "http://www.csrc.gov.cn"},
        ],
    },

    # ── 案例 3：五粮液收购传闻 —— 传闻 → 官方否认 ──
    {
        "event_id": "000858_SZ_并购重组",
        "ticker": "000858.SZ",
        "ticker_name": "五粮液",
        "theme": "并购重组",
        "nature_hint": "negative",
        "items": [
            {"date": "2026-02-18", "tier": "T3", "evidence_type": "rumor", "semantics": "neutral",
             "source": "深交所互动易（投资者提问）",
             "title": "投资者提问：听说泸州老窖要收购五粮液",
             "url": "https://irm.cninfo.com.cn"},
            {"date": "2026-02-19", "tier": "T0", "evidence_type": "fact", "semantics": "deny",
             "source": "五粮液董秘回复（深交所互动易）",
             "title": "五粮液董秘明确回复：不属实，感谢关注！",
             "url": "https://irm.cninfo.com.cn"},
            {"date": "2026-02-19", "tier": "T1", "evidence_type": "fact", "semantics": "deny",
             "source": "证券之星",
             "title": "五粮液否认被泸州老窖收购传闻",
             "url": "https://www.stockstar.com"},
        ],
    },

    # ── 案例 4：比亚迪被约谈传闻 —— 传闻 → 官方辟谣 ──
    {
        "event_id": "002594_SZ_监管问询",
        "ticker": "002594.SZ",
        "ticker_name": "比亚迪",
        "theme": "监管问询",
        "nature_hint": "negative",
        "items": [
            {"date": "2026-05-08", "tier": "T3", "evidence_type": "rumor", "semantics": "neutral",
             "source": "网络传言",
             "title": "网传「比亚迪被约谈、立案」",
             "url": ""},
            {"date": "2026-05-09", "tier": "T0", "evidence_type": "fact", "semantics": "deny",
             "source": "比亚迪网络举报中心（官方声明）",
             "title": "比亚迪官方澄清：网传「被约谈、立案」纯属虚假谣言，已取证将依法追责",
             "url": "https://www.byd.com"},
            {"date": "2026-05-09", "tier": "T1", "evidence_type": "fact", "semantics": "deny",
             "source": "央广网",
             "title": "比亚迪澄清：网传「被约谈、立案」系不实信息",
             "url": "https://www.cnr.cn"},
            {"date": "2026-05-09", "tier": "T1", "evidence_type": "fact", "semantics": "deny",
             "source": "证券时报",
             "title": "比亚迪：网传「比亚迪被约谈」不实",
             "url": "https://www.stcn.com"},
        ],
    },

    # ── 案例 5：宁德时代固态电池 —— 自媒体传闻 → 机构辟谣（媒体验证） ──
    {
        "event_id": "300750_SZ_技术进展",
        "ticker": "300750.SZ",
        "ticker_name": "宁德时代",
        "theme": "技术进展",
        "nature_hint": "risk",
        "items": [
            {"date": "2026-07-07", "tier": "T3", "evidence_type": "rumor", "semantics": "neutral",
             "source": "自媒体传闻",
             "title": "传宁德时代宜宾「全球首条全固态电池规模化量产产线」首期投产，规划产能 15GWh",
             "url": ""},
            {"date": "2026-07-08", "tier": "T1", "evidence_type": "opinion", "semantics": "neutral",
             "source": "上海有色网（SMM）",
             "title": "SMM 调研判断：该 15GWh 全固态量产线消息大概率系自媒体编造，无官方公告佐证",
             "url": "https://www.smm.cn"},
            {"date": "2026-07-08", "tier": "T1", "evidence_type": "fact", "semantics": "neutral",
             "source": "财经媒体（曾毓群达沃斯发言转载）",
             "title": "曾毓群：全固态电池技术成熟度仅 TRL-4 级，2030 年前难大规模装车",
             "url": "https://www.stcn.com"},
            {"date": "2026-07-29", "tier": "T0", "evidence_type": "fact", "semantics": "neutral",
             "source": "宁德时代（深交所互动易回复）",
             "title": "董秘回复：产品和技术相关信息请参考公开信息，感谢您的关注",
             "url": "https://irm.cninfo.com.cn"},
        ],
    },

    # ── 案例 6：九阳股份 —— 蹭热点传闻 → 澄清否认 ──
    {
        "event_id": "002242_SZ_战略合作",
        "ticker": "002242.SZ", "ticker_name": "九阳股份", "theme": "战略合作",
        "nature_hint": "negative",
        "items": [
            {"date": "2026-09-29", "tier": "T3", "evidence_type": "rumor", "semantics": "neutral",
             "source": "市场传闻（股吧/自媒体）",
             "title": "传九阳股份与华为达成战略合作，相关概念遭热炒，股价连续涨停",
             "url": ""},
            {"date": "2026-10-08", "tier": "T0", "evidence_type": "fact", "semantics": "deny",
             "source": "九阳股份（股票交易异常波动公告）",
             "title": "澄清：公司与华为不存在市场传闻所称的战略合作关系；关联系双方均持有深思考股权",
             "url": "http://www.cninfo.com.cn"},
            {"date": "2026-10-08", "tier": "T1", "evidence_type": "fact", "semantics": "deny",
             "source": "证券时报",
             "title": "九阳股份澄清：与华为不存在战略合作关系，提示估值风险",
             "url": "https://www.stcn.com"},
        ],
    },

    # ── 案例 7：兴业股份 —— 题材误传 → 澄清 ──
    {
        "event_id": "603928_SH_技术进展",
        "ticker": "603928.SH", "ticker_name": "兴业股份", "theme": "技术进展",
        "nature_hint": "negative",
        "items": [
            {"date": "2026-10-08", "tier": "T3", "evidence_type": "rumor", "semantics": "neutral",
             "source": "市场传闻（涨停概念炒作）",
             "title": "传兴业股份半导体光刻胶用酚醛树脂已批量供货，股价两连板",
             "url": ""},
            {"date": "2026-10-09", "tier": "T0", "evidence_type": "fact", "semantics": "deny",
             "source": "兴业股份（股票交易异常波动公告）",
             "title": "澄清：半导体光刻胶用酚醛树脂仅处于送样测试阶段，尚未签订供货合同、未形成收入",
             "url": "http://www.cninfo.com.cn"},
        ],
    },

    # ── 案例 8：欧菲光 —— 高管传闻 → 严正声明否认 ──
    {
        "event_id": "002456_SZ_公司治理",
        "ticker": "002456.SZ", "ticker_name": "欧菲光", "theme": "公司治理",
        "nature_hint": "negative",
        "items": [
            {"date": "2026-09-21", "tier": "T3", "evidence_type": "rumor", "semantics": "neutral",
             "source": "网络平台虚假信息",
             "title": "网络流传涉及公司及新任董秘李茵的虚假言论",
             "url": ""},
            {"date": "2026-09-21", "tier": "T0", "evidence_type": "fact", "semantics": "deny",
             "source": "欧菲光（严正声明）",
             "title": "严正声明：相关言论纯属凭空捏造、毫无事实依据，保留追究法律责任的权利",
             "url": "http://www.cninfo.com.cn"},
        ],
    },

    # ── 案例 9：贵州茅台 —— 多则传闻 → 官方辟谣 ──
    {
        "event_id": "600519_SH_公司治理",
        "ticker": "600519.SH", "ticker_name": "贵州茅台", "theme": "公司治理",
        "nature_hint": "negative",
        "items": [
            {"date": "2026-01-29", "tier": "T3", "evidence_type": "rumor", "semantics": "neutral",
             "source": "市场传闻（股吧/自媒体）",
             "title": "传茅台出资 SpaceX、开设名酒体验会所招商，白酒板块异动",
             "url": ""},
            {"date": "2026-01-30", "tier": "T0", "evidence_type": "fact", "semantics": "deny",
             "source": "贵州茅台（官方声明）",
             "title": "辟谣：公司从未开展任何名酒体验会所招募，也未出资相关项目，已向市场监管部门举报",
             "url": "http://www.moutaichina.com"},
        ],
    },

    # ── 案例 10：五粮液财报传闻 —— 仅传闻、无官方定性（长期停留"未证实"） ──
    {
        "event_id": "000858_SZ_定期报告",
        "ticker": "000858.SZ", "ticker_name": "五粮液", "theme": "定期报告",
        "nature_hint": "risk",
        "items": [
            {"date": "2026-04-20", "tier": "T3", "evidence_type": "rumor", "semantics": "neutral",
             "source": "自媒体（今日头条）",
             "title": "市场传闻五粮液「改报表」「业绩洗澡」，称年报及一季报披露延迟",
             "url": ""},
            {"date": "2026-04-28", "tier": "T3", "evidence_type": "speculation", "semantics": "neutral",
             "source": "股吧/财经自媒体",
             "title": "股吧推测：公司或提前与监管沟通，问询函迟迟未至",
             "url": ""},
        ],
    },
]


class MediaReplay:
    name = "MediaReplay"

    def run(self, cases=None) -> dict:
        init_db()
        cases = cases or CASES
        report = {"cases": [], "total_versions": 0, "total_transitions": 0}

        for case in cases:
            r = self._replay_case(case)
            report["cases"].append(r)
            report["total_versions"] += r["versions"]
            report["total_transitions"] += r["transitions"]

        return report

    # ─── 单个案例：按日期分组逐组回放 ───
    def _replay_case(self, case):
        db = get_db()
        cur = db.cursor()
        eid = case["event_id"]

        # 清空该事件已有数据（可重复运行）
        for tbl in ("events", "event_versions", "timeline_nodes", "evidence_items", "event_directions"):
            cur.execute(f"DELETE FROM {tbl} WHERE {'event_id' if tbl != 'events' else 'event_id'} = ?", (eid,))
        db.commit()

        # 按日期分组
        groups = {}
        for it in case["items"]:
            groups.setdefault(it["date"], []).append(it)
        dates = sorted(groups.keys())

        state_code = None
        state_label = None
        last_at = ""
        versions = 0
        transitions = 0
        chain = []

        for d in dates:
            items = groups[d]
            evidences = [
                sm.Evidence(tier=i["tier"], semantics=i["semantics"],
                            evidence_type=i["evidence_type"], publish_time=i["date"],
                            source=i["source"], summary=i["title"])
                for i in items
            ]
            last_at = max(last_at, d)

            # ★ 规则层裁决（确定性）
            # 关键：回放时 "now" 必须是**当批日期**（as-of），不能用真实当前时间，
            # 否则过期规则（Rule 10/11/13）会把历史事件误判为已过期。
            as_of = datetime.strptime(d, "%Y-%m-%d")
            tr = sm.arbitrate(state_code, evidences, last_evidence_at=last_at, now=as_of)

            # 事件主表
            if state_code is None:
                cur.execute("""
                    INSERT INTO events
                    (event_id, ticker, ticker_name, theme, headline, status, state_code, state_label,
                     nature, nature_label, event_time, disclosure_time, crawl_time, updated_at,
                     last_evidence_at, notification_level, timeline, evidence, directions, rumors)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '{}', '[]', '[]')
                """, (eid, case["ticker"], case["ticker_name"], case["theme"],
                      items[0]["title"][:120], tr.card_tag, tr.state_code, tr.state_label,
                      case.get("nature_hint", "neutral"),
                      {"positive": "利好", "negative": "利空", "risk": "风险"}.get(case.get("nature_hint"), "中性"),
                      dates[0], d, datetime.now().strftime("%Y-%m-%d"), d, last_at, tr.notification_level))
            else:
                cur.execute("""
                    UPDATE events SET status=?, state_code=?, state_label=?, headline=?,
                      updated_at=?, last_evidence_at=?, notification_level=?
                    WHERE event_id=?
                """, (tr.card_tag, tr.state_code, tr.state_label, items[-1]["title"][:120],
                      d, last_at, tr.notification_level, eid))

            # 证据
            for i in items:
                cur.execute("""
                    INSERT INTO evidence_items
                    (event_id, source, date, summary, tier, evidence_type, source_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (eid, i["source"], i["date"], i["title"][:300],
                      i["tier"], i["evidence_type"], i.get("url", "#")))

            # 时间线节点
            cur.execute("SELECT COALESCE(MAX(order_index), -1) FROM timeline_nodes WHERE event_id = ?", (eid,))
            idx = cur.fetchone()[0] + 1
            for k, i in enumerate(items):
                cur.execute("""
                    INSERT INTO timeline_nodes
                    (event_id, date, label, summary, tier, is_current, order_index)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (eid, i["date"], tr.card_tag, i["title"][:150], i["tier"],
                      1 if k == len(items) - 1 else 0, idx + k))

            # 版本快照
            cur.execute("SELECT COALESCE(MAX(version), 0) FROM event_versions WHERE event_id = ?", (eid,))
            ver = cur.fetchone()[0] + 1
            change_type = "deny" if tr.state_code == sm.OFFICIALLY_DENIED else \
                          "expire" if tr.state_code == sm.EXPIRED else \
                          "correct" if tr.is_correction else "update"
            cur.execute("""
                INSERT INTO event_versions
                (event_id, version, status, nature, headline, timeline_snapshot, evidence_snapshot,
                 directions_snapshot, change_type, change_reason, created_by, notification_level, rule_fired)
                VALUES (?, ?, ?, ?, ?, ?, '{}', '[]', ?, ?, 'media_replay', ?, ?)
            """, (eid, ver, tr.state_label, case.get("nature_hint", "neutral"),
                  items[-1]["title"][:120],
                  json.dumps([{"date": i["date"], "tier": i["tier"], "title": i["title"]} for i in items],
                             ensure_ascii=False),
                  change_type, f"[{tr.rule_id}] {tr.reason}", tr.notification_level, tr.rule_id))
            versions += 1

            # 通知
            if tr.changed and tr.notification_level:
                transitions += 1
                cur.execute("""
                    INSERT INTO notifications (user_id, event_id, type, title, content)
                    VALUES (1, ?, ?, ?, ?)
                """, (eid,
                      "denial" if tr.state_code == sm.OFFICIALLY_DENIED else "state_transition",
                      f"[{tr.notification_level}] {tr.state_label}",
                      f"{tr.rule_id}：{tr.reason}"))

            chain.append({"date": d, "rule": tr.rule_id,
                          "state": tr.state_code, "state_label": tr.state_label,
                          "changed": tr.changed})
            state_code = tr.state_code
            state_label = tr.state_label
            db.commit()

        db.close()
        return {"event_id": eid, "ticker_name": case["ticker_name"], "theme": case["theme"],
                "versions": versions, "transitions": transitions, "chain": chain}


if __name__ == "__main__":
    r = MediaReplay().run()
    print("=" * 66)
    print("媒体证据回放 —— 事件演化链")
    print("=" * 66)
    for c in r["cases"]:
        print(f"\n【{c['ticker_name']} · {c['theme']}】")
        for step in c["chain"]:
            mark = "★跃迁" if step["changed"] else "  补充"
            print(f"  {step['date']}  {mark}  [{step['rule'] or '——':8}] → {step['state_label']}")
    print(f"\n合计：{r['total_versions']} 个版本快照，{r['total_transitions']} 次状态跃迁")
