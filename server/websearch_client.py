"""
Serper (Google Search API) 客户端
用途：为媒体/传闻层证据提供**全自动**的搜索能力，不再依赖人工核实。
接口：https://google.serper.dev/{search|news}
"""
import os

os.environ.setdefault("no_proxy", "*")
os.environ.setdefault("NO_PROXY", "*")

import warnings
import requests

# 从 .env 读取密钥（.env 已被 .gitignore 排除）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

warnings.filterwarnings("ignore")

SERPER_BASE = "https://google.serper.dev"

# ─── 域名 → 证据层级（确定性规则表，优先级高于 LLM） ───
DOMAIN_TIER = [
    # T0 官方披露
    ("cninfo.com.cn", "T0"), ("sse.com.cn", "T0"), ("szse.cn", "T0"),
    ("hkexnews.hk", "T0"), ("csrc.gov.cn", "T0"), ("sseinfo.com", "T0"),
    # T1 权威媒体
    ("caixin.com", "T1"), ("stcn.com", "T1"), ("cnstock.com", "T1"),
    ("jiemian.com", "T1"), ("36kr.com", "T1"), ("nbd.com.cn", "T1"),
    ("chinanews.com", "T1"), ("cnr.cn", "T1"), ("xinhuanet.com", "T1"),
    ("people.com.cn", "T1"), ("yicai.com", "T1"), ("zqrb.cn", "T1"),
    ("cs.com.cn", "T1"), ("cctv.com", "T1"), ("guancha.cn", "T1"),
    ("cls.cn", "T1"), ("eeo.com.cn", "T1"), ("yicai.com", "T1"),
    ("wallstreetcn.com", "T1"), ("thepaper.cn", "T1"), ("21jingji.com", "T1"),
    ("stcn.com", "T1"), ("hexun.com", "T1"), ("中国证券报", "T1"),
    # T2 研报 / 数据平台
    ("hibor.com.cn", "T2"), ("lixinger.com", "T2"), ("yanbaolive.com", "T2"),
    ("dfcfw.com/report", "T2"), ("sina.com.cn/report", "T2"),
    # T3 传闻 / 社交
    ("guba.eastmoney.com", "T3"), ("xueqiu.com", "T3"), ("weibo.com", "T3"),
    ("zhihu.com", "T3"), ("toutiao.com", "T3"), ("baijiahao.baidu.com", "T3"),
    ("mp.weixin.qq.com", "T3"), ("tieba.baidu.com", "T3"), ("bilibili.com", "T3"),
]

# 自媒体/聚合平台（即使域名是门户，也降为 T3）
T3_HINTS = ["百家号", "头条", "自媒体", "股吧", "雪球", "微博", "知乎", "公众号", "企鹅号", "大鱼号"]


def classify_domain(url: str, source_name: str = "") -> str:
    """按域名/来源名判定证据层级"""
    u = (url or "").lower()
    s = source_name or ""
    for hint in T3_HINTS:
        if hint in s or hint in u:
            return "T3"
    for domain, tier in DOMAIN_TIER:
        if domain.lower() in u:
            return tier
    # 兜底：门户/未知 → T1（若明显是自媒体已在上面拦掉）
    if any(d in u for d in ["eastmoney.com", "sina.com.cn", "163.com", "qq.com",
                            "sohu.com", "ifeng.com", "hexun.com", "jrj.com.cn"]):
        return "T1"
    return "T3"


class SearchError(Exception):
    pass


class WebSearchClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("SERPER_API_KEY") or ""
        if not self.api_key:
            raise SearchError(
                "缺少 SERPER_API_KEY。请在 server/.env 中配置，或设置同名环境变量。"
            )

    def _post(self, path: str, payload: dict, timeout: int = 45):
        resp = requests.post(
            f"{SERPER_BASE}/{path}",
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            json=payload, timeout=timeout,
            proxies={"http": None, "https": None},
        )
        if resp.status_code != 200:
            raise SearchError(f"Serper HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def search(self, query: str, num: int = 10, gl: str = "cn", hl: str = "zh-cn", tbs: str = None):
        """网页搜索 → [{title, link, snippet, date, source}]；tbs 如 'qdr:y' 表示近一年"""
        payload = {"q": query, "gl": gl, "hl": hl, "num": num}
        if tbs:
            payload["tbs"] = tbs
        data = self._post("search", payload)
        out = []
        for it in (data.get("organic") or []):
            out.append({
                "title": it.get("title", ""),
                "link": it.get("link", ""),
                "snippet": it.get("snippet", ""),
                "date": it.get("date", ""),
                "source": it.get("source", ""),
            })
        return out

    def news(self, query: str, num: int = 10, gl: str = "cn", hl: str = "zh-cn"):
        """新闻搜索 → [{title, link, snippet, date, source}]"""
        data = self._post("news", {"q": query, "gl": gl, "hl": hl, "num": num})
        out = []
        for it in (data.get("news") or []):
            out.append({
                "title": it.get("title", ""),
                "link": it.get("link", ""),
                "snippet": it.get("snippet", ""),
                "date": it.get("date", ""),
                "source": it.get("source", ""),
            })
        return out


if __name__ == "__main__":
    c = WebSearchClient()
    print("=== search ===")
    for r in c.search("宁德时代 澄清 传闻", 5):
        print(f"  [{classify_domain(r['link'], r['source'])}] {r['title'][:60]} | {r['link'][:55]}")
    print("\n=== news ===")
    for r in c.news("五粮液 传闻", 5):
        print(f"  [{classify_domain(r['link'], r['source'])}] {r['title'][:60]} | {r['date']} | {r['source']}")
