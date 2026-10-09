"""
调度器 — 定时触发采集 Agent 与反思任务
不使用外部依赖（APScheduler 等），用 threading 实现最小可用调度。

周期：
  - 采集 Agent：每 COLLECT_INTERVAL_MIN 分钟（默认 30）
  - 分析 Agent：采集后立即触发一次（事件驱动）
  - 反思任务：每日 REFLECT_HOUR 点（默认 02:00）
"""
import os
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents"))

COLLECT_INTERVAL_MIN = int(os.getenv("COLLECT_INTERVAL_MIN", "30"))
REFLECT_HOUR = int(os.getenv("REFLECT_HOUR", "2"))


class Scheduler:
    def __init__(self):
        self._stop = threading.Event()
        self._threads = []
        self.state = {
            "collector": {"last_run": None, "last_result": None, "running": False},
            "analyst": {"last_run": None, "last_result": None, "running": False},
            "reflector": {"last_run": None, "last_result": None, "running": False},
        }

    # ─── 生命周期 ───
    def start(self):
        t1 = threading.Thread(target=self._loop_collect, daemon=True, name="collector-loop")
        t2 = threading.Thread(target=self._loop_reflect, daemon=True, name="reflector-loop")
        self._threads = [t1, t2]
        t1.start()
        t2.start()
        print(f"[Scheduler] 已启动：采集每 {COLLECT_INTERVAL_MIN} 分钟，反思每日 {REFLECT_HOUR:02d}:00")

    def stop(self):
        self._stop.set()

    # ─── 采集循环 ───
    def _loop_collect(self):
        # 启动后是否立即跑一次（默认：否，避免与手动流水线/首次部署冲突）
        # 设 SCHEDULER_RUN_ON_START=1 可开启
        if os.getenv("SCHEDULER_RUN_ON_START", "0") == "1":
            self.run_collect_and_analyze()
        while not self._stop.is_set():
            if self._stop.wait(COLLECT_INTERVAL_MIN * 60):
                break
            self.run_collect_and_analyze()

    # ─── 反思循环 ───
    def _loop_reflect(self):
        while not self._stop.is_set():
            now = datetime.now()
            # 计算到下一个反思时刻的秒数
            target = now.replace(hour=REFLECT_HOUR, minute=0, second=0, microsecond=0)
            if target <= now:
                from datetime import timedelta
                target = target + timedelta(days=1)
            wait_s = (target - now).total_seconds()
            print(f"[Scheduler] 下次反思：{target.strftime('%Y-%m-%d %H:%M')}")
            if self._stop.wait(wait_s):
                break
            self.run_reflection()

    # ─── 手动/定时执行 ───
    def run_collect_and_analyze(self):
        if self.state["collector"]["running"]:
            return {"skipped": True, "reason": "collector already running"}
        self.state["collector"]["running"] = True
        try:
            from collector_agent import CollectorAgent
            from analyst_agent import AnalystAgent
            from media_search_collector import MediaSearchCollector

            lookback = int(os.getenv("COLLECT_LOOKBACK_DAYS", "30"))

            # ① 官方公告（iFinD → T0）
            c = CollectorAgent()
            cres = c.collect(days=lookback)

            # ② 媒体 / 传闻（Serper → T1/T2/T3）
            mres = {}
            if os.getenv("ENABLE_MEDIA_SEARCH", "1") == "1":
                try:
                    mres = MediaSearchCollector().collect(days=max(lookback, 180))
                except Exception as e:
                    print(f"[Scheduler] 媒体搜索失败: {str(e)[:120]}")

            self.state["collector"]["last_run"] = datetime.now().isoformat()
            self.state["collector"]["last_result"] = {"ifind": cres, "websearch": mres}

            self.state["analyst"]["running"] = True
            a = AnalystAgent()
            ares = a.process_batch(limit=60)
            self.state["analyst"]["last_run"] = datetime.now().isoformat()
            self.state["analyst"]["last_result"] = ares
            self.state["analyst"]["running"] = False

            return {"collector": cres, "analyst": ares}
        except Exception as e:
            print(f"[Scheduler] 采集/分析失败: {type(e).__name__}: {e}")
            return {"error": str(e)}
        finally:
            self.state["collector"]["running"] = False
            self.state["analyst"]["running"] = False

    def run_reflection(self):
        if self.state["reflector"]["running"]:
            return {"skipped": True}
        self.state["reflector"]["running"] = True
        try:
            from reflector import Reflector
            r = Reflector().run()
            self.state["reflector"]["last_run"] = datetime.now().isoformat()
            self.state["reflector"]["last_result"] = r
            return r
        except Exception as e:
            print(f"[Scheduler] 反思失败: {type(e).__name__}: {e}")
            return {"error": str(e)}
        finally:
            self.state["reflector"]["running"] = False


scheduler = Scheduler()
