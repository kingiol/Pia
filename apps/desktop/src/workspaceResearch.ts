import type { MarketWorkspace, Task, WorkspaceHealth } from "./api";

export const REPLAY_AS_OF = "2026-11-05";

export function isDemoMarket(market: MarketWorkspace | null) {
  return market?.source === "fixture" || market?.provider_id === "fixture";
}

export function reviewSession(health: WorkspaceHealth | null, market: MarketWorkspace | null) {
  if (health?.provider.provider_id === "fixture") {
    return { as_of: REPLAY_AS_OF, calendar_verified: true };
  }
  if (market?.review_session) return market.review_session;
  // Older runtimes do not expose a review session.
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: health?.scheduler?.timezone ?? "Asia/Shanghai",
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts().map(({ type, value }) => [type, value]));
  const day = new Date(`${parts.year}-${parts.month}-${parts.day}T00:00:00Z`);
  if (`${parts.hour}:${parts.minute}` < (health?.scheduler?.close_time ?? "15:05")) {
    day.setUTCDate(day.getUTCDate() - 1);
  }
  while ([0, 6].includes(day.getUTCDay())) day.setUTCDate(day.getUTCDate() - 1);
  return { as_of: day.toISOString().slice(0, 10), calendar_verified: false };
}

export function stockCode(value: string): string | undefined {
  const code = value.trim().toUpperCase();
  if (!/^\d{6}(?:\.(?:SH|SZ|BJ))?$/.test(code)) return;
  if (code.includes(".")) return code;
  if (/^(?:[48]|92)/.test(code)) return `${code}.BJ`;
  return `${code}.${/^[56]/.test(code) ? "SH" : "SZ"}`;
}

const activeStatuses = new Set(["QUEUED", "PLANNING", "RUNNING", "REVIEWING", "PAUSED"]);
const failedStatuses = new Set(["FAILED", "RETRYABLE", "TIMEOUT", "CANCELLED", "EXPIRED"]);

export function latestStockResearch(tasks: Task[]) {
  const latest = new Map<string, Task>();
  const active = new Map<string, Task>();
  for (const task of tasks) {
    if (task.trigger_type !== "StockResearch" || task.target._replay_of) continue;
    const code = stockCode(String(task.target.symbol ?? ""));
    if (!code) continue;
    if (activeStatuses.has(task.status) && !active.has(code)) active.set(code, task);
    const previous = latest.get(code);
    if (!previous || (failedStatuses.has(previous.status) && !failedStatuses.has(task.status))) {
      latest.set(code, task);
    }
  }
  for (const [code, task] of active) latest.set(code, task);
  return latest;
}

export function taskTitle(task: Task, names?: ReadonlyMap<string, string>) {
  if (task.trigger_type === "MarketClose") return "收盘市场复盘";
  if (task.target.symbol) {
    const symbol = String(task.target.symbol);
    const name = names?.get(stockCode(symbol) ?? symbol);
    return name ? `${name} ${symbol} 研究` : `${symbol} 研究`;
  }
  return task.trigger_type;
}
