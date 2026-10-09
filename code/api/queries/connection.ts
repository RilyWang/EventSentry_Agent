import { drizzle } from "drizzle-orm/mysql2";
import mysql from "mysql2/promise";
import { env } from "../lib/env";
import * as schema from "@db/schema";
import * as relations from "@db/relations";

const fullSchema = { ...schema, ...relations };

let instance: ReturnType<typeof drizzle<typeof fullSchema>>;
let connection: mysql.Connection;

export async function createConnection() {
  if (!connection) {
    connection = await mysql.createConnection(env.databaseUrl);
  }
  return connection;
}

export function getDb() {
  if (!instance) {
    // 开发模式下延迟连接，避免启动时崩溃
    if (!env.databaseUrl && !env.isProduction) {
      console.warn("[DB] DATABASE_URL not set, using mock mode");
    }
    instance = drizzle(env.databaseUrl || "mysql://root:root@localhost:3306/eventsentry", {
      mode: "planetscale",
      schema: fullSchema,
    });
  }
  return instance;
}
