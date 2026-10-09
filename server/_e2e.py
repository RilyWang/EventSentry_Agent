"""端到端验证脚本"""
import os
import json
import requests

os.environ["no_proxy"] = "*"
B = "http://localhost:3000"


def show(title, fn):
    print(f"\n=== {title} ===")
    try:
        fn()
    except Exception as e:
        print("  ERROR:", type(e).__name__, str(e)[:200])


def t_agents():
    d = requests.get(f"{B}/api/agents/status", timeout=30).json()
    for name, a in d["agents"].items():
        print(f"  {name:12} | {a['model']:32} | {a['schedule']}")
    print("  数据:", json.dumps(d["data"], ensure_ascii=False))


def t_events():
    d = requests.get(f"{B}/api/events", params={"limit": 6}, timeout=30).json()
    print(f"  total={d['total']}")
    for e in d["items"]:
        print(f"    {e['ticker_name']:6} | {e['theme']:8} | {e['status']:8} | {e['nature_label']}")


def t_search():
    for kw in ["宁德时代", "定期报告", "比亚迪"]:
        d = requests.get(f"{B}/api/events", params={"search": kw, "limit": 3}, timeout=30).json()
        print(f"  搜索 {kw!r}: {d['total']} 条")


def t_detail():
    d = requests.get(f"{B}/api/events", params={"limit": 1}, timeout=30).json()
    eid = d["items"][0]["id"]
    for sub in ["timeline", "evidence", "versions"]:
        r = requests.get(f"{B}/api/events/{eid}/{sub}", timeout=30).json()
        print(f"    {sub}: {len(r)} 条")
    print(f"    样例事件: {eid}")


def t_stock_agent():
    """参谋查行情 —— 验证真实工具调用"""
    r = requests.post(f"{B}/api/chat",
                      json={"message": "宁德时代最近5天的股价表现如何？"},
                      timeout=300).json()
    print("  回答:", (r.get("answer") or "")[:250].replace("\n", " "))
    print("  工具:", [t["tool"] for t in r.get("tools_used", [])])
    print("  引用:", len(r.get("citations", [])), "条")


def t_notif():
    d = requests.get(f"{B}/api/notifications", timeout=30).json()
    print(f"  通知 {len(d['list'])} 条，未读 {d['unread_count']}")


show("① 多 Agent 状态", t_agents)
show("② 事件列表（来自真实 iFinD 数据）", t_events)
show("③ 搜索", t_search)
show("④ 事件详情（时间线/证据/版本）", t_detail)
show("⑤ 参谋 Agent 查行情（真实工具调用）", t_stock_agent)
show("⑥ 通知", t_notif)
