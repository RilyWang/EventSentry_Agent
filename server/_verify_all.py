import os, re, json
os.environ["no_proxy"] = "*"; os.environ["NO_PROXY"] = "*"
import requests

LOCAL = "http://localhost:3000"
PUBLIC = "https://watson-wanting-dream-examinations.trycloudflare.com"
S = {"http": None, "https": None}

print("=" * 62)
print("三端一致性核验")
print("=" * 62)

for label, base in [("本地", LOCAL), ("公网", PUBLIC)]:
    print(f"\n【{label}】{base}")
    try:
        h = requests.get(base + "/", timeout=45, proxies=S)
        ver = re.findall(r"\?v=([a-z0-9]+)", h.text)
        print(f"  首页 HTTP {h.status_code} | 资源版本 {set(ver)}")
        feats = {
            "头部搜索框": "header-search" in h.text,
            "发现页默认高亮": 'nav-item active" data-tab="discover"' in h.text,
            "状态筛选栏": "status-filters" in h.text,
            "只看关注按钮": "feed-followed" in h.text,
            "我的关注区块": "subscribed-list" in h.text,
            "订阅星号": 'id="detail-bookmark"' in h.text,
            "通知铃铛": 'id="notif-btn"' in h.text,
            "无限滚动容器": 'id="feed-end"' in h.text,
        }
        for k, v in feats.items():
            print(f"    {'✅' if v else '❌'} {k}")

        css = requests.get(base + "/style.css?v=20261009h", timeout=45, proxies=S).text
        styles = {
            "同花顺红主色": "--primary: #E5333D" in css,
            "红涨绿跌": "--up: #E64545" in css and "--down: #00A870" in css,
            "Toast提示": "#toast-box" in css,
            "已关注角标": ".followed-tag" in css,
            "订阅星号黄色": ".bookmark-btn.subscribed" in css,
            "我的关注列表": ".sub-item-main" in css,
            "全屏弹层": "100dvh" in css,
        }
        for k, v in styles.items():
            print(f"    {'✅' if v else '❌'} {k}")

        api = {
            "/api/ping": 0,
            "/api/events": 0,
            "/api/agents/status": 0,
            "/api/tickers": 0,
            "/api/subscriptions": 0,
            "/api/subscriptions/events": 0,
            "/api/notifications": 0,
            "/api/holdings": 0,
            "/api/preferences": 0,
        }
        ok = 0
        for p in api:
            try:
                r = requests.get(base + p, timeout=45, proxies=S)
                if r.status_code == 200: ok += 1
            except Exception:
                pass
        print(f"    {'✅' if ok == len(api) else '⚠️'} API 接口 {ok}/{len(api)} 正常")
    except Exception as e:
        print(f"  ❌ 不可达: {type(e).__name__} {str(e)[:90]}")

print("\n" + "=" * 62)
print("数据一致性")
print("=" * 62)
try:
    l = requests.get(LOCAL + "/api/events?limit=1", timeout=30, proxies=S).json()
    p = requests.get(PUBLIC + "/api/events?limit=1", timeout=45, proxies=S).json()
    print(f"  本地事件 {l['total']} vs 公网事件 {p['total']} → {'✅ 一致' if l['total']==p['total'] else '⚠️ 不一致'}")
    print(f"  状态分布: {json.dumps(l.get('status_counts',{}), ensure_ascii=False)}")

    t = requests.get(PUBLIC + "/api/tickers", timeout=45, proxies=S).json()
    print(f"  关注标的: {t['total']} 个 → {[x['ticker_name'] for x in t['items']]}")
    sub = requests.get(PUBLIC + "/api/subscriptions/events", timeout=45, proxies=S).json()
    print(f"  关注事件: {sub['total']} 个 | 关注股票: {sub['ticker_count']}")
except Exception as e:
    print("  ❌", type(e).__name__, str(e)[:90])
