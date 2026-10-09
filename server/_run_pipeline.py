"""运行完整流水线：采集 Agent → 分析 Agent"""
import os
import sys
import json

os.environ["no_proxy"] = "*"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents"))

from collector_agent import CollectorAgent
from analyst_agent import AnalystAgent

print("=" * 60)
print("① 采集 Agent（Collector）")
print("=" * 60)
c = CollectorAgent()
collect_stats = c.collect(days=180)
print(json.dumps(collect_stats, ensure_ascii=False, indent=2))

print()
print("=" * 60)
print("② 分析 Agent（Analyst）")
print("=" * 60)
a = AnalystAgent()
analyst_stats = a.process_batch(limit=60)
print(json.dumps(analyst_stats, ensure_ascii=False, indent=2))
