/**
 * Collector Agent — 事件采集调度器
 * 频率：每 5 分钟（cron）
 * 职责：调用 iFinD Python 脚本采集原始数据 → 写入 raw_messages
 */

import { execSync } from "child_process";
import { spawn } from "child_process";
import { resolve } from "path";
import { getDb } from "../api/queries/connection";
import { rawMessages } from "../db/schema";
import { eq } from "drizzle-orm";

const TICKERS = [
  "300750.SZ", // 宁德时代
  "002594.SZ", // 比亚迪
  "688981.SH", // 中芯国际
  "000858.SZ", // 五粮液
  "00700.HK",  // 腾讯控股
];

const SCRIPT_PATH = resolve(process.cwd(), "scripts/ifind_collector.py");

/**
 * 单次采集任务
 */
export async function runCollection(days: number = 3) {
  console.log(`[Collector] Starting collection at ${new Date().toISOString()}`);

  for (const ticker of TICKERS) {
    try {
      const result = await collectTicker(ticker, days);
      console.log(`[Collector] ${ticker} → ${result} messages`);
    } catch (err) {
      console.error(`[Collector] ${ticker} failed:`, err);
    }
  }

  // 统计未处理消息数
  const db = getDb();
  const unprocessed = await db.select().from(rawMessages).where(eq(rawMessages.processed, false));
  console.log(`[Collector] Unprocessed messages in queue: ${unprocessed.length}`);

  console.log(`[Collector] Done at ${new Date().toISOString()}`);
  return unprocessed.length;
}

/**
 * 调用 Python 脚本采集单个标的
 */
function collectTicker(ticker: string, days: number): Promise<number> {
  return new Promise((resolve, reject) => {
    const args = [SCRIPT_PATH, "--ticker", ticker, "--days", String(days)];
    const env = { ...process.env, PYTHONIOENCODING: "utf-8" };

    const child = spawn("python", args, { env, cwd: process.cwd() });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    child.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("close", (code) => {
      if (code !== 0) {
        console.error(`[Collector] Python stderr: ${stderr}`);
        // 即使 Python 失败，也尝试从 JSON 输出读取
      }

      // 解析输出中的插入数量
      const match = stdout.match(/Total messages:\s*(\d+)/);
      const count = match ? parseInt(match[1], 10) : 0;
      resolve(count);
    });

    child.on("error", (err) => {
      reject(err);
    });
  });
}

/**
 * 手动触发采集（用于 CLI 或 API 调用）
 */
export async function triggerManualCollection(tickers?: string[], days: number = 7) {
  const targets = tickers || TICKERS;
  let total = 0;

  for (const ticker of targets) {
    const count = await collectTicker(ticker, days);
    total += count;
  }

  return { total, tickers: targets };
}

// CLI 入口
if (import.meta.main) {
  const days = Number(process.argv[2]) || 3;
  runCollection(days).then(() => process.exit(0));
}
