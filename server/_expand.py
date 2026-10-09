"""扩充采集：多标的 + 长回溯，用于把发现页信息流做厚"""
import os
import sys
import json

os.environ["no_proxy"] = "*"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents"))

from collector_agent import CollectorAgent, TRACKED_TICKERS

print(f"跟踪标的数: {len(TRACKED_TICKERS)}")
c = CollectorAgent()
stats = c.collect(days=180)
print(json.dumps(stats, ensure_ascii=False, indent=2))
