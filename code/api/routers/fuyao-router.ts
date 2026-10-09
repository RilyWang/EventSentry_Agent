import { z } from "zod";
import { createRouter, publicQuery } from "../middleware";
import {
  getPriceChange,
  getFinancialIndicator,
  getCompanyProfile,
  verifyEventImpact,
} from "../lib/fuyao";

export const fuyaoRouter = createRouter({
  /**
   * 获取事件后 N 日股价变动
   */
  priceChange: publicQuery
    .input(
      z.object({
        ticker: z.string(),
        eventDate: z.string(), // YYYY-MM-DD
        days: z.number().min(1).max(30).default(5),
      })
    )
    .query(async ({ input }) => {
      return getPriceChange(input.ticker, input.eventDate, input.days);
    }),

  /**
   * 获取财务指标
   */
  financialIndicator: publicQuery
    .input(
      z.object({
        ticker: z.string(),
        indicators: z.array(z.string()).optional(),
      })
    )
    .query(async ({ input }) => {
      return getFinancialIndicator(input.ticker, input.indicators);
    }),

  /**
   * 获取公司基本资料
   */
  companyProfile: publicQuery
    .input(z.object({ ticker: z.string() }))
    .query(async ({ input }) => {
      return getCompanyProfile(input.ticker);
    }),

  /**
   * 批量验证事件影响（1/3/5/10日）
   */
  verifyImpact: publicQuery
    .input(
      z.object({
        ticker: z.string(),
        eventDate: z.string(),
      })
    )
    .query(async ({ input }) => {
      return verifyEventImpact(input.ticker, input.eventDate);
    }),
});
