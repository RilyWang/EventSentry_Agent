/**
 * 扶摇（Fuyao）HTTP 客户端
 * 用于事件影响验证：行情、财务、估值数据
 */

import { env } from "./env";

const FUYAO_BASE_URL = process.env.FUYAO_BASE_URL || "https://api.fuyao.com/v1";
const FUYAO_API_KEY = process.env.FUYAO_API_KEY || "";

interface FuyaoResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface PriceChangeData {
  ticker: string;
  eventDate: string;
  days: number;
  preClose: number;
  postClose: number;
  changePercent: number;
  maxDrawdown: number;
  volumeRatio: number;
}

export interface FinancialIndicator {
  ticker: string;
  reportDate: string;
  indicators: Record<string, number>;
}

export interface CompanyProfile {
  ticker: string;
  name: string;
  industry: string;
  marketCap: number;
  peTtm: number;
  pb: number;
}

async function fuyaoRequest<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  if (!FUYAO_API_KEY) {
    throw new Error("FUYAO_API_KEY not configured");
  }

  const url = new URL(path, FUYAO_BASE_URL);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${FUYAO_API_KEY}`,
      "Content-Type": "application/json",
    },
  });

  if (!res.ok) {
    throw new Error(`Fuyao API error: ${res.status} ${res.statusText}`);
  }

  const json = (await res.json()) as FuyaoResponse<T>;
  if (json.code !== 0) {
    throw new Error(`Fuyao API error: ${json.message}`);
  }

  return json.data;
}

/**
 * 获取事件后 N 日股价变动
 */
export async function getPriceChange(
  ticker: string,
  eventDate: string,
  days: number = 5
): Promise<PriceChangeData> {
  try {
    return await fuyaoRequest<PriceChangeData>("/market/price-change", {
      ticker,
      eventDate,
      days,
    });
  } catch (err) {
    console.error(`[Fuyao] getPriceChange failed for ${ticker}:`, err);
    // 返回 mock 数据，确保流程不中断
    return {
      ticker,
      eventDate,
      days,
      preClose: 100,
      postClose: 100,
      changePercent: 0,
      maxDrawdown: 0,
      volumeRatio: 1,
    };
  }
}

/**
 * 获取财务指标
 */
export async function getFinancialIndicator(
  ticker: string,
  indicators: string[] = ["revenue", "netProfit", "roe", "grossMargin"]
): Promise<FinancialIndicator> {
  try {
    return await fuyaoRequest<FinancialIndicator>("/finance/indicators", {
      ticker,
      indicators: indicators.join(","),
    });
  } catch (err) {
    console.error(`[Fuyao] getFinancialIndicator failed for ${ticker}:`, err);
    return {
      ticker,
      reportDate: new Date().toISOString().split("T")[0],
      indicators: {},
    };
  }
}

/**
 * 获取公司基本资料
 */
export async function getCompanyProfile(ticker: string): Promise<CompanyProfile> {
  try {
    return await fuyaoRequest<CompanyProfile>("/company/profile", { ticker });
  } catch (err) {
    console.error(`[Fuyao] getCompanyProfile failed for ${ticker}:`, err);
    return {
      ticker,
      name: ticker,
      industry: "未知",
      marketCap: 0,
      peTtm: 0,
      pb: 0,
    };
  }
}

/**
 * 批量验证事件影响（Analyst Agent 调用）
 * 返回事件后 1/3/5/10 日的涨跌幅
 */
export async function verifyEventImpact(
  ticker: string,
  eventDate: string
): Promise<{ d1: number; d3: number; d5: number; d10: number }> {
  const results = await Promise.all([
    getPriceChange(ticker, eventDate, 1),
    getPriceChange(ticker, eventDate, 3),
    getPriceChange(ticker, eventDate, 5),
    getPriceChange(ticker, eventDate, 10),
  ]);

  return {
    d1: results[0].changePercent,
    d3: results[1].changePercent,
    d5: results[2].changePercent,
    d10: results[3].changePercent,
  };
}
