import { useCallback, useEffect, useRef, useState } from "react";
import type { HoldingsReview, HoldingsReviewSummary } from "../../../../packages/contracts/generated/typescript/client";
import { useWorkspaceApi } from "../api";

const activeStatuses = new Set(["QUEUED", "PLANNING", "RUNNING", "REVIEWING", "PAUSED"]);
const ruleNames = { stock: "个股仓位", etf: "单 ETF 仓位", sector: "股票行业集中度" };
const issueNames: Record<string, string> = {
  SESSION_CLOSED: "目标日期未开市。",
  CALENDAR_UNAVAILABLE: "交易日历暂不可核验。",
  PORTFOLIO_UNAVAILABLE: "请导入目标交易日或更早的持仓。",
  CASH_REQUIRED: "请补录账户现金，现金为零时请明确填写 0。",
  CLOSES_UNAVAILABLE: "部分持仓缺少目标交易日的有效收盘价。",
  HOLDINGS_INVALID: "持仓数量、标的类型或净值有误，请核对持仓。",
  SECTOR_UNAVAILABLE: "部分股票缺少行业归类，请在持仓中补录。",
};
const percent = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 2 });
const amount = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 });

function reviewStatus(review: HoldingsReview | null) {
  if (!review) return "待准备";
  if (activeStatuses.has(review.task_status)) return "正在准备";
  if (review.confirmed_at) return "已复核";
  const result = review.result;
  if (!result) return "准备失败";
  if (result.calculation === "empty") return "无持仓可复核";
  if (result.calculation === "incomplete") return "部分规则无法判断";
  if (review.replay) return "历史回放";
  return result.needs_confirmation ? "待确认持仓和现金" : "待人工复核";
}

function reviewError(error: unknown, fallback: string) {
  const text = error instanceof Error ? error.message : "";
  if (/HOLDINGS_(SNAPSHOT|RULES)_CHANGED/.test(text)) return "持仓、规则或目标交易日已更新。请核对后重新准备。";
  if (text.includes("HOLDINGS_REVIEW_NOT_READY")) return "请打开最新的完整结果后再复核。";
  if (text.includes("HOLDINGS_REVIEW_IN_PROGRESS")) return "正在准备上一份结果。完成后可以重新填写现金。";
  if (text.includes("HOLDINGS_INPUT_CONFIRMATION_REQUIRED")) return "请确认目标交易日的持仓数量和现金。";
  return fallback;
}

export function HoldingsReviewCard({ onOpenTask, onOpenPortfolio }: {
  onOpenTask: (id: string) => void;
  onOpenPortfolio: () => void;
}) {
  const api = useWorkspaceApi();
  const [summary, setSummary] = useState<HoldingsReviewSummary>();
  const [loadingError, setLoadingError] = useState("");
  const [actionError, setActionError] = useState("");
  const [cash, setCash] = useState("");
  const [editingCash, setEditingCash] = useState(false);
  const [pending, setPending] = useState(false);
  const request = useRef(0);

  const refresh = useCallback(async () => {
    const sequence = ++request.current;
    try {
      const value = await api.holdingsReview();
      if (sequence !== request.current) return;
      setSummary(value);
      setLoadingError("");
    } catch {
      if (sequence === request.current) setLoadingError("暂时无法读取收盘持仓复核。");
    }
  }, [api]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => {
      window.clearInterval(timer);
      request.current += 1;
    };
  }, [refresh]);

  async function prepare(withCash: boolean) {
    if (pending || !summary) return;
    const snapshotId = summary.portfolio_snapshot_id;
    if (withCash && (!snapshotId || !cash.trim() || !Number.isFinite(Number(cash)) || Number(cash) < 0)) {
      setActionError("请输入大于或等于零的现金余额。");
      return;
    }
    setPending(true);
    setActionError("");
    try {
      await api.startHoldingsReview(withCash && snapshotId
        ? { as_of: summary.as_of, portfolio_snapshot_id: snapshotId, cash: Number(cash) }
        : undefined);
      setEditingCash(false);
      setCash("");
      await refresh();
    } catch (error) {
      setActionError(reviewError(error, "准备复核失败，可以重试。"));
      await refresh();
    } finally {
      setPending(false);
    }
  }

  const attempt = summary?.attempt ?? null;
  const result = attempt?.result;
  const active = attempt ? activeStatuses.has(attempt.task_status) : false;
  const changed = Boolean(attempt && !active && summary?.portfolio_snapshot_id !== result?.portfolio_snapshot_id);
  const rulesChanged = Boolean(result && summary?.rule_snapshot_id !== result.rule_snapshot_id);
  const showPrepare = !attempt || changed || rulesChanged || (!active && (!result || result.calculation === "incomplete"));

  return <section className="panel holdings-review" aria-label="收盘持仓复核">
    <div className="holdings-review-heading">
      <h2>收盘持仓复核</h2>
      {summary && <strong role="status">{changed ? "持仓已更新" : rulesChanged ? "规则已更新" : reviewStatus(attempt)}</strong>}
    </div>
    {loadingError && <p role="alert">{loadingError} <button className="quiet-button" onClick={() => void refresh()}>重试读取</button></p>}
    {!summary && !loadingError && <p role="status">正在读取收盘复核…</p>}
    {summary && <>
      <p>交易日 {summary.as_of} · 持仓快照 {result?.portfolio_as_of ?? summary.portfolio_as_of ?? "暂无"}
        {result && <> · {result.data_mode === "fixture" ? "演示行情 " : "行情覆盖 "}{result.covered}/{result.total}</>}</p>
      {result?.checks && result.calculation !== "empty" && <ul className="holdings-review-checks">
        {result.checks.map((check) => <li key={check.kind}>{ruleNames[check.kind]} ·
          {check.status === "unavailable" ? "无法判断" : check.status === "clear" ? "未超限" : `${check.items.filter((item) => item.breach).length} 项超限`}</li>)}
      </ul>}
      {result?.issues.map((issue) => <p key={issue}>{issueNames[issue] ?? issue}</p>)}
      <div className="research-next-actions">
        {attempt && <button className="quiet-button" onClick={() => onOpenTask(attempt.task_id)}>查看结果与证据</button>}
        {summary.portfolio_snapshot_id && showPrepare && !active &&
          <button className="primary-button" disabled={pending} onClick={() => void prepare(false)}>
            {pending ? "正在提交…" : attempt && !changed ? "重试准备" : "准备收盘复核"}
          </button>}
        {summary.portfolio_snapshot_id && !active && !editingCash &&
          <button className="quiet-button" disabled={pending} onClick={() => setEditingCash(true)}>
            {result?.cash == null || changed ? "填写账户现金" : "更正账户现金"}
          </button>}
        {(!summary.portfolio_snapshot_id || result?.needs_confirmation || result?.issues.includes("SECTOR_UNAVAILABLE")) &&
          <button className="quiet-button" onClick={onOpenPortfolio}>{summary.portfolio_snapshot_id ? "更新持仓" : "添加持仓"}</button>}
      </div>
      {editingCash && !active && <form className="quick-retrospective" onSubmit={(event) => {
        event.preventDefault();
        void prepare(true);
      }}>
        <label>目标交易日的账户现金（元）
          <input type="number" value={cash} onChange={(event) => setCash(event.target.value)}
            min="0" step="any" placeholder="如无现金，请填写 0" required disabled={pending} />
        </label>
        <div className="research-next-actions">
          <button className="primary-button" disabled={pending}>使用现金并准备复核</button>
          <button type="button" className="quiet-button" disabled={pending} onClick={() => setEditingCash(false)}>取消</button>
        </div>
      </form>}
      {actionError && <p role="alert">{actionError}</p>}
    </>}
  </section>;
}

export function HoldingsReviewResult({ review, onConfirmed, onOpenPortfolio, onRetry }: {
  review: HoldingsReview; onConfirmed: () => Promise<void>; onOpenPortfolio: () => void; onRetry: () => void;
}) {
  const api = useWorkspaceApi();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const result = review.result;
  const active = activeStatuses.has(review.task_status);
  const confirmable = !active && !review.confirmed_at && !review.replay
    && (result?.calculation === "breach" || result?.calculation === "clear");

  async function confirm() {
    if (pending) return;
    setPending(true);
    setError("");
    try {
      await api.confirmHoldingsReview(review.task_id, result?.needs_confirmation === true);
      await onConfirmed();
    } catch (error) {
      setError(reviewError(error, "保存复核确认失败，可以重试。"));
    } finally {
      setPending(false);
    }
  }

  return <section className="panel holdings-review" aria-label="持仓规则结果">
    <div className="holdings-review-heading"><h3>持仓规则结果</h3><strong role="status">{reviewStatus(review)}</strong></div>
    {!result && <p>{active ? "正在获取交易日历和持仓收盘价。" : "本次未生成规则结果。"}</p>}
    {result && <>
      <p>{result.data_mode === "fixture" ? "演示行情" : "行情覆盖"} {result.covered}/{result.total}
        {" · "}持仓快照 {result.portfolio_as_of ?? "暂无"}
        {" · "}现金 {result.cash === null ? "待填写" : amount.format(result.cash)}
        {" · "}净值 {result.nav === null ? "无法核定" : amount.format(result.nav)}</p>
      <p>规则版本 {result.rule_snapshot_id}</p>
      {result.issues.map((issue) => <p key={issue}>{issueNames[issue] ?? issue}</p>)}
      {result.calculation !== "empty" && <div className="holdings-rule-results">
        {result.checks.map((check) => <div key={check.kind}>
          <h4>{ruleNames[check.kind]} · 上限 {percent.format(check.limit)}</h4>
          {check.status === "unavailable" ? <p>无法判断</p> : check.items.length
            ? <ul>{check.items.map((item) => <li key={item.label}>{item.label} · {percent.format(item.actual)} · {item.breach ? "超限" : "未超限"}</li>)}</ul>
            : <p>无适用持仓</p>}
        </div>)}
      </div>}
      {result.positions.length > 0 && <details open>
        <summary>收盘估值依据</summary>
        <ul>{result.positions.map((item, index) => <li key={`${item.symbol}-${index}`}>
          {item.symbol} · {item.quantity === null ? "数量有误" : `${amount.format(item.quantity)} 股 / 份`}
          {item.close === null ? " · 缺收盘价" : ` × ${amount.format(item.close)} 元 · ${item.provider_id ?? "来源未知"}`}
          {item.observed_at && <> · <time dateTime={item.observed_at}>{new Date(item.observed_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</time></>}
          {!!item.failed_attempts?.length && <small> · 取数诊断 {item.failed_attempts.map((attempt) =>
            `${attempt.provider_id}（${attempt.reason ?? "失败"}）`).join("、")}</small>}
        </li>)}</ul>
      </details>}
    </>}
    <div className="research-next-actions">
      {confirmable && <button className="primary-button" disabled={pending} onClick={() => void confirm()}>
        {pending ? "正在保存…" : result?.needs_confirmation ? "确认持仓数量无变化和目标日现金" : "标记为已复核"}
      </button>}
      {!review.replay && (result?.needs_confirmation || result?.issues.includes("SECTOR_UNAVAILABLE")) &&
        <button className="quiet-button" onClick={onOpenPortfolio}>更新持仓</button>}
      {!review.replay && !active && (!result || result.calculation === "incomplete") &&
        <button className="quiet-button" onClick={onRetry}>返回复核入口</button>}
    </div>
    {error && <p role="alert">{error}</p>}
  </section>;
}
