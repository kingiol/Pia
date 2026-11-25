import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import {
  ArrowClockwiseIcon,
  ArrowCounterClockwiseIcon,
  ArrowRightIcon,
  ArrowUpRightIcon,
  BellIcon,
  BookOpenTextIcon,
  BriefcaseIcon,
  ChartLineIcon,
  CheckIcon,
  CaretRightIcon,
  ClipboardTextIcon,
  DatabaseIcon,
  EyeIcon,
  ExportIcon,
  FloppyDiskIcon,
  HouseIcon,
  ListIcon,
  LinkSimpleIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  SlidersHorizontalIcon,
  TrashIcon,
  UserIcon,
  WarningCircleIcon,
  XIcon,
  type Icon,
} from "@phosphor-icons/react";
import { useWorkspaceApi, marketSyncStages, Evidence, JournalItem, JournalPatterns, JournalSummary, RuleResult, Task, TaskDataResponse, TaskDetail, TaskInput, TaskStatus, TraceRow, Watchlist } from "./api";
import { HoldingsReviewCard, HoldingsReviewResult } from "./components/HoldingsReview";
import type { CandidateListResponse, HistoricalAnomalyTask, LocalCredentialStatus, MarketAnomalies, MarketSyncProgress, MarketSyncStage, MarketWorkspace, Retrospective, RuleReason, SchedulerResponse, WorkspaceHealth } from "./api";
import { registerWebPushDevice } from "./push";
import { RunFlow } from "./components/RunFlow";
import { WorkspaceSearch } from "./components/WorkspaceSearch";
import { researchAgentLabel } from "./researchLabels";
import { isDemoMarket, latestStockResearch, REPLAY_AS_OF, reviewSession, stockCode, taskTitle } from "./workspaceResearch";
import demoPortfolio from "../../../tests/fixtures/portfolio/default.json";
import baselineRules from "../../../rules/baseline.yaml?raw";

const nav = [
  ["总览", "Overview", "overview"],
  ["市场", "Market", "market"],
  ["自选", "Watchlist", "watchlist"],
  ["持仓", "Portfolio", "portfolio"],
  ["研究", "Research", "research"],
  ["决策日志", "Journal", "journal"],
  ["设置", "Profile", "profile"],
  ["规则", "Rules", "rules"],
  ["数据", "Data Health", "data"],
  ["审计", "Audit", "audit"],
  ["通知", "Notifications", "notifications"],
] as const;

export type WorkspaceView = (typeof nav)[number][1];

const pageResources = {
  Overview: ["tasks", "rules", "market", "portfolio", "profile", "watchlists", "notifications"],
  Market: ["market", "watchlists"],
  Watchlist: ["watchlists", "tasks", "market"],
  Portfolio: ["portfolio"],
  Research: ["tasks", "market", "notifications"],
  Journal: ["journal", "journalSummary", "journalPatterns"],
  Profile: ["profile"],
  Rules: ["rules"],
  "Data Health": ["health", "market", "portfolio", "watchlists"],
  Audit: ["tasks"],
  Notifications: ["notifications"],
} as const satisfies Record<WorkspaceView, readonly string[]>;

type Resource = (typeof pageResources)[WorkspaceView][number];
type ResourceStatus = { error?: string };
type ActiveMarketSync = { asOf: string; startedAt: number };
type CommitResource = <T>(value: T, apply: (value: T) => void) => void;
type RetrospectiveInput = Pick<Retrospective, "action_taken" | "outcome"> & {
  notes?: string;
  observed_at?: string | null;
};
const primaryResource: Partial<Record<WorkspaceView, Resource>> = {
  Market: "market", Watchlist: "watchlists", Portfolio: "portfolio", Journal: "journal",
  Rules: "rules", "Data Health": "health", Audit: "tasks", Notifications: "notifications",
};

const DEFAULT_WATCHLIST = "Research watchlist";

const webRoutes: Record<WorkspaceView, string> = {
  Overview: "/overview",
  Market: "/market",
  Watchlist: "/watchlist",
  Portfolio: "/portfolio",
  Research: "/research",
  Journal: "/journal",
  Profile: "/profile",
  Rules: "/rules",
  "Data Health": "/data-health",
  Audit: "/audit",
  Notifications: "/alerts",
};

function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function viewFromWebPath(pathname: string): WorkspaceView {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  if (normalized.startsWith("/research/")) return "Research";
  return (Object.keys(webRoutes) as WorkspaceView[]).find((view) => webRoutes[view] === normalized) ?? "Overview";
}

function taskFromWebPath(pathname: string) {
  const match = pathname.match(/^\/research\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function friendlyError(error: unknown, fallback: string) {
  if (!(error instanceof Error)) return fallback;
  const raw = error.message.trim();
  if (!raw) return fallback;
  try {
    const payload = JSON.parse(raw) as { error?: string; message?: string; detail?: string };
    const code = payload.error ?? payload.message;
    if (code === "task_not_found") return "这条研究记录已不存在。";
    if (code === "unauthorized") return "云端工作区需要重新连接，请输入访问令牌。";
    if (code === "CapabilityUnavailable") return "所需数据暂不可用，请检查数据源后重试。";
    if (payload.detail === "PORTFOLIO_CHANGED") return "持仓快照已更新，请关闭表单，核对最新持仓后重试。";
    if (payload.detail === "PORTFOLIO_POSITION_EXISTS") return "这个代码已在持仓中。请在对应行点击「编辑」。";
    if (payload.detail === "PORTFOLIO_POSITION_AMBIGUOUS") return "这份快照有多条相同代码的记录。请合并这些记录后重新批量导入。";
    if (payload.detail === "INVALID_PORTFOLIO_SYMBOL") return "请输入 6 位股票或 ETF 代码。";
    if (payload.detail === "INVALID_PORTFOLIO_DATE") return "持仓日期不能早于当前快照。";
    if (payload.detail === "INVALID_PORTFOLIO_VALUES") return "请检查持有数量、平均成本和持仓总市值。";
    if (code) return /\p{Script=Han}/u.test(code) ? code : fallback;
  } catch {
    // The runtime may return a plain-text transport error.
  }
  if (/failed to fetch|networkerror|connection refused/i.test(raw)) {
    return "无法连接运行时，请检查所选环境的服务地址和网络后重试。";
  }
  if (/^(?:request failed:\s*)?(?:unauthorized|401)$/i.test(raw)) return "云端工作区需要重新连接，请输入访问令牌。";
  if (!/\p{Script=Han}/u.test(raw)) return fallback;
  return raw.length > 220 ? `${raw.slice(0, 217)}…` : raw;
}

function missingPortfolio(error: unknown) {
  if (!(error instanceof Error)) return false;
  try {
    return JSON.parse(error.message)?.error === "PORTFOLIO_AS_OF_UNAVAILABLE";
  } catch {
    return false;
  }
}

const DEFAULT_INVESTMENT_OBJECTIVE = "capital preservation with disciplined growth";
const DEFAULT_INVESTMENT_OBJECTIVE_LABEL = "稳健增值，优先控制回撤";

function displayInvestmentObjective(objective: string) {
  return objective === DEFAULT_INVESTMENT_OBJECTIVE ? DEFAULT_INVESTMENT_OBJECTIVE_LABEL : objective;
}

function shanghaiDate() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function taskInput(
  health: { provider?: { provider_id?: string } } | null,
  market: MarketWorkspace | null,
  requestedDate?: string,
): TaskInput {
  const demo = health?.provider?.provider_id === "fixture";
  const demoSnapshot = isDemoMarket(market);
  const asOf = requestedDate ?? (demo ? REPLAY_AS_OF : !demoSnapshot && typeof market?.as_of === "string" ? market.as_of : shanghaiDate());
  if (market?.as_of === asOf && market.quality === "verified" && typeof market.snapshot_id === "string" && demo === demoSnapshot) {
    return { asOf, marketSnapshotId: market.snapshot_id };
  }
  return demo ? { asOf, fixture: { market: `close-${asOf}.json` } } : { asOf };
}

function evidenceQuality(evidence: Evidence) {
  if (evidence.quality === "verified" && new Date(evidence.expires_at).getTime() <= Date.now()) return "stale";
  return evidence.quality;
}

function statusLabel(status: TaskStatus | string) {
  const labels: Record<string, string> = {
    RUNNING: "运行中",
    PLANNING: "规划中",
    REVIEWING: "审核中",
    PAUSED: "已暂停",
    WAITING_APPROVAL: "待处理",
    BLOCKED: "已阻断",
    NO_ACTION: "无动作",
    APPROVED: "已批准",
    REJECTED: "已拒绝",
    FAILED: "失败",
    RETRYABLE: "可重试",
    DONE: "完成",
    TIMEOUT: "超时",
    CANCELLED: "已取消",
    EXPIRED: "已过期",
    QUEUED: "排队中",
    PENDING: "待生成",
    WATCH: "观察",
    HOLD: "持有",
    BUY_CANDIDATE: "买入候选",
    SELL_CANDIDATE: "卖出候选",
  };
  return labels[status] ?? status;
}

const levelLabels: Record<string, string> = { low: "低", medium: "中", high: "高" };
const trendLabels: Record<string, string> = { up: "上涨", down: "下跌", flat: "横盘", "up or flat": "上涨或横盘" };
const qualityLabels: Record<string, string> = { verified: "已验证", partial: "部分验证", stale: "已过期", unavailable: "不可用", unknown: "未知" };
const healthLabels: Record<string, string> = { ok: "正常", healthy: "正常", local: "本地", cloud: "云端", degraded: "降级", unavailable: "不可用" };
const retrospectiveActionLabels = {
  NOT_TAKEN: "未采取行动", APPROVE: "采纳建议", REJECT: "拒绝建议", NO_ACTION: "暂不行动", OTHER: "其他行动",
};

function localizedLabel(labels: Record<string, string>, value: unknown, fallback = "—") {
  const key = String(value ?? fallback);
  return Object.hasOwn(labels, key) ? labels[key] : key;
}

function nextActionLabel(action: string) {
  return action === "Review evidence and unresolved research limitations."
    ? "核对证据与尚未解决的研究限制。"
    : action;
}

function StatusBadge({ status }: { status: TaskStatus | string }) {
  return <span className={`status status-${status.toLowerCase()}`}><i />{statusLabel(status)}</span>;
}

function EmptyState({ message }: { message: string }) {
  return <div className="empty-state"><span className="empty-mark">—</span><p>{message}</p></div>;
}

const navIcons: Record<(typeof nav)[number][2], Icon> = {
  overview: HouseIcon,
  market: ChartLineIcon,
  watchlist: EyeIcon,
  portfolio: BriefcaseIcon,
  research: MagnifyingGlassIcon,
  journal: BookOpenTextIcon,
  profile: UserIcon,
  rules: SlidersHorizontalIcon,
  data: DatabaseIcon,
  audit: ClipboardTextIcon,
  notifications: BellIcon,
};

function NavIcon({ name }: { name: (typeof nav)[number][2] }) {
  const Icon = navIcons[name];
  return <Icon className="nav-icon" size={16} weight="regular" aria-hidden="true" />;
}

type SetupState = {
  profile: boolean;
  portfolio: boolean;
  rules: boolean;
  data: boolean;
  review: boolean;
};

function SetupGuide({ setup, onNavigate, onCreateReview, onPreview, disabled, loadError, onRetry }: {
  setup: SetupState;
  onNavigate: (view: WorkspaceView) => void;
  onCreateReview: () => void;
  onPreview: () => void;
  disabled: boolean;
  loadError: boolean;
  onRetry: () => void;
}) {
  const steps = [
    { key: "profile" as const, title: "告诉 Pia 你的投资方式", description: "风险偏好、投资目标和可研究范围", action: "去设置", onClick: () => onNavigate("Profile") },
    { key: "portfolio" as const, title: "添加你的持仓", description: "逐条添加，或批量导入 CSV 和 Excel", action: "添加持仓", onClick: () => onNavigate("Portfolio") },
    { key: "rules" as const, title: "设置一条持仓规则", description: "为单只股票设置仓位上限", action: "设置规则", onClick: () => onNavigate("Rules") },
    { key: "data" as const, title: "确认数据准备好", description: "核对收盘行情日期和可用性", action: "检查数据", onClick: () => onNavigate("Data Health") },
    { key: "review" as const, title: "完成第一次收盘复盘", description: "Pia 会给出结论、依据和风险提示", action: "开始复盘", onClick: onCreateReview },
  ];
  const completed = steps.filter((step) => setup[step.key]).length;
  const next = steps.find((step) => !setup[step.key]);
  return <section className={`welcome-panel panel ${completed === steps.length ? "setup-complete" : ""}`}>
    <div className="welcome-copy">
      <span className="eyebrow">{completed === steps.length ? "准备就绪" : "首次设置"}</span>
      <h2>{completed === steps.length ? "研究准备已完成" : "准备你的研究工作台"}</h2>
      <p>按你的投资纪律研究，由你确认行动</p>
      <div className="onboarding-actions">
        <button className="quiet-button" onClick={onPreview}>体验演示复盘</button>
        {!setup.portfolio && <button className="quiet-button" onClick={() => onNavigate("Portfolio")}>添加我的持仓</button>}
      </div>
      {loadError && <p role="status">部分准备信息暂不可用。<button className="text-button" onClick={onRetry}>重新检查</button></p>}
      <progress className="setup-progress" value={completed} max={steps.length} aria-label="研究设置完成进度" />
      <small>{completed}/{steps.length} 已完成</small>
    </div>
    <div className="setup-steps">
      {steps.map((step, index) => <button className={`setup-step ${setup[step.key] ? "complete" : ""} ${next?.key === step.key ? "current" : ""}`} key={step.key} aria-current={next?.key === step.key ? "step" : undefined} disabled={step.key === "review" && disabled} onClick={step.onClick}>
        <span className="setup-number">{setup[step.key] ? <CheckIcon size={16} aria-hidden="true" /> : index + 1}</span>
        <span><strong>{step.title}</strong><small>{step.description}</small></span>
        <b>{setup[step.key] ? "已完成" : step.action}<ArrowRightIcon size={16} aria-hidden="true" /></b>
      </button>)}
    </div>
  </section>;
}

function LoginView({ onSubmit, error }: { onSubmit: (token: string) => void; error?: string | null }) {
  const [token, setToken] = useState("");
  return <main className="auth-shell">
    <section className="auth-panel panel">
      <div className="brand auth-brand"><span className="brand-mark">P</span><div><strong>Pia</strong><small>投资研究工作台</small></div></div>
      <span className="eyebrow">连接云端工作区</span>
      <h1>连接到你的 Pia</h1>
      <p className="auth-copy">输入管理员提供的访问令牌。使用本地桌面版时无需填写。</p>
      <input
        className="auth-input"
        type="password"
        value={token}
        placeholder="访问令牌"
        onChange={(event) => setToken(event.target.value)}
        onKeyDown={(event) => { if (event.key === "Enter" && token.trim()) onSubmit(token); }}
        autoFocus
      />
      {error && <p className="auth-error">{error}</p>}
      <button className="primary-button auth-submit" onClick={() => onSubmit(token)} disabled={!token.trim()}>连接</button>
    </section>
  </main>;
}

export function App({
  runtimeControl, runtimeReady = true, runtimeMode, runtimeHealth, runtimeError, onRuntimeRetry,
  workspaceView, onWorkspaceViewChange,
}: {
  runtimeControl?: ReactNode;
  runtimeReady?: boolean;
  runtimeMode?: "local" | "cloud";
  runtimeHealth?: WorkspaceHealth;
  runtimeError?: string;
  onRuntimeRetry?: () => void;
  workspaceView?: WorkspaceView;
  onWorkspaceViewChange?: (view: WorkspaceView) => void;
} = {}) {
  const api = useWorkspaceApi();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    if (typeof window === "undefined" || isTauriRuntime()) return null;
    return taskFromWebPath(window.location.pathname)
      ?? new URLSearchParams(window.location.search).get("task");
  });
  const selectedTaskRef = useRef(selectedId);
  const detailSequence = useRef({ requested: 0, applied: 0 });
  const [taskDetail, setDetail] = useState<TaskDetail | null>(null);
  const detail = taskDetail?.task.id === selectedId ? taskDetail : null;
  const [detailError, setDetailError] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(() => Boolean(selectedId));
  const [latestHealth, setHealth] = useState<WorkspaceHealth | null>(null);
  const [scheduler, setScheduler] = useState<SchedulerResponse>();
  const availableHealth = latestHealth ?? runtimeHealth ?? null;
  const health = scheduler && availableHealth ? { ...availableHealth, scheduler } : availableHealth;
  const [rules, setRules] = useState<Record<string, unknown> | null>(null);
  const [market, setMarket] = useState<MarketWorkspace | null>(null);
  const [portfolio, setPortfolio] = useState<Record<string, unknown> | null>(null);
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [candidateScan, setCandidateScan] = useState<{ key: string; result: CandidateListResponse } | null>(null);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [journalItems, setJournalItems] = useState<JournalItem[]>([]);
  const [journalSummary, setJournalSummary] = useState<JournalSummary | null>(null);
  const [journalPatterns, setJournalPatterns] = useState<JournalPatterns | null>(null);
  const [notifications, setNotifications] = useState<NotificationRow[]>([]);
  const unreadNotifications = notifications.filter((item) => !item.read_at).length;
  const [notificationDetail, setNotificationDetail] = useState<NotificationRow | null>(null);
  const [portfolioRequiredDate, setPortfolioRequiredDate] = useState<string | null>(null);
  const [portfolioImportDate, setPortfolioImportDate] = useState<string | null>(null);
  const [internalView, setInternalView] = useState<WorkspaceView>(() => {
    if (typeof window === "undefined" || isTauriRuntime()) return "Overview";
    return viewFromWebPath(window.location.pathname);
  });
  const view = workspaceView ?? internalView;
  const setView = onWorkspaceViewChange ?? setInternalView;
  const desktopWorkspace = Boolean(runtimeControl);
  const [resourceLoads, setResourceLoads] = useState<Partial<Record<Resource, ResourceStatus>>>({});
  const latestRequest = useRef<Partial<Record<Resource, number>>>({});
  const taskCreation = useRef(false);
  const [journalFocus, setJournalFocus] = useState<string | null>(() =>
    typeof window !== "undefined" && !isTauriRuntime()
      ? new URLSearchParams(window.location.search).get("journal_task")
      : null,
  );
  const [busy, setBusy] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [pushStatus, setPushStatus] = useState("");
  const [dataQuality, setDataQuality] = useState<Awaited<ReturnType<typeof api.syncData>> | null>(null);
  const [marketSync, setMarketSync] = useState<ActiveMarketSync | null>(null);
  const [marketSyncError, setMarketSyncError] = useState("");
  const [marketSyncSteps, setMarketSyncSteps] = useState<Record<string, MarketSyncProgress>>({});
  const [taskData, setTaskData] = useState<TaskDataResponse | null>(null);
  const [searchQuery, setSearchQuery] = useState(() => {
    if (typeof window === "undefined" || isTauriRuntime()) return "";
    return new URLSearchParams(window.location.search).get("q") ?? "";
  });
  const searchRef = useRef<HTMLInputElement>(null);
  const focusMarketSection = useRef<"market-candidates" | "market-anomalies" | null>(null);
  const applyScheduler = useCallback((value: SchedulerResponse) => {
    latestRequest.current.health = (latestRequest.current.health ?? 0) + 1;
    setScheduler(value);
  }, []);

  const selectTask = useCallback((taskId: string | null) => {
    if (selectedTaskRef.current === taskId) return;
    selectedTaskRef.current = taskId;
    // Invalidate outstanding reads, even when the user switches back to the same task.
    detailSequence.current.applied = ++detailSequence.current.requested;
    setSelectedId(taskId);
    setDetail(null);
    setDetailError("");
    if (!taskId) setMobileDetailOpen(false);
    setTaskData(null);
  }, []);

  const loadDetail = useCallback(async (taskId: string) => {
    if (selectedTaskRef.current !== taskId) return;
    const request = ++detailSequence.current.requested;
    try {
      const result = await api.task(taskId);
      if (selectedTaskRef.current !== taskId || request < detailSequence.current.applied) return;
      detailSequence.current.applied = request;
      setDetail(result);
      setDetailError("");
    } catch (error) {
      if (selectedTaskRef.current !== taskId || request < detailSequence.current.applied) return;
      detailSequence.current.applied = request;
      const message = friendlyError(error, "读取任务失败");
      if (message.includes("已不存在")) {
        selectTask(null);
        setError(message);
      } else {
        setDetailError(message);
      }
    }
  }, [api, selectTask]);

  const openResearch = (taskId: string) => {
    selectTask(taskId);
    setMobileDetailOpen(true);
    if (window.matchMedia("(max-width: 700px)").matches) {
      window.requestAnimationFrame(() => document.getElementById("return-to-research-queue")?.focus());
    }
  };

  const goToResearch = (taskId: string) => {
    openResearch(taskId);
    setView("Research");
    window.requestAnimationFrame(() => {
      document.querySelector("main")?.scrollTo({ top: 0 });
      window.scrollTo({ top: 0 });
    });
  };

  const returnToQueue = () => {
    setMobileDetailOpen(false);
    window.requestAnimationFrame(() => {
      const row = document.getElementById(`task-${selectedTaskRef.current}`);
      (row ?? document.getElementById("research-queue-heading"))?.focus();
    });
  };

  const refreshResources = useCallback(async (resources: readonly Resource[]) => {
    if (!runtimeReady) return;
    const loaders: Record<Resource, (commit: CommitResource) => Promise<void>> = {
      tasks: async (commit) => commit(await api.tasks(), (result) => {
        setTasks(result.tasks);
        if (!selectedTaskRef.current && result.tasks[0]) selectTask(result.tasks[0].id);
      }),
      health: async (commit) => commit(await api.health(), (value) => {
        setHealth(value);
        setScheduler(undefined);
      }),
      rules: async (commit) => commit((await api.rules()).rules, setRules),
      market: async (commit) => commit(await api.market(), setMarket),
      portfolio: async (commit) => commit(await api.portfolio(), setPortfolio),
      profile: async (commit) => commit(await api.profile(), setProfile),
      watchlists: async (commit) => commit((await api.watchlists()).watchlists, setWatchlists),
      notifications: async (commit) => commit((await api.notifications()).notifications as NotificationRow[], setNotifications),
      journal: async (commit) => commit((await api.journal({ task_id: journalFocus ?? undefined })).items, setJournalItems),
      journalSummary: async (commit) => commit(await api.journalSummary(), setJournalSummary),
      journalPatterns: async (commit) => commit(await api.journalPatterns(), setJournalPatterns),
    };
    await Promise.all(resources.map(async (name) => {
      const request = (latestRequest.current[name] ?? 0) + 1;
      latestRequest.current[name] = request;
      const commit: CommitResource = (value, apply) => {
        if (latestRequest.current[name] === request) apply(value);
      };
      try {
        await loaders[name](commit);
        commit({}, (status) => setResourceLoads((loads) => ({ ...loads, [name]: status })));
      } catch (requestError) {
        const message = friendlyError(requestError, "无法加载工作区数据");
        commit({ error: message }, (status) => {
          if (!desktopWorkspace && /云端工作区需要重新连接|unauthorized|401/i.test(message)) {
            setError(message);
            setAuthRequired(true);
          }
          setResourceLoads((loads) => ({ ...loads, [name]: status }));
        });
      }
    }));
  }, [api, desktopWorkspace, journalFocus, runtimeReady, selectTask]);

  const refresh = useCallback((target = view) => refreshResources(
    runtimeHealth || target === "Data Health" ? pageResources[target] : [...pageResources[target], "health"],
  ), [refreshResources, runtimeHealth, view]);

  useEffect(() => {
    if (runtimeControl) return;
    const storedToken = typeof window !== "undefined"
      ? window.sessionStorage.getItem("pia.cloud_token") ?? window.sessionStorage.getItem("pia.server_token")
      : null;
    if (storedToken) api.setToken(storedToken);
  }, [api, runtimeControl]);
  useEffect(() => { void refresh(); }, [refresh]);
  const selectedTaskStatus = detail?.task.status;
  useEffect(() => {
    if (selectedTaskStatus === "WAITING_APPROVAL") void refreshResources(["notifications"]);
  }, [selectedTaskStatus, refreshResources]);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (isTauriRuntime()) {
      if (selectedId) url.searchParams.set("task", selectedId);
      else url.searchParams.delete("task");
      window.history.replaceState({}, "", url);
      return;
    }
    const isMobileQueue = (view === "Research" || view === "Overview")
      && !mobileDetailOpen && window.matchMedia("(max-width: 700px)").matches;
    const linkedTask = isMobileQueue ? null : selectedId;
    if (view === "Research" && linkedTask) {
      url.pathname = `/research/${encodeURIComponent(linkedTask)}`;
      url.searchParams.delete("task");
    } else {
      url.pathname = webRoutes[view] ?? webRoutes.Overview;
      if (linkedTask) url.searchParams.set("task", linkedTask);
      else url.searchParams.delete("task");
    }
    if (searchQuery.trim()) url.searchParams.set("q", searchQuery.trim());
    else url.searchParams.delete("q");
    if (view === "Journal" && journalFocus) url.searchParams.set("journal_task", journalFocus);
    else url.searchParams.delete("journal_task");
    window.history.replaceState({}, "", url);
  }, [journalFocus, searchQuery, selectedId, view, mobileDetailOpen]);
  useEffect(() => {
    if (!selectedId || !runtimeReady || !["Overview", "Research", "Audit", "Rules"].includes(view)) return;
    let active = true;
    let loading = false;
    const update = async (includeQueue = false) => {
      if (!active || loading) return;
      loading = true;
      await Promise.all([
        loadDetail(selectedId),
        includeQueue && (view === "Overview" || view === "Research") ? refreshResources(["tasks"]) : undefined,
      ]);
      loading = false;
    };
    const refreshSelection = () => { void update(true); };
    void update();
    const unsubscribe = api.subscribeTask(selectedId, refreshSelection);
    const handle = window.setInterval(refreshSelection, 1200);
    return () => { active = false; unsubscribe(); window.clearInterval(handle); };
  }, [api, view, selectedId, runtimeReady, loadDetail, refreshResources]);

  const marketForNewResearch = () => health?.provider.provider_id === "fixture" && market
    ? Promise.resolve(market)
    : api.market();

  const createTask = async () => {
    if (!runtimeReady || !health || busy || taskCreation.current) return;
    taskCreation.current = true;
    setBusy(true);
    setPortfolioRequiredDate(null);
    let date = reviewSession(health, market).as_of;
    try {
      const snapshot = await marketForNewResearch();
      date = reviewSession(health, snapshot).as_of;
      const result = await api.createTask(taskInput(health, snapshot, date));
      goToResearch(result.task.id);
      setError(null);
      void refreshResources(["tasks"]);
    } catch (requestError) {
      showResearchError(requestError, date, "创建任务失败");
    } finally {
      taskCreation.current = false;
      setBusy(false);
    }
  };

  useEffect(() => {
    const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
    if (!isTauri) return;
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    void import("@tauri-apps/api/event")
      .then(({ listen }) => listen<string>("pia://tray", async (event) => {
        if (cancelled) return;
        if (event.payload === "status") {
          setView("Data Health");
          await refresh("Data Health");
          return;
        }
        if (!runtimeReady) return;
        if (event.payload === "pause-scheduler") {
          try {
            applyScheduler(await api.stopScheduler());
            setView("Data Health");
            setError(null);
          } catch (requestError) {
            setError(friendlyError(requestError, "暂停调度器失败"));
          }
          return;
        }
        if (event.payload === "resume-scheduler") {
          try {
            applyScheduler(await api.startScheduler());
            setView("Data Health");
            setError(null);
          } catch (requestError) {
            setError(friendlyError(requestError, "恢复调度器失败"));
          }
        }
      }))
      .then((dispose) => {
        if (cancelled) dispose();
        else unlisten = dispose;
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [api, applyScheduler, refresh, runtimeReady, setView]);

  useEffect(() => {
    const onShortcut = (event: globalThis.KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      } else if (key === "p") {
        event.preventDefault();
        setView("Portfolio");
      } else if (event.key === "Enter") {
        const target = event.target as HTMLElement | null;
        if (
          target?.closest("input, textarea, select, [contenteditable='true']")
          && target !== searchRef.current
        ) return;
        event.preventDefault();
        document.querySelector<HTMLButtonElement>("[data-shortcut='new-review']")?.click();
      }
    };
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, [setView]);

  const showResearchError = (requestError: unknown, date: string, fallback: string) => {
    if (missingPortfolio(requestError)) {
      setError(null);
      setPortfolioRequiredDate(date);
    } else {
      setError(friendlyError(requestError, fallback));
    }
  };

  const createResearch = async (symbol: string, anomaly?: MarketAnomalies) => {
    if (!runtimeReady || !health || busy || taskCreation.current) return;
    taskCreation.current = true;
    setBusy(true);
    setPortfolioRequiredDate(null);
    setError(null);
    let date = anomaly?.as_of ?? reviewSession(health, market).as_of;
    try {
      const snapshot = anomaly ? market : await marketForNewResearch();
      date = anomaly?.as_of ?? reviewSession(health, snapshot).as_of;
      const input = taskInput(health, snapshot, date);
      const result = await api.createResearchTask(symbol, {
        ...input, marketSnapshotId: anomaly?.snapshot_id ?? input.marketSnapshotId,
      });
      setNotificationDetail(null);
      goToResearch(result.task.id);
      setError(null);
      void refreshResources(["tasks"]);
    } catch (requestError) {
      showResearchError(requestError, date, "创建个股研究失败");
    } finally {
      taskCreation.current = false;
      setBusy(false);
    }
  };

  const approve = async (taskId: string, action: "APPROVE" | "REJECT" | "NO_ACTION" | "REQUEST_MORE_RESEARCH" | "MARK_AS_WATCH") => {
    if (busy || taskId !== selectedTaskRef.current || detail?.task.id !== taskId || detail.task.status !== "WAITING_APPROVAL") return;
    setBusy(true);
    try {
      await api.approve(taskId, action);
      await loadDetail(taskId);
      await refresh();
    } catch (requestError) {
      setError(friendlyError(requestError, "审批失败"));
    } finally {
      setBusy(false);
    }
  };

  const controlTask = async (action: "pause" | "resume") => {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api[action](selectedId);
      await refresh();
      await loadDetail(selectedId);
    } catch (requestError) {
      setError(friendlyError(requestError, "任务控制失败"));
    } finally {
      setBusy(false);
    }
  };

  const cancelTask = async () => {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api.cancel(selectedId, "Cancelled from Pia Workspace");
      await refresh();
      await loadDetail(selectedId);
    } catch (requestError) {
      setError(friendlyError(requestError, "取消任务失败"));
    } finally {
      setBusy(false);
    }
  };

  const retryTask = async () => {
    if (!selectedId) return;
    setBusy(true);
    setPortfolioRequiredDate(null);
    try {
      const result = await api.retry(selectedId);
      selectTask(result.task.id);
      await refresh();
      await loadDetail(result.task.id);
    } catch (requestError) {
      showResearchError(requestError, String(detail?.task.target.as_of ?? "2026-11-05"), "重试任务失败");
    } finally {
      setBusy(false);
    }
  };

  const replayTask = async () => {
    if (!selectedId) return;
    setBusy(true);
    try {
      const result = await api.replay(selectedId);
      selectTask(result.task.id);
      await refresh();
      await loadDetail(result.task.id);
    } catch (requestError) {
      setError(friendlyError(requestError, "回放任务失败"));
    } finally {
      setBusy(false);
    }
  };

  const loadTaskData = async () => {
    if (!selectedId) return;
    setBusy(true);
    try {
      const data = await api.taskData(selectedId);
      if (data.task_id === selectedTaskRef.current) setTaskData(data);
    } catch (requestError) {
      setError(friendlyError(requestError, "读取原始数据失败"));
    } finally {
      setBusy(false);
    }
  };

  const copyTaskLink = async () => {
    if (!selectedId || typeof window === "undefined") return;
    const url = new URL(window.location.href);
    url.searchParams.set("task", selectedId);
    try {
      await navigator.clipboard.writeText(url.toString());
      setError(null);
    } catch {
      setError("无法复制稳定任务链接");
    }
  };

  const copyEvidenceLink = async (evidenceId: string) => {
    if (!selectedId || typeof window === "undefined") return;
    const url = new URL(window.location.href);
    url.searchParams.set("task", selectedId);
    url.hash = `evidence-${evidenceId}`;
    try {
      await navigator.clipboard.writeText(url.toString());
      setError(null);
    } catch {
      setError("无法复制稳定证据链接");
    }
  };

  const saveWatchlist = async (name: string, symbols: string[], append: boolean) => {
    const saved = await api.saveWatchlist(name, symbols, append);
    setWatchlists((lists) => [saved, ...lists.filter((list) => list.id !== saved.id)]);
    void refreshResources(["market"]);
  };

  const saveJournalCandidate = async (candidateKey: string) => {
    setBusy(true);
    try {
      await api.materializeJournalMemoryCandidate(candidateKey);
      await refresh();
      setError(null);
    } catch (requestError) {
      setError(friendlyError(requestError, "保存待确认记忆失败"));
    } finally {
      setBusy(false);
    }
  };

  const reviewJournalCandidate = async (
    candidateId: string,
    payload: {
      action: "CONFIRM" | "EDIT_AND_CONFIRM" | "REJECT" | "ARCHIVE";
      title?: string | null;
      content?: string | null;
      notes?: string;
    },
  ) => {
    setBusy(true);
    try {
      await api.reviewJournalMemoryCandidate(candidateId, payload);
      await refresh();
      setError(null);
    } catch (requestError) {
      setError(friendlyError(requestError, "审核待确认记忆失败"));
    } finally {
      setBusy(false);
    }
  };

  const feedbackJournalCandidate = async (
    candidateId: string,
    usageId: string,
    rating: "HELPFUL" | "NOT_HELPFUL" | "UNCERTAIN",
  ) => {
    setBusy(true);
    try {
      await api.memoryCandidateFeedback(candidateId, { rating, usage_id: usageId });
      await refresh();
      setError(null);
    } catch (requestError) {
      setError(friendlyError(requestError, "保存记忆效果反馈失败"));
    } finally {
      setBusy(false);
    }
  };

  const takeoverTask = async () => {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api.takeover(selectedId, "Taken over from Pia Workspace");
      await loadDetail(selectedId);
      await refresh();
    } catch (requestError) {
      setError(friendlyError(requestError, "人工接管失败"));
    } finally {
      setBusy(false);
    }
  };

  const exportTaskContext = async () => {
    if (!selectedId) return;
    setBusy(true);
    try {
      const context = await api.exportTask(selectedId);
      const blob = new Blob([context], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `pia-task-${selectedId}-context.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(friendlyError(requestError, "导出上下文失败"));
    } finally {
      setBusy(false);
    }
  };

  const recordRetrospective = async (taskId: string, payload: RetrospectiveInput) => {
    if (taskId !== selectedTaskRef.current) throw new Error("请重新打开这条研究后保存。");
    setBusy(true);
    try {
      await api.recordRetrospective(taskId, payload);
      void loadDetail(taskId);
    } finally {
      setBusy(false);
    }
  };

  const markNotificationRead = async (notification: NotificationRow) => {
    if (notification.read_at) return;
    try {
      await api.markNotificationRead(notification.id);
      setNotifications((current) => current.map((item) => item.id === notification.id
        ? { ...item, read_at: new Date().toISOString() }
        : item));
      void refreshResources(["notifications"]);
    } catch (requestError) {
      setError(friendlyError(requestError, "标记通知失败"));
    }
  };

  const openNotificationDetail = (notification: NotificationRow) => {
    setPortfolioRequiredDate(null);
    setError(null);
    setNotificationDetail(notification);
    void markNotificationRead(notification);
  };

  const enablePush = async () => {
    setPushStatus("Registering browser notifications…");
    try {
      const result = await registerWebPushDevice(api.registerDevice);
      setPushStatus(
        result.status === "registered"
          ? `Web Push enabled for ${result.deviceId}`
          : result.detail,
      );
    } catch (requestError) {
      setPushStatus(
        requestError instanceof Error
          ? requestError.message
          : "Web Push registration failed",
      );
    }
  };

  const counts = useMemo(() => ({
    running: tasks.filter((task) => ["RUNNING", "PLANNING", "REVIEWING"].includes(task.status)).length,
    blocked: tasks.filter((task) => task.status === "BLOCKED").length,
    approval: tasks.filter((task) => task.status === "WAITING_APPROVAL").length,
  }), [tasks]);
  const session = reviewSession(health, market);
  const syncMarketData = async (refreshStage?: MarketSyncStage) => {
    if (marketSync) return;
    const symbols = [
      ...(Array.isArray(portfolio?.positions) && portfolio.source !== "fixture"
        ? portfolio.positions.map((position) => String(position.symbol)) : []),
      ...watchlists.flatMap((list) => list.symbols),
    ];
    const codes = [...new Set(symbols.flatMap((symbol) => stockCode(symbol) ?? []))];
    setMarketSync({ asOf: session.as_of, startedAt: Date.now() });
    setMarketSyncError("");
    setMarketSyncSteps({});
    setDataQuality(null);
    try {
      const result = await api.syncData(session.as_of, codes, (progress) => {
        setMarketSyncSteps((steps) => ({ ...steps, [progress.stage]: progress }));
        if (progress.stage === "market_snapshot" && progress.status === "done") {
          void refreshResources(["market"]);
        }
      }, refreshStage);
      setDataQuality(result);
    } catch (error) {
      setMarketSyncError(friendlyError(error, "市场数据同步失败，请稍后重试。"));
    } finally {
      setMarketSync(null);
      void refreshResources(["market", "health", "notifications"]);
    }
  };
  const isDemo = health?.provider.provider_id === "fixture";
  const sessionReady = market?.quality === "verified" && market.as_of === session.as_of
    && isDemo === isDemoMarket(market);
  const setup: SetupState = {
    profile: Boolean(profile?.payload && Object.keys(profile.payload as Record<string, unknown>).length > 0),
    portfolio: Boolean(portfolio?.source === "import" && Array.isArray(portfolio.positions) && portfolio.positions.length > 0),
    rules: Boolean(rules?.version && rules.version !== "v1"),
    data: sessionReady,
    review: tasks.some((task) => task.trigger_type === "MarketClose" && !task.target._replay_of
      && !task.error && ["BLOCKED", "NO_ACTION", "WAITING_APPROVAL", "DONE"].includes(task.status)),
  };
  const dataState = isDemo
    ? { label: "演示行情", tone: "replay" }
    : resourceLoads.market?.error
      ? { label: "行情状态读取失败", tone: "unavailable" }
      : !resourceLoads.market
        ? { label: "正在读取行情", tone: "connecting" }
        : sessionReady
          ? { label: "收盘行情已就绪", tone: "live" }
          : market?.as_of === session.as_of && market.snapshot_id
            ? { label: "收盘行情不完整", tone: "degraded" }
            : { label: "拟复盘日行情未就绪", tone: "degraded" };
  const instrumentNames = useMemo(() => new Map(
    (market?.instruments ?? []).flatMap(({ symbol, name }) => {
      const code = symbol ? stockCode(symbol) : undefined;
      return code && name ? [[code, name] as const] : [];
    }),
  ), [market]);
  const latestResearch = useMemo(() => latestStockResearch(tasks), [tasks]);
  const portfolioPrompt = portfolioRequiredDate ? <div className="error-banner" role="alert">
    <WarningCircleIcon size={16} aria-hidden="true" /><strong>缺少持仓快照</strong>
    <span>请导入 {portfolioRequiredDate} 或更早的持仓，再开始研究。</span>
    <button type="button" onClick={() => setPortfolioImportDate(portfolioRequiredDate)}>导入持仓</button>
    <button type="button" className="icon-button" title="关闭提示" aria-label="关闭持仓提示"
      onClick={() => setPortfolioRequiredDate(null)}><XIcon size={16} aria-hidden="true" /></button>
  </div> : null;
  const lastReview = tasks.find((task) => task.trigger_type === "MarketClose" && !task.target._replay_of);
  const visibleTasks = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return tasks;
    return tasks.filter((task) => [
      task.id,
      taskTitle(task, instrumentNames),
      task.status,
      JSON.stringify(task.target),
    ].join(" ").toLowerCase().includes(query));
  }, [searchQuery, tasks, instrumentNames]);

  const pageTitle = view === "Overview" ? "研究总览" : nav.find(([, key]) => key === view)?.[0] ?? view;
  const required = primaryResource[view];
  const pageLoad = required ? resourceLoads[required] : undefined;
  const loadError = runtimeError ?? pageLoad?.error;
  const contentReady = runtimeReady && (!required || Boolean(pageLoad && !loadError));

  useEffect(() => {
    const section = focusMarketSection.current;
    if (!section) return;
    if (view !== "Market" || contentReady) {
      focusMarketSection.current = null;
      if (view === "Market") document.getElementById(section)?.focus();
    }
  }, [contentReady, view]);

  if (authRequired && !runtimeControl) {
    return <LoginView
      error={error}
      onSubmit={(token) => {
        api.setToken(token);
        if (typeof window !== "undefined") window.sessionStorage.setItem("pia.cloud_token", token);
        setError(null);
        setAuthRequired(false);
        void refresh();
      }}
    />;
  }

  const isResearchWorkspace = view === "Overview" || view === "Research";
  const showMarketContext = isResearchWorkspace || view === "Market";
  const showMobileDetail = Boolean(selectedId && mobileDetailOpen && isResearchWorkspace);
  const showWindowTitlebar = isTauriRuntime() && navigator.userAgent.includes("Macintosh");
  const scanKey = JSON.stringify([health?.provider?.provider_id, market?.snapshot_id, market?.quality, profile?.id, rules?.version]);
  const openMarketSection = (section: "market-candidates" | "market-anomalies") => {
    focusMarketSection.current = section;
    setView("Market");
  };
  const openJournal = (taskId: string) => {
    setJournalFocus(taskId);
    setView("Journal");
    window.requestAnimationFrame(() => {
      document.querySelector("main")?.scrollTo({ top: 0 });
      window.scrollTo({ top: 0 });
    });
  };
  return (
    <div className={`shell${showWindowTitlebar ? " shell--macos" : ""}`}>
      {showWindowTitlebar && <>
        <div className="window-drag-region window-drag-region--sidebar" data-tauri-drag-region aria-hidden="true" />
        <div className="window-drag-region" data-tauri-drag-region aria-hidden="true" />
      </>}
      <aside className={`sidebar ${navigationOpen ? "navigation-open" : ""}`} onKeyDown={(event) => {
        if (event.key === "Escape" && navigationOpen) {
          setNavigationOpen(false);
          document.querySelector<HTMLButtonElement>(".navigation-toggle")?.focus();
        }
      }}>
        <div className="brand"><span className="brand-mark">P</span><div><strong>Pia</strong><small>你的投资研究助手</small></div></div>
        <button className="icon-button navigation-toggle" aria-label={navigationOpen ? "关闭导航" : "打开导航"} title={navigationOpen ? "关闭导航" : "打开导航"} aria-expanded={navigationOpen} aria-controls="sidebar-navigation" onClick={() => setNavigationOpen((open) => !open)}>
          {navigationOpen ? <XIcon size={16} aria-hidden="true" /> : <ListIcon size={16} aria-hidden="true" />}
        </button>
        <nav id="sidebar-navigation" aria-label="主导航" onClick={() => {
          if (navigationOpen) document.querySelector<HTMLHeadingElement>(".page-heading h1")?.focus();
        }}>
        <div className="sidebar-section">
          <span className="eyebrow">工作台</span>
          {nav.slice(0, 6).map(([label, key, icon]) => <button key={key} title={label} aria-label={label} aria-current={view === key ? "page" : undefined} className={`nav-item ${view === key ? "active" : ""}`} onClick={() => { if (key === "Journal") setJournalFocus(null); setView(key); setMobileDetailOpen(false); setNavigationOpen(false); }}><span className="nav-glyph"><NavIcon name={icon} /></span><span className="nav-label">{label}</span></button>)}
        </div>
        <div className="sidebar-section">
          <span className="eyebrow">设置</span>
          {nav.slice(6).map(([label, key, icon]) => <button key={key} title={label} aria-label={label} aria-current={view === key ? "page" : undefined} className={`nav-item ${view === key ? "active" : ""}`} onClick={() => { setView(key); setMobileDetailOpen(false); setNavigationOpen(false); }}><span className="nav-glyph"><NavIcon name={icon} /></span><span className="nav-label">{label}</span></button>)}
        </div>
        </nav>
        <div className="sidebar-bottom">
          {runtimeControl}
        </div>
      </aside>

      <main className={`main${isResearchWorkspace ? " main--research" : ""}${showMobileDetail ? " research-detail-open" : ""}`}>
        <header className="topbar">
          <div className="page-heading">
            <h1 tabIndex={-1}>{pageTitle}</h1>
            {showMarketContext && contentReady && <div className="page-context">
              <span className="date-chip">{isDemo ? "演示日期" : "拟复盘日"} {session.as_of}{!session.calendar_verified && " · 待日历确认"}</span>
              <button className={`text-button provenance-chip ${dataState.tone}`} onClick={() => setView("Data Health")}><i />{dataState.label}</button>
            </div>}
          </div>
          <div className="topbar-actions">
            <WorkspaceSearch inputRef={searchRef} query={searchQuery} setQuery={setSearchQuery}
              instruments={instrumentNames} tasks={tasks} latest={latestResearch} busy={busy || !runtimeReady || !health}
              historyReady={Boolean(resourceLoads.tasks && !resourceLoads.tasks.error)}
              onSearch={() => void refreshResources((["market", "tasks"] as const).filter((name) => !resourceLoads[name] || resourceLoads[name]?.error))}
              onOpen={goToResearch} onResearch={(symbol) => void createResearch(symbol)} />
            <button className="icon-button notification-button" title={`通知 · ${unreadNotifications} 条未读`} aria-label={`通知，${unreadNotifications} 条未读`} onClick={() => setView("Notifications")}><BellIcon size={16} aria-hidden="true" />{unreadNotifications > 0 ? <span className="notification-count">{unreadNotifications > 99 ? "99+" : unreadNotifications}</span> : null}</button>
            <button className="icon-button" title="刷新" aria-label="刷新" disabled={!runtimeReady} onClick={() => void refresh()}><ArrowClockwiseIcon size={16} aria-hidden="true" /></button>
            {view === "Overview" && lastReview && <button className="quiet-button" onClick={() => goToResearch(lastReview.id)}>查看上次复盘</button>}
            <button className={`primary-button${isResearchWorkspace ? "" : " shortcut-only"}`} data-shortcut="new-review" onClick={() => void createTask()} disabled={busy || !runtimeReady || !health}><PlusIcon size={16} aria-hidden="true" />{isDemo ? "开始演示复盘" : "开始收盘复盘"}</button>
          </div>
        </header>

        {!notificationDetail && error && <div className="error-banner" role="alert"><WarningCircleIcon size={16} aria-hidden="true" /><strong>需要处理</strong><span>{error}</span><button onClick={() => void refresh()}>重试</button><button className="icon-button" title="关闭提示" aria-label="关闭提示" onClick={() => setError(null)}><XIcon size={16} aria-hidden="true" /></button></div>}

        {!contentReady ? <section className="single-panel panel workspace-status">
          {loadError ? <>
            <p role="alert">{loadError}</p>
            <button className="quiet-button" onClick={runtimeError ? onRuntimeRetry : () => void refresh()}>重试</button>
          </> : <p role="status">正在加载{runtimeMode === "cloud" ? "云端" : "本地"}{pageTitle}…</p>}
        </section> : <>
        {view === "Overview" && !Object.values(setup).every(Boolean) && <SetupGuide setup={setup} onNavigate={setView}
          onCreateReview={() => void createTask()} onPreview={() => setPreviewOpen(true)} disabled={busy || !health}
          loadError={(["profile", "portfolio", "rules", "market"] as const).some((name) => Boolean(resourceLoads[name]?.error))}
          onRetry={() => void refreshResources(["profile", "portfolio", "rules", "market"])} />}
        {view === "Overview" && <AttentionFeed notifications={notifications} onOpenTask={goToResearch}
          onOpenDetail={openNotificationDetail}
          load={resourceLoads.notifications} onRetry={() => void refreshResources(["notifications"])} />}
        {view === "Overview" && runtimeMode !== "cloud" && <HoldingsReviewCard
          onOpenTask={goToResearch} onOpenPortfolio={() => setView("Portfolio")} />}

        {view === "Overview" && <section className="metrics" aria-label="研究统计">
          <div className="metric"><span>进行中的研究</span><strong>{counts.running}</strong><small>实时更新进度</small></div>
          <div className="metric"><span>等你确认</span><strong className={counts.approval > 0 ? "metric-warning" : undefined}>{counts.approval}</strong><small>需要人工判断</small></div>
          <div className="metric"><span>被规则拦截</span><strong className={counts.blocked > 0 ? "metric-danger" : undefined}>{counts.blocked}</strong><small>先解决风险再行动</small></div>
          <div className="metric"><span>当前规则</span><strong>{String((rules as { version?: unknown } | null)?.version ?? "v1")}</strong><small>每次研究固定版本</small></div>
        </section>}

        {view === "Journal" ? <JournalView key={journalFocus ?? "all"} items={journalItems} focusTaskId={journalFocus}
          onClearFocus={() => setJournalFocus(null)} summary={journalSummary} patterns={journalPatterns}
          onSaveCandidate={(candidateKey) => void saveJournalCandidate(candidateKey)} onReviewCandidate={(candidateId, payload) => void reviewJournalCandidate(candidateId, payload)}
          onFeedbackCandidate={(candidateId, usageId, rating) => void feedbackJournalCandidate(candidateId, usageId, rating)}
          onOpenTask={goToResearch} /> :
          view === "Market" ? <MarketView key={scanKey} market={market} demo={health?.provider?.provider_id === "fixture"}
            pending={market === null && error === null} savedScan={candidateScan?.key === scanKey ? candidateScan.result : null}
            onScanned={(result) => setCandidateScan({ key: scanKey, result })}
            watchlists={watchlists} onResearch={(symbol) => void createResearch(symbol)}
            onResearchAnomaly={(symbol, anomaly) => void createResearch(symbol, anomaly)} busy={busy || !health}
            onWatch={(symbol) => saveWatchlist(DEFAULT_WATCHLIST, [symbol], true)}
            onOpenData={() => setView("Data Health")} /> :
          view === "Watchlist" ? <WatchlistView watchlists={watchlists} onSaved={saveWatchlist}
            instruments={instrumentNames} latest={latestResearch} taskLoad={resourceLoads.tasks} busy={busy}
            onRetryTasks={() => void refreshResources(["tasks"])} onOpenTask={goToResearch}
            onResearch={(symbol) => void createResearch(symbol)} onOpenMarket={() => openMarketSection("market-candidates")} /> :
          view === "Portfolio" ? <PortfolioView portfolio={portfolio} demoDate={health?.provider?.provider_id === "fixture" ? REPLAY_AS_OF : undefined} onChanged={(snapshot) => {
            if (snapshot) setPortfolio(snapshot);
            void refresh();
          }} /> :
          view === "Profile" ? <ProfileView profile={profile} load={resourceLoads.profile}
            onReload={() => void refreshResources(["profile"])}
            onCredentialsSaved={() => void refreshResources(["health", "market"])}
            localCredentials={runtimeMode === "local" && runtimeReady} /> :
          view === "Rules" ? <RulesView rules={rules} evaluation={detail?.decision?.rationale.rules} onSaved={() => void refresh()} /> :
          view === "Data Health" ? <DataHealthView health={health} market={market} session={session} marketLabel={dataState.label}
            syncResult={dataQuality} marketSync={marketSync} syncError={marketSyncError}
            syncSteps={marketSyncSteps} onSync={syncMarketData} onSchedulerChange={applyScheduler}
            onOpenSettings={() => setView("Profile")} onOpenAnomalies={() => openMarketSection("market-anomalies")} /> :
          view === "Audit" ? <AuditView detail={detail} /> :
          view === "Notifications" ? <NotificationsView
            notifications={notifications}
            onRead={(notification) => void markNotificationRead(notification)}
            onEnablePush={() => void enablePush()}
            pushStatus={pushStatus}
            onOpenTask={goToResearch}
            onOpenDetail={openNotificationDetail}
          /> :
        <div className="workspace">
          <section className="queue-panel panel">
            <div className="panel-header"><div><span className="eyebrow">研究记录</span><h2 id="research-queue-heading" tabIndex={-1}>你的研究</h2></div><span className="count">{tasks.length}</span></div>
            <div className="queue-list">
              {resourceLoads.tasks?.error
                ? <div className="form-hint" role="status">研究列表暂不可用。<button className="text-button" onClick={() => void refreshResources(["tasks"])}>重试列表</button></div>
                : !resourceLoads.tasks && <p className="form-hint" role="status">正在读取研究记录…</p>}
              {visibleTasks.length > 0
                ? <TaskQueue tasks={visibleTasks} selectedId={selectedId} onSelect={selectTask} onOpen={openResearch} />
                : resourceLoads.tasks && !resourceLoads.tasks.error && <EmptyState message={tasks.length === 0 ? "还没有研究。可以发起收盘复盘，或搜索标的开始研究。" : "没有匹配的研究记录。"} />}
            </div>
          </section>

          <section className="detail-panel">
            {showMobileDetail && <button id="return-to-research-queue" className="quiet-button research-queue-back" onClick={returnToQueue}>返回研究队列</button>}
            {detailError && <div className="detail-load-error" role="alert">
              <p>{detailError}</p>
              {selectedId && <button className="quiet-button" onClick={() => void loadDetail(selectedId)}>重试读取研究</button>}
            </div>}
            {!detail ? selectedId
              ? !detailError && <p className="detail-loading" role="status">正在加载研究详情…</p>
              : <EmptyState message="选择一条研究记录，这里会显示结论、依据和风险。" />
              : <ResearchDetail key={detail.task.id} detail={detail} busy={busy} rawData={taskData?.task_id === detail.task.id ? taskData : null} onApprove={(action) => void approve(detail.task.id, action)} onControl={controlTask} onCancel={() => void cancelTask()} onRetry={() => void retryTask()} onTakeover={() => void takeoverTask()} onExport={() => void exportTaskContext()} onReplay={() => void replayTask()} onRawData={() => void loadTaskData()} onCopyLink={() => void copyTaskLink()} onCopyEvidenceLink={(evidenceId) => void copyEvidenceLink(evidenceId)}
                onRetrospective={(payload) => recordRetrospective(detail.task.id, payload)}
                onOpenJournal={() => openJournal(detail.task.id)} onOpenPortfolio={() => setView("Portfolio")}
                onHoldingsConfirmed={() => loadDetail(detail.task.id)}
                onHoldingsRetry={() => { setMobileDetailOpen(false); setView("Overview"); }} />}
          </section>
        </div>}
        {view === "Overview" && <StrategyAgentPanel
          profile={profile}
          rules={rules}
          health={health}
          portfolio={portfolio}
          watchlists={watchlists}
          tasks={tasks}
          dataTone={dataState.tone}
          onNavigate={setView}
        />}
        </>}
      </main>
      {previewOpen && <DemoReview onClose={() => setPreviewOpen(false)} onPortfolio={() => {
        setPreviewOpen(false);
        setView("Portfolio");
      }} />}
      {notificationDetail && !portfolioImportDate && <AnomalyNotificationDialog key={notificationDetail.id}
        notification={notificationDetail} busy={busy || !health}
        onClose={() => {
          setNotificationDetail(null);
          setPortfolioRequiredDate(null);
          setError(null);
        }} onOpenTask={(taskId) => { setNotificationDetail(null); goToResearch(taskId); }}
        onResearch={(symbol, anomaly) => void createResearch(symbol, anomaly)}>
        {portfolioPrompt}
        {error && <p className="form-hint" role="alert">{error}</p>}
      </AnomalyNotificationDialog>}
      {portfolioRequiredDate && !notificationDetail && !portfolioImportDate && <WorkspaceDialog
        title="缺少持仓快照" pending={false} onClose={() => setPortfolioRequiredDate(null)}>
        <p className="portfolio-dialog-hint">请导入 {portfolioRequiredDate} 或更早的持仓，再开始研究。</p>
        <div className="runtime-dialog-actions">
          <button type="button" className="quiet-button" onClick={() => setPortfolioRequiredDate(null)}>取消</button>
          <button type="button" className="primary-button" data-initial-focus onClick={() => setPortfolioImportDate(portfolioRequiredDate)}>导入持仓</button>
        </div>
      </WorkspaceDialog>}
      {portfolioImportDate && <PortfolioImportDialog defaultDate={portfolioImportDate}
        onClose={() => setPortfolioImportDate(null)}
        onImported={(snapshot) => {
          setPortfolioImportDate(null);
          if (String(snapshot.as_of) <= portfolioImportDate) setPortfolioRequiredDate(null);
          void refreshResources(["portfolio", "market", "notifications"]);
        }} />}
    </div>
  );
}

type NotificationRow = {
  id: string;
  task_id?: string | null;
  event_type: string;
  title: string;
  body: string;
  created_at: string;
  read_at?: string | null;
  data?: MarketAnomalies | { as_of: string; count: number };
};

function NotificationMark({ notification }: { notification: NotificationRow }) {
  const needsAttention = ["PortfolioRiskChanged", "DataQualityDegraded", "EventDeliveryFailed",
    "TaskFailed", "TaskWaitingApproval"].includes(notification.event_type);
  return <span className="notification-mark" aria-hidden="true">
    {needsAttention ? <WarningCircleIcon size={17} />
      : !notification.read_at && <span className="notification-unread-dot" />}
  </span>;
}

function notificationLabel(eventType: string) {
  const labels: Record<string, string> = {
    MarketClose: "收盘复盘",
    PortfolioRiskChanged: "持仓风险",
    FilingPublished: "公告事件",
    AnnouncementPublished: "公告事件",
    DataQualityDegraded: "数据质量",
    MarketBreadthChanged: "市场广度变化",
    PriceVolumeAnomaly: "量价异常",
    PriceVolumeDigest: "关注异动",
    PriceVolumeHistory: "历史异动研究",
    EventDeliveryFailed: "事件处理失败",
    TaskFailed: "任务失败",
    TaskWaitingApproval: "等待确认",
  };
  return labels[eventType] ?? eventType;
}

function AttentionFeed({ notifications, onOpenTask, onOpenDetail, load, onRetry }: {
  notifications: NotificationRow[];
  onOpenTask: (taskId: string) => void;
  onOpenDetail: (notification: NotificationRow) => void;
  load?: ResourceStatus;
  onRetry: () => void;
}) {
  const latest = notifications.slice(0, 3);
  return <section className="attention-panel panel">
    <div className="panel-header">
      <div><span className="eyebrow">Pia 正在关注</span><h2>需要你留意的变化</h2></div>
      <span className="attention-count">{notifications.filter((item) => !item.read_at).length} 未读</span>
    </div>
    {load?.error && <div className="attention-empty" role="status">通知暂不可用。<button className="text-button" onClick={onRetry}>重试通知</button></div>}
    {!load && <p className="attention-empty" role="status">正在读取通知…</p>}
    {latest.length === 0 ? load && !load.error && <div className="attention-empty"><strong>今天还没有需要处理的事件</strong><span>收盘、持仓风险和数据质量变化会自动出现在这里。</span></div> :
      <div className="attention-list">{latest.map((notification) => <article className={`attention-row ${notification.read_at ? "read" : ""}`} key={notification.id}>
        <NotificationMark notification={notification} />
        <div className="attention-copy">
          <div><span className="attention-type">{notificationLabel(notification.event_type)}</span><time>{formatDate(notification.created_at)}</time></div>
          <strong>{notification.title}</strong>
          <p>{notification.body}</p>
        </div>
        {notification.data
          ? <button className="quiet-button" onClick={() => onOpenDetail(notification)}>查看明细</button>
          : notification.task_id && <button className="quiet-button" onClick={() => onOpenTask(notification.task_id as string)}>查看研究</button>}
      </article>)}</div>}
  </section>;
}

function StrategyAgentPanel({
  profile,
  rules,
  health,
  portfolio,
  watchlists,
  tasks,
  dataTone,
  onNavigate,
}: {
  profile: Record<string, unknown> | null;
  rules: Record<string, unknown> | null;
  health: {
    status: string;
    provider: { status: string; provider_id?: string };
    scheduler?: { enabled: boolean; timezone: string; close_time: string; last_dispatched_date: string | null };
  } | null;
  portfolio: Record<string, unknown> | null;
  watchlists: Watchlist[];
  tasks: Task[];
  dataTone: string;
  onNavigate: (view: WorkspaceView) => void;
}) {
  const profilePayload = (profile?.payload ?? {}) as Record<string, unknown>;
  const objective = String(profilePayload.investment_objective ?? "");
  const objectiveLabel = objective.trim() ? displayInvestmentObjective(objective) : "还没有设置投资目标";
  const riskLabels: Record<string, string> = { conservative: "保守", moderate: "稳健", aggressive: "积极" };
  const riskTolerance = String(profilePayload.risk_tolerance ?? "");
  const riskLabel = riskLabels[riskTolerance] ?? (riskTolerance || "未设置");
  const drawdown = Number(profilePayload.drawdown_limit);
  const drawdownLabel = Number.isFinite(drawdown) && drawdown > 0 ? `${(drawdown * 100).toFixed(0)}%` : "未设置";
  const positions = Array.isArray(portfolio?.positions) ? portfolio.positions.length : 0;
  const watchedSymbols = Array.from(new Set(watchlists.flatMap((list) => list.symbols))).length;
  const activeTasks = tasks.filter((task) => ["QUEUED", "PLANNING", "RUNNING", "REVIEWING"].includes(task.status));
  const schedulerEnabled = Boolean(health?.scheduler?.enabled);
  const needsCheck = dataTone === "degraded" || dataTone === "unavailable";
  const agentStatus = needsCheck ? "需要检查" : activeTasks.length > 0 ? "正在研究" : schedulerEnabled ? "持续关注中" : "等待调度";
  const agentStatusTone = needsCheck ? "warning" : activeTasks.length > 0 ? "active" : "steady";
  const lastCheck = health?.scheduler?.last_dispatched_date ? formatDate(health.scheduler.last_dispatched_date) : "尚未运行";
  const targetLabel = (task: Task) => {
    const target = task.target ?? {};
    const symbols = Array.isArray(target.symbols) ? target.symbols.map(String) : [];
    const symbol = typeof target.symbol === "string" ? target.symbol : "";
    return symbols.join("、") || symbol || "市场复盘";
  };

  return <section className="strategy-agent-panel panel">
    <div className="strategy-agent-column">
      <div className="strategy-agent-heading"><span className="eyebrow">你的策略 · 规则 {String(rules?.version ?? "v1")}</span><button className="text-button strategy-link" onClick={() => onNavigate("Profile")}>查看策略<ArrowRightIcon size={16} aria-hidden="true" /></button></div>
      <h2>投资目标与纪律</h2>
      <p className="strategy-objective">{objectiveLabel}</p>
      <div className="strategy-facts">
        <div><span>风险偏好</span><strong>{riskLabel}</strong></div>
        <div><span>最大回撤</span><strong>{drawdownLabel}</strong></div>
        <div><span>研究范围</span><strong>{watchedSymbols + positions} 个标的</strong></div>
      </div>
    </div>
    <div className="strategy-agent-column agent-column">
      <div className="strategy-agent-heading"><span className="eyebrow">你的研究助手</span><span className={`agent-status ${agentStatusTone}`}><i className="agent-status-dot" />{agentStatus}</span></div>
      <p className="agent-summary">关注 {watchedSymbols} 个自选标的、{positions} 个持仓</p>
      <div className="agent-details">
        <div><span>上次检查</span><strong>{lastCheck}</strong></div>
        <div><span>当前规则</span><strong>{String(rules?.version ?? "v1")}</strong></div>
      </div>
      {activeTasks.length > 0 ? <div className="agent-tasks"><span>进行中的研究</span>{activeTasks.slice(0, 2).map((task) => <div key={task.id}><strong>{targetLabel(task)}</strong><span>{statusLabel(task.status)}</span></div>)}</div> : <div className="agent-next"><span>下一步</span><strong>{schedulerEnabled ? "等待市场变化或收盘调度" : "去数据页开启调度"}</strong></div>}
    </div>
  </section>;
}

function JournalView({ items, focusTaskId, onClearFocus, summary, patterns, onSaveCandidate, onReviewCandidate, onFeedbackCandidate, onOpenTask }: {
  items: JournalItem[];
  focusTaskId: string | null;
  onClearFocus: () => void;
  summary: JournalSummary | null;
  patterns: JournalPatterns | null;
  onSaveCandidate: (candidateKey: string) => void;
  onReviewCandidate: (candidateId: string, payload: {
    action: "CONFIRM" | "EDIT_AND_CONFIRM" | "REJECT" | "ARCHIVE";
    title?: string | null;
    content?: string | null;
    notes?: string;
  }) => void;
  onFeedbackCandidate: (candidateId: string, usageId: string, rating: "HELPFUL" | "NOT_HELPFUL" | "UNCERTAIN") => void;
  onOpenTask: (taskId: string) => void;
}) {
  const [activeTab, setActiveTab] = useState<"journal" | "patterns" | "memory">("journal");
  const [symbolFilter, setSymbolFilter] = useState("");
  const [intentFilter, setIntentFilter] = useState("all");
  const [editingCandidateId, setEditingCandidateId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const normalizedSymbol = symbolFilter.trim().toUpperCase();
  const visibleItems = items.filter((item) => {
    const record = item.decision_record;
    const symbols = record.subject.symbols ?? [];
    const symbolMatch = !normalizedSymbol || symbols.some((symbol) => symbol.includes(normalizedSymbol));
    const intentMatch = intentFilter === "all" || record.intent === intentFilter;
    return symbolMatch && intentMatch && (!focusTaskId || record.task.id === focusTaskId);
  });
  const retrospectiveCount = visibleItems.reduce((count, item) => count + item.retrospectives.length, 0);
  const actionCount = visibleItems.reduce((count, item) => count + item.retrospectives.filter((row) => row.action_taken === "APPROVE").length, 0);
  const notTakenCount = visibleItems.reduce((count, item) => count + item.retrospectives.filter((row) => ["NOT_TAKEN", "REJECT", "NO_ACTION"].includes(row.action_taken)).length, 0);
  const intents = Array.from(new Set(items.map((item) => item.decision_record.intent).filter(Boolean)));
  const numberValue = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : null;
  const countValue = (values: unknown, key: string) => {
    if (!values || typeof values !== "object") return 0;
    const value = (values as Record<string, unknown>)[key];
    return typeof value === "number" ? value : 0;
  };
  const patternRows = (values: Array<Record<string, unknown>> | undefined) => (values ?? []).map((pattern) => {
    const average = numberValue(pattern.average_return_pct);
    const benchmarkAverage = numberValue(pattern.average_benchmark_return_pct);
    const excessAverage = numberValue(pattern.average_excess_return_pct);
    const actions = pattern.action_counts as Record<string, unknown> | undefined;
    return <article className="pattern-row" key={String(pattern.key)}>
      <div className="pattern-heading">
        <strong>{String(pattern.key ?? "UNKNOWN")}</strong>
        <span>{String(pattern.sample_size ?? 0)} 次决策</span>
      </div>
      <div className="pattern-metrics">
        <span>{String(pattern.retrospective_count ?? 0)} 条后续记录</span>
        <span>{String(pattern.comparable_outcome_count ?? 0)} 个可比较结果</span>
        <span>{average === null ? "—" : `${average > 0 ? "+" : ""}${average.toFixed(2)}% 平均`}</span>
        {benchmarkAverage !== null && <span>{benchmarkAverage > 0 ? "+" : ""}{benchmarkAverage.toFixed(2)}% 基准</span>}
        {excessAverage !== null && <span>{excessAverage > 0 ? "+" : ""}{excessAverage.toFixed(2)}% 超额</span>}
        {actions && <span>{countValue(actions, "TAKEN")} 次采取 · {countValue(actions, "NOT_TAKEN")} 次未采取</span>}
      </div>
      <div className="pattern-meta">
        <span>正向结果 {String(pattern.positive_outcome_count ?? 0)}</span>
        <span>负向结果 {String(pattern.negative_outcome_count ?? 0)}</span>
        <span>规则提示 {String(pattern.rule_violation_count ?? 0)} 次拦截 / {String(pattern.rule_warning_count ?? 0)} 次警告</span>
      </div>
    </article>;
  });
  const tabs = [
    { id: "journal" as const, label: "决策日志" },
    { id: "patterns" as const, label: "模式" },
    { id: "memory" as const, label: "投资记忆" },
  ];
  return <section className="journal-view">
    <div className="journal-tabs" role="tablist" aria-label="决策日志视图">
      {tabs.map((tab) => <button
        className={`journal-tab ${activeTab === tab.id ? "active" : ""}`}
        key={tab.id}
        role="tab"
        aria-selected={activeTab === tab.id}
        onClick={() => setActiveTab(tab.id)}
      >{tab.label}</button>)}
    </div>
    {activeTab === "journal" && <div className="journal-layout">
      <div className="journal-summary">
        <Panel title="日志摘要" eyebrow="跨研究事实">
          <div className="journal-summary-grid">
            <div><strong>{visibleItems.length}</strong><span>研究决策</span></div>
            <div><strong>{retrospectiveCount}</strong><span>后续记录</span></div>
            <div><strong>{actionCount}</strong><span>采纳建议</span></div>
            <div><strong>{notTakenCount}</strong><span>未采取行动</span></div>
          </div>
          <p className="form-hint">这里展示已存在的研究事实，不把结果改写成当时的预测。</p>
        </Panel>
      </div>
      <Panel title={focusTaskId ? "这次研究的记录" : "决策时间线"} eyebrow={`${visibleItems.length} 条记录`}
        actions={focusTaskId && <button className="quiet-button" onClick={onClearFocus}>查看全部日志</button>}>
        <div className="journal-filters">
          <input value={symbolFilter} onChange={(event) => setSymbolFilter(event.target.value)} placeholder="筛选股票代码" aria-label="按股票代码筛选" />
          <select value={intentFilter} onChange={(event) => setIntentFilter(event.target.value)} aria-label="按决策意图筛选">
            <option value="all">全部决策</option>
            {intents.map((intent) => <option value={intent} key={intent}>{statusLabel(intent)}</option>)}
          </select>
        </div>
        {visibleItems.length === 0 ? <EmptyState message={items.length === 0 ? "还没有可回看的决策记录。" : "没有符合筛选条件的记录。"} /> :
          <div className="journal-list">{visibleItems.map((item) => {
            const record = item.decision_record;
            const task = record.task;
            const latestOutcome = item.retrospectives[0];
            return <article className="journal-row" key={task.id}>
              <div className="journal-date"><time>{formatDate(record.created_at)}</time><span>{String(record.data_snapshot_id ?? "没有数据快照")}</span></div>
              <div className="journal-main">
                <div className="journal-heading">
                  <strong>{record.subject.symbol ?? (record.subject.symbols.join(", ") || taskTitle(task))}</strong>
                  <span className={`decision-pill decision-${String(record.intent).toLowerCase()}`}>{statusLabel(record.intent)}</span>
                </div>
                <p>{record.next_action ? nextActionLabel(record.next_action) : "没有记录下一步动作。"}</p>
                <div className="journal-meta">
                  <span>规则 {String(record.rule_snapshot_id ?? "—")}</span>
                  <span>依据 {item.evidence_summary.count}</span>
                  {latestOutcome && <span>{localizedLabel(retrospectiveActionLabels, latestOutcome.action_taken)}</span>}
                </div>
                {latestOutcome?.notes && <p className="journal-notes">{latestOutcome.notes}</p>}
              </div>
              <button className="quiet-button" onClick={() => onOpenTask(task.id)}>查看研究</button>
            </article>;
          })}</div>}
      </Panel>
    </div>}
    {activeTab === "patterns" && <div className="pattern-layout">
      <Panel title="已观察摘要" eyebrow="跨研究事实">
        {!summary ? <EmptyState message="正在加载统计。" /> : <>
          <div className="journal-summary-grid">
            <div><strong>{summary.decision_count}</strong><span>研究决策</span></div>
            <div><strong>{summary.retrospective_count}</strong><span>后续记录</span></div>
            <div><strong>{summary.comparable_outcome_count}</strong><span>可比较结果</span></div>
            <div><strong>{summary.average_return_pct === null || summary.average_return_pct === undefined ? "—" : `${summary.average_return_pct > 0 ? "+" : ""}${summary.average_return_pct.toFixed(2)}%`}<span>平均结果</span></strong></div>
          </div>
          <div className="pattern-counts">
            {Object.entries(summary.action_counts).map(([key, value]) => <span key={key}>{key}: {value}</span>)}
          </div>
          {summary.warnings.map((warning) => <p className="journal-warning" key={warning}>{warning}</p>)}
        </>}
      </Panel>
      <Panel title="按意图查看模式" eyebrow="确定性统计">
        <p className="form-hint">这些是历史分组统计，不代表预测正确率，也不会自动生成交易动作。</p>
        {!patterns ? <EmptyState message="正在加载模式统计。" /> : patterns.intent_patterns.length ? <div className="pattern-list">{patternRows(patterns.intent_patterns)}</div> : <EmptyState message="还没有足够的决策记录形成分组。" />}
      </Panel>
      <Panel title="按规则快照查看模式" eyebrow="区分版本的统计">
        {!patterns ? <EmptyState message="正在加载模式统计。" /> : patterns.rule_patterns.length ? <div className="pattern-list">{patternRows(patterns.rule_patterns)}</div> : <EmptyState message="还没有规则快照统计。" />}
      </Panel>
    </div>}
    {activeTab === "memory" && <div className="memory-layout">
      <Panel title="投资记忆候选" eyebrow="确认前先复核">
        <p className="form-hint">候选模式来自确定性统计，尚未确认，不会影响未来研究，也不会生成买卖指令。</p>
        {!patterns ? <EmptyState message="正在加载候选模式。" /> : patterns.memory_candidates.length === 0 ? <EmptyState message="暂时没有候选模式。" /> :
          <div className="memory-list">{patterns.memory_candidates.map((candidate) => {
            const average = numberValue(candidate.average_return_pct);
            const benchmarkAverage = numberValue(candidate.average_benchmark_return_pct);
            const excessAverage = numberValue(candidate.average_excess_return_pct);
            const usageAverage = numberValue(candidate.usage_average_return_pct);
            const usageCount = typeof candidate.usage_count === "number" ? candidate.usage_count : 0;
            const latestUsageId = typeof candidate.latest_usage_id === "string" ? candidate.latest_usage_id : null;
            const usageOutcomeCount = typeof candidate.usage_outcome_count === "number" ? candidate.usage_outcome_count : 0;
            const usageTaskIds = Array.isArray(candidate.usage_task_ids) ? candidate.usage_task_ids : [];
            const helpfulCount = typeof candidate.helpful_count === "number" ? candidate.helpful_count : 0;
            const notHelpfulCount = typeof candidate.not_helpful_count === "number" ? candidate.not_helpful_count : 0;
            const uncertainCount = typeof candidate.uncertain_count === "number" ? candidate.uncertain_count : 0;
            const feedbackRecommendation = String(candidate.feedback_recommendation ?? "NO_FEEDBACK");
            const sourceIds = Array.isArray(candidate.source_task_ids) ? candidate.source_task_ids : [];
            const candidateId = typeof candidate.memory_candidate_id === "string" ? candidate.memory_candidate_id : null;
            const status = String(candidate.status ?? "UNSAVED");
            const isEditing = editingCandidateId === candidateId;
            const statusLabel = status === "CONFIRMED"
              ? "已确认"
              : status === "REJECTED"
                ? "已拒绝"
                : status === "ARCHIVED"
                  ? "已归档"
                  : status === "CANDIDATE"
                    ? "已保存候选"
                    : candidate.eligible
                      ? "达到最低门槛"
                      : "样本不足";
            return <article className="memory-candidate" key={`${String(candidate.kind)}-${String(candidate.title)}`}>
              <div className="pattern-heading">
                <strong>{String(candidate.title ?? "未命名候选")}</strong>
                <span className={status === "CONFIRMED" ? "candidate-eligible" : status === "CANDIDATE" ? "candidate-saved" : "candidate-pending"}>
                  {statusLabel}
                </span>
              </div>
              {isEditing && <div className="memory-edit-form">
                <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} aria-label="记忆标题" />
                <textarea value={editContent} onChange={(event) => setEditContent(event.target.value)} aria-label="记忆内容" rows={3} />
              </div>}
              <p>{String(candidate.reason ?? "")}</p>
              <div className="pattern-metrics">
                <span>{String(candidate.sample_size ?? 0)} 次决策</span>
                <span>{String(candidate.comparable_outcome_count ?? 0)} 个可比较结果</span>
                <span>{average === null ? "—" : `${average > 0 ? "+" : ""}${average.toFixed(2)}% 平均`}</span>
                {benchmarkAverage !== null && <span>{benchmarkAverage > 0 ? "+" : ""}{benchmarkAverage.toFixed(2)}% 基准</span>}
                {excessAverage !== null && <span>{excessAverage > 0 ? "+" : ""}{excessAverage.toFixed(2)}% 超额</span>}
                {status === "CONFIRMED" && <span>{usageCount} 次上下文使用</span>}
                {status === "CONFIRMED" && <span>{usageOutcomeCount} 次使用后结果</span>}
                {status === "CONFIRMED" && usageAverage !== null && <span>{usageAverage > 0 ? "+" : ""}{usageAverage.toFixed(2)}% 使用后</span>}
                {status === "CONFIRMED" && <span>反馈：{helpfulCount} 有帮助 · {notHelpfulCount} 无帮助 · {uncertainCount} 不确定</span>}
              </div>
              <div className="pattern-meta"><span>来源研究：{sourceIds.length ? sourceIds.map(String).join(" · ") : "—"}</span></div>
              {status === "CONFIRMED" && <div className="pattern-meta"><span>使用于：{usageTaskIds.length ? usageTaskIds.map(String).join(" · ") : "尚未用于后续研究"}</span></div>}
              {status === "CONFIRMED" && latestUsageId && candidateId && <div className="memory-feedback">
                <span className="form-hint">累计反馈建议：{feedbackRecommendation === "ARCHIVE_SUGGESTED" ? "建议归档" : feedbackRecommendation === "REVIEW_SUGGESTED" ? "建议复查" : feedbackRecommendation === "KEEP" ? "继续保留" : "尚未反馈"}</span>
                <span className="form-hint">最近一次使用：{String(usageTaskIds[0] ?? "")}</span>
                <div className="memory-actions">
                  <button className="quiet-button" onClick={() => onFeedbackCandidate(candidateId, latestUsageId, "HELPFUL")}>有帮助</button>
                  <button className="quiet-button" onClick={() => onFeedbackCandidate(candidateId, latestUsageId, "NOT_HELPFUL")}>无帮助</button>
                  <button className="quiet-button" onClick={() => onFeedbackCandidate(candidateId, latestUsageId, "UNCERTAIN")}>不确定</button>
                </div>
              </div>}
              {candidate.eligible === true && status === "UNSAVED" && <button className="quiet-button memory-save-button" onClick={() => onSaveCandidate(String(candidate.candidate_key))}>保存候选</button>}
              {candidateId && status === "CANDIDATE" && !isEditing && <div className="memory-actions">
                <button className="quiet-button" onClick={() => onReviewCandidate(candidateId, { action: "CONFIRM" })}>确认</button>
                <button className="quiet-button" onClick={() => {
                  setEditingCandidateId(candidateId);
                  setEditTitle(String(candidate.title ?? ""));
                  setEditContent(String(candidate.content ?? ""));
                }}>编辑并确认</button>
                <button className="quiet-button" onClick={() => onReviewCandidate(candidateId, { action: "REJECT" })}>拒绝</button>
                <button className="quiet-button" onClick={() => onReviewCandidate(candidateId, { action: "ARCHIVE" })}>归档</button>
              </div>}
              {candidateId && status === "CANDIDATE" && isEditing && <div className="memory-actions">
                <button className="quiet-button" onClick={() => {
                  onReviewCandidate(candidateId, {
                    action: "EDIT_AND_CONFIRM",
                    title: editTitle,
                    content: editContent,
                  });
                  setEditingCandidateId(null);
                }}>保存并确认</button>
                <button className="quiet-button" onClick={() => setEditingCandidateId(null)}>取消</button>
              </div>}
              {candidateId && status === "CONFIRMED" && <div className="memory-actions">
                <button className="quiet-button" onClick={() => onReviewCandidate(candidateId, { action: "ARCHIVE" })}>归档</button>
              </div>}
            </article>;
          })}</div>}
      </Panel>
      {patterns?.warnings.map((warning) => <p className="journal-warning" key={warning}>{warning}</p>)}
    </div>}
  </section>;
}

function NotificationsView({
  notifications,
  onRead,
  onEnablePush,
  pushStatus,
  onOpenTask,
  onOpenDetail,
}: {
  notifications: NotificationRow[];
  onRead: (notification: NotificationRow) => void;
  onEnablePush: () => void;
  pushStatus: string;
  onOpenTask: (taskId: string) => void;
  onOpenDetail: (notification: NotificationRow) => void;
}) {
  return <section className="single-panel panel notifications-panel">
    <div className="panel-header">
      <div><span className="eyebrow">事件收件箱</span><h2>通知</h2></div>
      <span className="count">{notifications.filter((item) => !item.read_at).length}</span>
    </div>
    <div className="form-row">
      <button className="quiet-button" onClick={onEnablePush}>启用浏览器通知</button>
      <span className="form-hint">{pushStatus || "浏览器通知通过已注册的设备通道发送。"}</span>
    </div>
    {notifications.length === 0 ? <EmptyState message="还没有通知。任务失败、数据质量降级和审批事件会显示在这里。" /> :
      <div className="notification-list">{notifications.map((notification) => <article className={`notification-row ${notification.read_at ? "read" : "unread"}`} key={notification.id}>
        <NotificationMark notification={notification} />
        <div className="notification-copy">
          <div className="notification-heading"><strong>{notification.title}</strong><time>{formatDate(notification.created_at)}</time></div>
          <p>{notification.body}</p>
          <span>{notificationLabel(notification.event_type)}{notification.event_type === "PriceVolumeDigest" && notification.data ? ` · ${notification.data.as_of}` : ""}</span>
        </div>
        <div className="notification-actions">
          {notification.data
            ? <button className="quiet-button" onClick={() => onOpenDetail(notification)}>查看明细</button>
            : notification.task_id && <button className="quiet-button" onClick={() => onOpenTask(notification.task_id as string)}>查看研究</button>}
          {!notification.read_at && <button className="quiet-button" onClick={() => onRead(notification)}>标为已读</button>}
        </div>
      </article>)}</div>}
  </section>;
}

function AnomalyNotificationDialog({ notification, busy, onClose, onOpenTask, onResearch, children }: {
  notification: NotificationRow;
  busy: boolean;
  onClose: () => void;
  onOpenTask: (taskId: string) => void;
  onResearch: (symbol: string, anomaly: MarketAnomalies) => void;
  children: ReactNode;
}) {
  const api = useWorkspaceApi();
  const [history, setHistory] = useState<HistoricalAnomalyTask[]>();
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(25);
  const data = notification.data;
  const legacy = data !== undefined && "count" in data;
  useEffect(() => {
    if (!legacy) return;
    let active = true;
    void api.notificationAnomalies(notification.id).then(({ items }) => {
      if (active) setHistory(items);
    }).catch((requestError) => {
      if (active) setError(friendlyError(requestError, "历史异动明细暂不可用。"));
    });
    return () => { active = false; };
  }, [api, legacy, notification.id]);

  return <WorkspaceDialog title={notification.title} pending={busy} onClose={onClose} wide>
    {children}
    {data && "items" in data && <MarketAnomalyList data={data} busy={busy} onResearch={onResearch} />}
    {legacy && (history ? <div className="anomaly-list">
      {history.slice(0, visible).map((task) => <div className="anomaly-row" key={task.task_id}>
        <div><strong>{task.symbol ?? "标的未记录"}</strong><small>{statusLabel(task.status)}</small></div>
        <span>{task.error?.code === "PORTFOLIO_AS_OF_UNAVAILABLE" ? "缺少持仓快照" : (task.error?.message || task.error?.code)}</span>
        <button type="button" className="quiet-button" onClick={() => onOpenTask(task.task_id)}>查看研究</button>
      </div>)}
      {visible < history.length && <button type="button" className="text-button" onClick={() => setVisible(visible + 25)}>显示更多</button>}
    </div> : <p className="form-hint" role="status">{error || "正在读取历史异动明细…"}</p>)}
    <div className="runtime-dialog-actions"><button type="button" className="quiet-button" disabled={busy} onClick={onClose}>关闭</button></div>
  </WorkspaceDialog>;
}

const TASK_GROUPS: Array<{ key: string; label: string; statuses: string[] }> = [
  { key: "active", label: "进行中", statuses: ["QUEUED", "PLANNING", "RUNNING", "REVIEWING", "PAUSED"] },
  { key: "approval", label: "等待确认", statuses: ["WAITING_APPROVAL"] },
  { key: "blocked", label: "已阻断", statuses: ["BLOCKED", "NO_ACTION"] },
  { key: "completed", label: "已完成", statuses: ["APPROVED", "REJECTED", "DONE"] },
  { key: "failed", label: "失败或过期", statuses: ["RETRYABLE", "FAILED", "TIMEOUT", "EXPIRED", "CANCELLED"] },
];

function TaskQueue({ tasks, selectedId, onSelect, onOpen }: {
  tasks: Task[];
  selectedId: string | null;
  onSelect: (taskId: string) => void;
  onOpen: (taskId: string) => void;
}) {
  const orderedTasks = TASK_GROUPS.flatMap((group) => tasks.filter((task) => group.statuses.includes(task.status)));
  const moveSelection = (currentId: string | null, direction: 1 | -1) => {
    if (!orderedTasks.length) return;
    const currentIndex = currentId ? orderedTasks.findIndex((task) => task.id === currentId) : -1;
    const nextIndex = currentIndex < 0
      ? 0
      : (currentIndex + direction + orderedTasks.length) % orderedTasks.length;
    const nextTask = orderedTasks[nextIndex];
    onSelect(nextTask.id);
    window.requestAnimationFrame(() => document.getElementById(`task-${nextTask.id}`)?.focus());
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      event.preventDefault();
      moveSelection(selectedId, 1);
    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      event.preventDefault();
      moveSelection(selectedId, -1);
    } else if (event.key === "Home" && orderedTasks.length) {
      event.preventDefault();
      onSelect(orderedTasks[0].id);
      window.requestAnimationFrame(() => document.getElementById(`task-${orderedTasks[0].id}`)?.focus());
    } else if (event.key === "End" && orderedTasks.length) {
      event.preventDefault();
      const lastTask = orderedTasks[orderedTasks.length - 1];
      onSelect(lastTask.id);
      window.requestAnimationFrame(() => document.getElementById(`task-${lastTask.id}`)?.focus());
    }
  };
  return <div className="task-groups" role="listbox" aria-label="研究任务" tabIndex={0} onKeyDown={handleKeyDown}>{TASK_GROUPS.map((group) => {
    const grouped = tasks.filter((task) => group.statuses.includes(task.status));
    if (!grouped.length) return null;
    return <section className="task-group" key={group.key}>
      <div className="task-group-heading"><span>{group.label}</span><strong>{grouped.length}</strong></div>
      {grouped.map((task) => <button id={`task-${task.id}`} role="option" aria-selected={selectedId === task.id} key={task.id} className={`queue-row ${selectedId === task.id ? "selected" : ""}`} onClick={() => onOpen(task.id)}>
        <div className="queue-row-top"><StatusBadge status={task.status} /><time>{formatDate(task.created_at)}</time></div>
        <strong>{task.trigger_type === "DailyHoldingsReview" ? "收盘持仓复核" : task.trigger_type === "MarketClose" ? "收盘市场复盘" : task.trigger_type === "StockResearch" && task.target.symbol ? `${String(task.target.symbol)} 研究` : task.trigger_type}</strong>
        <span>{String(task.target.as_of ?? "日期未记录")} · {task.id.slice(-6)}</span>
      </button>)}
    </section>;
  })}</div>;
}

function watchlistName(name: string) {
  return name === DEFAULT_WATCHLIST ? "研究自选" : name;
}

function WatchlistView({ watchlists, onSaved, onResearch, onOpenMarket, latest, instruments, taskLoad, busy, onRetryTasks, onOpenTask }: {
  watchlists: Watchlist[];
  latest: ReadonlyMap<string, Task>;
  instruments: ReadonlyMap<string, string>;
  taskLoad?: ResourceStatus;
  busy: boolean;
  onSaved: (name: string, symbols: string[], append: boolean) => Promise<void>;
  onResearch: (symbol: string) => void;
  onOpenMarket: () => void;
  onRetryTasks: () => void;
  onOpenTask: (taskId: string) => void;
}) {
  const [editor, setEditor] = useState<Watchlist | "add" | null>(null);
  const [listName, setListName] = useState(DEFAULT_WATCHLIST);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const editing = editor && editor !== "add" ? editor : null;

  const openEditor = (list: Watchlist | "add") => {
    setEditor(list);
    setListName(list === "add" ? DEFAULT_WATCHLIST : list.name);
    setError("");
    setStatus("");
  };
  const closeEditor = () => setEditor(null);

  return <section className="control-grid">
    <Panel title="自选列表" wide actions={
      <div className="workspace-actions">
        <button className="quiet-button" type="button" onClick={onOpenMarket}>查看市场候选</button>
        <button className="primary-button" type="button" onClick={() => openEditor("add")}><PlusIcon size={16} aria-hidden="true" />添加自选</button>
      </div>
    }>
      {taskLoad?.error && <p className="form-hint" role="status">暂时无法确认最近的研究。<button className="text-button" onClick={onRetryTasks}>重试读取</button></p>}
      {watchlists.length === 0 ? <EmptyState message="还没有自选标的。" /> :
        <div className="watchlist-list">{watchlists.map((watchlist) => <article className="watchlist-row" key={watchlist.id}>
          <div><strong>{watchlistName(watchlist.name)}</strong><span>{watchlist.symbols.length} 个标的</span></div>
          <div className="watchlist-symbols">{watchlist.symbols.map((symbol) => {
            const code = stockCode(symbol) ?? symbol;
            const task = latest.get(code);
            const name = instruments.get(code);
            const historyReady = Boolean(taskLoad && !taskLoad.error);
            return <div className="watchlist-stock" key={symbol}>
              <button className="quiet-button" title={task ? "打开已有研究" : "开始研究"}
                disabled={busy || (!task && !historyReady)}
                onClick={() => task ? onOpenTask(task.id) : onResearch(code)}>
                <strong>{name ? `${name} ${symbol}` : symbol}</strong>
                <small>{task ? `${statusLabel(task.status)} · ${String(task.target.as_of ?? "日期未记录")}` : historyReady ? "开始研究" : "等待研究记录"}</small>
              </button>
              {task && <button className="text-button" disabled={busy} aria-label={`重新研究 ${symbol}`} onClick={() => onResearch(code)}>重新研究</button>}
            </div>;
          })}</div>
          <button className="text-button watchlist-edit" type="button" aria-label={`编辑${watchlistName(watchlist.name)}列表`} onClick={() => openEditor(watchlist)}>编辑列表</button>
        </article>)}</div>}
      {status && <p className="form-hint" role="status">{status}</p>}
    </Panel>
    {editor && <WorkspaceDialog title={editing ? "编辑自选列表" : "添加自选"} pending={saving} onClose={closeEditor}>
      <form onSubmit={async (event) => {
        event.preventDefault();
        if (saving) return;
        const fields = new FormData(event.currentTarget);
        const name = listName || String(fields.get("list_name") ?? "").trim();
        const symbols = String(fields.get("symbols") ?? "").toUpperCase().split(/[,，\s]+/).filter(Boolean);
        if (!name || symbols.length === 0) {
          setError("请填写列表名称和至少一个标的代码。");
          return;
        }
        setSaving(true);
        setError("");
        try {
          await onSaved(name, symbols, !editing);
          setStatus(editing ? "自选列表已更新。" : `已加入「${watchlistName(name)}」。`);
          closeEditor();
        } catch (requestError) {
          setError(friendlyError(requestError, "保存自选失败，请重试。"));
        } finally {
          setSaving(false);
        }
      }}>
        <fieldset className="runtime-fields dialog-fields" disabled={saving}>
          {editing ? <label>列表<input value={watchlistName(editing.name)} readOnly /></label> :
            <label>加入列表<select value={listName} onChange={(event) => setListName(event.target.value)}>
              <option value={DEFAULT_WATCHLIST}>{watchlistName(DEFAULT_WATCHLIST)}</option>
              {watchlists.filter((list) => list.name !== DEFAULT_WATCHLIST).map((list) => <option key={list.id} value={list.name}>{list.name}</option>)}
              <option value="">新建列表</option>
            </select></label>}
          {!listName && <label>列表名称<input name="list_name" required /></label>}
          <label>股票或 ETF 代码<textarea name="symbols" rows={3} required defaultValue={editing?.symbols.join(", ") ?? ""}
            placeholder="600000.SH, 510300.SH" /></label>
          <small>多个代码可用逗号或空格分隔。</small>
        </fieldset>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <div className="runtime-dialog-actions">
          <button className="quiet-button" type="button" onClick={closeEditor} disabled={saving}>取消</button>
          <button className="primary-button" disabled={saving}>{saving ? "正在保存…" : editing ? "保存列表" : "加入自选"}</button>
        </div>
      </form>
    </WorkspaceDialog>}
  </section>;
}

function ChartFrame({ title, unit, asOf, source, children }: {
  title: string;
  unit: string;
  asOf: string;
  source: string;
  children: ReactNode;
}) {
  return <article className="chart-frame" tabIndex={0} aria-label={`${title}，${unit}，截至 ${asOf}，来源 ${source}`}>
    <div className="chart-heading"><div><strong>{title}</strong><span>{unit}</span></div><small>{asOf} · {source}</small></div>
    {children}
  </article>;
}

function HorizontalBars({ items, empty = "暂无数据" }: {
  items: Array<{ label: string; value: number; display: string; tone?: "positive" | "negative" | "neutral" }>;
  empty?: string;
}) {
  if (!items.length) return <div className="chart-empty">{empty}</div>;
  const max = Math.max(...items.map((item) => Math.abs(item.value)), 1);
  return <div className="chart-bars">{items.map((item) => {
    const width = `${Math.max(4, Math.min(100, Math.abs(item.value) / max * 100))}%`;
    return <div className="chart-bar-row" key={item.label}>
      <span className="chart-label">{item.label}</span>
      <span className="chart-track"><span className={`chart-fill ${item.tone ?? "neutral"}`} style={{ width }} /></span>
      <strong className="chart-value">{item.display}</strong>
    </div>;
  })}</div>;
}

function MarketCharts({ market, indices }: {
  market: Record<string, unknown>;
  indices: Array<{ name: string; close: number; change_pct: number }>;
}) {
  const breadth = Math.max(0, Math.min(1, Number(market.breadth ?? 0)));
  const asOf = String(market.as_of ?? "—");
  const source = String(market.source ?? "未知");
  return <div className="chart-grid">
    <ChartFrame title="市场宽度" unit="% 上涨" asOf={asOf} source={source}>
      <div className="chart-gauge" aria-label={`${(breadth * 100).toFixed(1)}% 上涨`}>
        <span className="chart-gauge-fill" style={{ width: `${breadth * 100}%` }} />
      </div>
      <div className="chart-caption"><strong>{(breadth * 100).toFixed(1)}%</strong><span>上涨宽度</span></div>
    </ChartFrame>
    <ChartFrame title="指数趋势" unit="% 日变化" asOf={asOf} source={source}>
      <HorizontalBars items={indices.map((index) => ({
        label: index.name,
        value: Number(index.change_pct),
        display: `${index.change_pct >= 0 ? "+" : ""}${index.change_pct.toFixed(2)}%`,
        tone: index.change_pct > 0 ? "positive" : index.change_pct < 0 ? "negative" : "neutral",
      }))} />
    </ChartFrame>
  </div>;
}

function PortfolioCharts({ portfolio, positions }: {
  portfolio: Record<string, unknown> | null;
  positions: Array<Record<string, unknown>>;
}) {
  const asOf = String(portfolio?.as_of ?? "—");
  const source = String(portfolio?.source ?? "未知");
  const drawdown = Math.max(0, Number(portfolio?.drawdown ?? 0));
  return <div className="chart-grid">
    <ChartFrame title="持仓暴露" unit="% 总市值" asOf={asOf} source={source}>
      <HorizontalBars items={positions.map((position) => ({
        label: String(position.symbol),
        value: Number(position.weight ?? 0) * 100,
        display: `${(Number(position.weight ?? 0) * 100).toFixed(1)}%`,
        tone: "neutral",
      }))} />
    </ChartFrame>
    <ChartFrame title="回撤" unit="% 较高点" asOf={asOf} source={source}>
      <div className="chart-gauge drawdown">
        <span className="chart-gauge-fill negative" style={{ width: `${Math.min(100, drawdown * 100)}%` }} />
      </div>
      <div className="chart-caption"><strong>{(drawdown * 100).toFixed(1)}%</strong><span>当前回撤</span></div>
    </ChartFrame>
  </div>;
}

function AgentTimelineChart({ trace, asOf, source }: {
  trace: TraceRow[];
  asOf: string;
  source: string;
}) {
  const durations = trace.map((row) => {
    const started = new Date(row.started_at).getTime();
    const finished = row.finished_at ? new Date(row.finished_at).getTime() : Date.now();
    return {
      label: researchAgentLabel(row.agent_name),
      value: Math.max(1, finished - started),
      display: `${Math.max(1, finished - started)} 毫秒`,
      tone: row.status === "FAILED" ? "negative" as const : row.status === "RUNNING" ? "positive" as const : "neutral" as const,
    };
  });
  return <ChartFrame title="研究过程时间线" unit="耗时" asOf={asOf} source={source}>
    <HorizontalBars items={durations} empty="还没有研究过程记录" />
  </ChartFrame>;
}

const DEFAULT_SCAN_STRATEGY = { strategy_id: "legacy_momentum_v1", version: "1.0.0" };
const scanSourceLabels = { fixture: "演示行情", akshare: "AKShare", tushare: "Tushare" };
const scanExclusionLabels: Record<string, string> = {
  INELIGIBLE_INSTRUMENT: "ST、停牌或退市风险",
  PROFILE_ASSET_TYPE: "超出投资设置的资产范围",
  PROFILE_UNIVERSE: "超出投资设置的市场范围",
  RULE_NEW_LISTING: "上市时间未达规则要求",
  RULE_LIQUIDITY: "成交额未达规则要求",
  MISSING_AVERAGE_TURNOVER: "缺少平均成交额",
  MISSING_CHANGE_PCT: "缺少涨跌幅",
  MISSING_BREADTH: "缺少市场宽度",
  MISSING_LISTED_DAYS: "缺少上市天数",
};

type MarketCandidatesProps = {
  asOf: string | undefined;
  source: string | undefined;
  fixture: string | undefined;
  pending: boolean;
  savedScan: CandidateListResponse | null;
  watchlists: Watchlist[];
  onScanned: (result: CandidateListResponse) => void;
  onWatch: (symbol: string) => Promise<void>;
  onResearch: (symbol: string) => void;
  onOpenData: () => void;
};

function MarketCandidates({ asOf, source, fixture, pending, savedScan, watchlists, onScanned, onWatch, onResearch, onOpenData }: MarketCandidatesProps) {
  const api = useWorkspaceApi();
  const [strategies, setStrategies] = useState([DEFAULT_SCAN_STRATEGY]);
  const [strategy, setStrategy] = useState(() => {
    const id = savedScan?.strategy_id ?? DEFAULT_SCAN_STRATEGY.strategy_id;
    const version = savedScan?.strategy_version ?? DEFAULT_SCAN_STRATEGY.version;
    return `${id}@${version}`;
  });
  const [scan, setScan] = useState(savedScan);
  const [scanBusy, setScanBusy] = useState(Boolean(asOf && !savedScan));
  const [scanError, setScanError] = useState("");
  const [failedReplay, setFailedReplay] = useState(false);
  const [showExcluded, setShowExcluded] = useState(false);
  const [savingSymbol, setSavingSymbol] = useState("");
  const [watchError, setWatchError] = useState("");

  useEffect(() => {
    if (!asOf) return;
    let cancelled = false;
    void api.screeningStrategies().then(({ strategies }) => {
      if (!cancelled && strategies.length > 0) setStrategies(strategies);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [asOf]);

  useEffect(() => {
    if (!asOf || savedScan) return;
    let cancelled = false;
    void api.candidates(asOf, fixture).then((result) => {
      if (!cancelled) setScan(result);
    }).catch((error) => {
      if (!cancelled) setScanError(friendlyError(error, "请检查数据源或稍后重试。"));
    }).finally(() => {
      if (!cancelled) setScanBusy(false);
    });
    return () => { cancelled = true; };
  }, [asOf, fixture, savedScan]);

  const executeScan = async (replay = false) => {
    if (!asOf || scanBusy) return;
    setScanBusy(true);
    setScanError("");
    setShowExcluded(false);
    try {
      const [id, version] = strategy.split("@");
      const result = replay && scan?.scan_id ? await api.replayCandidateScan(scan.scan_id)
        : await api.createCandidateScan(asOf, id, version, fixture);
      setScan(result);
      onScanned(result);
    } catch (error) {
      setScanError(friendlyError(error, "请检查数据源或稍后重试。"));
      setFailedReplay(replay);
    } finally {
      setScanBusy(false);
    }
  };

  const savedSymbols = new Set(watchlists.flatMap((list) => list.symbols));
  const result = !scanBusy && !scanError ? scan : null;
  const excluded = result?.excluded ?? [];
  const sourceLabel = localizedLabel(scanSourceLabels, source, "来源未知");
  const resultSource = localizedLabel(scanSourceLabels, result?.source ?? result?.candidates[0]?.source, sourceLabel);
  const scanSummary = result
    ? `${result.as_of ?? asOf} · ${resultSource} · ${result.candidates.length} 只候选`
    : asOf ? `${asOf} · ${sourceLabel}` : undefined;

  let notice: ReactNode;
  if (pending) {
    notice = <div className="scan-state" role="status"><strong>正在读取行情快照</strong></div>;
  } else if (!asOf) {
    notice = <div className="scan-state">
      <div><strong>缺少可用行情</strong><p>{source === "fixture"
        ? "当前只有演示行情。同步真实行情后可以扫描。"
        : "同步市场数据后，就能按策略筛选候选。"}</p></div>
      <button className="primary-button" type="button" onClick={onOpenData}>前往数据页<ArrowRightIcon size={16} aria-hidden="true" /></button>
    </div>;
  } else if (scanBusy) {
    notice = <div className="scan-state" role="status"><strong>正在扫描行情</strong></div>;
  } else if (scanError) {
    notice = <div className="scan-state" role="alert"><div><strong>扫描失败</strong><p>{scanError}</p></div></div>;
  } else if (!result) {
    notice = <div className="scan-state"><strong>点击「扫描」，查看所选策略的候选。</strong></div>;
  } else if (result.candidates.length === 0) {
    notice = <div className="scan-state" role="status">
      <div><strong>扫描完成，0 只符合条件</strong><p>{excluded.length > 0 ? `${excluded.length} 只标的被筛除。` : "行情快照中没有可供筛选的标的。"}</p></div>
    </div>;
  }

  return <div id="market-candidates" className="wide" tabIndex={-1}>
    <Panel title="候选扫描" eyebrow={scanSummary} actions={asOf && <div className="scan-controls">
      <label>策略 <select value={strategy} disabled={scanBusy} onChange={(event) => {
        setStrategy(event.target.value);
        setScan(null);
        setScanError("");
      }}>
        {strategies.map((item) => <option key={`${item.strategy_id}@${item.version}`} value={`${item.strategy_id}@${item.version}`}>
          {item.strategy_id === DEFAULT_SCAN_STRATEGY.strategy_id ? "动量与成交额" : item.strategy_id} · {item.version}
        </option>)}
      </select></label>
      <button className="quiet-button" type="button" onClick={() => void executeScan(Boolean(scanError && failedReplay))} disabled={scanBusy}>
        <MagnifyingGlassIcon size={16} aria-hidden="true" />{scanError ? "重试扫描" : "扫描"}
      </button>
      {scan?.scan_id && !scanError && <button className="quiet-button" type="button" onClick={() => void executeScan(true)} disabled={scanBusy}>
        <ArrowCounterClockwiseIcon size={16} aria-hidden="true" />复算
      </button>}
    </div>}>
      {notice}
      {result && result.candidates.length > 0 &&
      <div className="data-table">{result.candidates.map((candidate) => {
        const symbol = String(candidate.symbol);
        const saved = savedSymbols.has(symbol);
        return <div className="data-row candidate-row" key={symbol}>
          <strong>{symbol}</strong>
          <span>{String(candidate.name ?? symbol)} · 评分 {Number(candidate.score).toFixed(2)}</span>
          <button className="quiet-button" type="button" aria-label={saved ? `${symbol} 已在自选` : `加入自选 ${symbol}`}
            disabled={saved || Boolean(savingSymbol)} onClick={async () => {
              setSavingSymbol(symbol);
              setWatchError("");
              try {
                await onWatch(symbol);
              } catch (error) {
                setWatchError(friendlyError(error, "加入自选失败，请重试。"));
              } finally {
                setSavingSymbol("");
              }
            }}>{saved ? "已在自选" : savingSymbol === symbol ? "正在加入…" : "加入自选"}</button>
          <button className="quiet-button" type="button" onClick={() => onResearch(symbol)}>开始研究</button>
          <details className="candidate-factors"><summary>评分依据</summary>
            {Array.isArray(candidate.factors) && candidate.factors.map((factor) => <p key={String(factor.id)}>
              • {String(factor.id)} · {Number(factor.value).toLocaleString(undefined, { maximumFractionDigits: 6 })} × {Number(factor.weight).toLocaleString(undefined, { maximumFractionDigits: 6 })} = {Number(factor.contribution).toLocaleString(undefined, { maximumFractionDigits: 6 })}
            </p>)}
            <small>{String(candidate.snapshot_id)} · {localizedLabel(qualityLabels, candidate.quality, "未知")}</small>
            {Array.isArray(candidate.warnings) && candidate.warnings.map((warning) => <p key={String(warning)}>{localizedLabel(scanExclusionLabels, warning)}</p>)}
          </details>
        </div>;
      })}</div>}
      {watchError && <p className="form-hint" role="alert">{watchError}</p>}
      {excluded.length > 0 && <details className="scan-exclusions" onToggle={(event) => setShowExcluded(event.currentTarget.open)}>
        <summary>查看筛除原因（{excluded.length}）</summary>
        {showExcluded && <ul>{excluded.map((item, index) => <li key={`${String(item.symbol)}-${index}`}>
          <strong>{String(item.symbol)}</strong>{" · "}{Array.isArray(item.reason_codes) ? item.reason_codes.map((reason) => localizedLabel(scanExclusionLabels, reason)).join("、") : "未记录原因"}
        </li>)}</ul>}
      </details>}
    </Panel>
  </div>;
}

function MarketAnomalyList({ data, busy, market = false, onResearch }: {
  data: MarketAnomalies;
  busy: boolean;
  market?: boolean;
  onResearch: (symbol: string, anomaly: MarketAnomalies) => void;
}) {
  const [reason, setReason] = useState("all");
  const [followedOnly, setFollowedOnly] = useState(false);
  const [visible, setVisible] = useState(8);
  const filtered = data.items.filter((item) =>
    (!followedOnly || item.followed) && (
      reason === "all" || (reason === "price" ? item.price_triggered : item.volume_triggered)
    ),
  );
  return <div className="anomaly-list">
    {market && data.items.length > 0 && <div className="anomaly-filters">
      <label>触发原因 <select value={reason} onChange={(event) => { setReason(event.target.value); setVisible(8); }}>
        <option value="all">全部</option>
        <option value="price">涨跌幅达阈值</option>
        <option value="volume">量比 ≥ 2</option>
      </select></label>
      <label><input type="checkbox" checked={followedOnly} onChange={(event) => { setFollowedOnly(event.target.checked); setVisible(8); }} /> 只看持仓和自选</label>
      <span role="status">{filtered.length} 个标的</span>
    </div>}
    {!market && <p className="anomaly-date">交易日 {data.as_of}</p>}
    {filtered.length === 0
      ? <EmptyState message={data.items.length ? "当前筛选条件下没有异动。" : "这份快照中没有标的达到异动阈值。"} />
      : filtered.slice(0, visible).map((item) => <div className="anomaly-row" key={item.symbol}>
        <div><strong>{item.name || item.symbol}</strong><small>{item.name ? item.symbol : ""}{item.followed ? `${item.name ? " · " : ""}已关注` : ""}</small></div>
        <div className="anomaly-reasons">
          {item.price_triggered && item.change_pct !== null && <span className={item.change_pct >= 0 ? "up" : "down"}>
            涨跌幅 {item.change_pct > 0 ? "+" : ""}{item.change_pct.toFixed(2)}%
          </span>}
          {item.volume_triggered && item.volume_ratio !== null && <span>量比 {item.volume_ratio.toFixed(2)}</span>}
        </div>
        <button type="button" className="quiet-button" disabled={busy} onClick={() => onResearch(item.symbol, data)}
          aria-label={`研究 ${item.name || item.symbol}`}>研究</button>
      </div>)}
    {visible < filtered.length && <button type="button" className="text-button" onClick={() => setVisible(visible + 20)}>显示更多</button>}
  </div>;
}

function MarketView({ market, demo, busy, onResearchAnomaly, ...candidateProps }: {
  market: MarketWorkspace | null;
  demo: boolean;
  busy: boolean;
  onResearchAnomaly: (symbol: string, anomaly: MarketAnomalies) => void;
} & Omit<MarketCandidatesProps, "asOf" | "source" | "fixture">) {
  const snapshot = market?.snapshot_id ? market : null;
  const demoSnapshot = snapshot?.source === "fixture" || snapshot?.provider_id === "fixture";
  const asOf = demo ? REPLAY_AS_OF : !demoSnapshot && typeof snapshot?.as_of === "string"
    && (snapshot.quality === "verified" || snapshot.quality === "partial") ? snapshot.as_of : undefined;
  const source = demo ? "fixture" : typeof snapshot?.source === "string" ? snapshot.source : undefined;
  const sectors = (snapshot?.sectors as Array<{ name: string; change_pct: number; breadth: number }> | undefined) ?? [];
  const indices = (snapshot?.indices as Array<{ name: string; close: number; change_pct: number }> | undefined) ?? [];
  return <section className="control-grid">
    {market?.price_volume_anomalies && <div id="market-anomalies" className="wide" tabIndex={-1}>
      <Panel title="市场异动" eyebrow={market.price_volume_anomalies.as_of}>
        <MarketAnomalyList key={market.price_volume_anomalies.snapshot_id} data={market.price_volume_anomalies}
          busy={busy} market onResearch={onResearchAnomaly} />
      </Panel>
    </div>}
    <MarketCandidates asOf={asOf} source={source} fixture={demo ? `close-${REPLAY_AS_OF}.json` : undefined} {...candidateProps} />
    {snapshot && <>
      <Panel title="市场快照" eyebrow={`截至 ${String(snapshot.as_of)}`} wide>
        <div className="snapshot-head">
          <div><strong className="big-number">{Math.round(Number(snapshot.breadth) * 100)}%</strong><span>市场宽度</span></div>
          <div><strong className="big-number">{localizedLabel(trendLabels, snapshot.index_trend)}</strong><span>指数趋势</span></div>
          <div><strong className="big-number">{rulePercent(snapshot.volatility)}</strong><span>波动率</span></div>
          <div><strong className="big-number">{snapshot.source === "fixture" ? "回放数据" : String(snapshot.source)}</strong><span>数据来源</span></div>
        </div>
      </Panel>
      <div className="wide"><MarketCharts market={snapshot} indices={indices} /></div>
      <Panel title="指数" eyebrow="收盘数据">
        <div className="data-table">{indices.map((index) => <div className="data-row" key={index.name}>
          <strong>{index.name}</strong>
          <span>{index.close.toFixed(2)}</span>
          <span className={index.change_pct >= 0 ? "up" : "down"}>{index.change_pct >= 0 ? "+" : ""}{index.change_pct.toFixed(2)}%</span>
        </div>)}</div>
      </Panel>
      <Panel title="行业强弱" eyebrow="相对表现">
        <div className="data-table">{sectors.map((sector) => <div className="data-row" key={sector.name}>
          <strong>{sector.name}</strong>
          <span>{Math.round(sector.breadth * 100)}% 宽度</span>
          <span className={sector.change_pct >= 0 ? "up" : "down"}>{sector.change_pct >= 0 ? "+" : ""}{sector.change_pct.toFixed(1)}%</span>
        </div>)}</div>
      </Panel>
    </>}
  </section>;
}

type PortfolioPositionDraft = {
  snapshotId: string | null;
  asOf: string;
  mode: "add" | "edit" | "delete";
  position?: Record<string, unknown>;
  positionIndex?: number;
};

function WorkspaceDialog({ title, pending, onClose, children, wide }: {
  title: string; pending: boolean; onClose: () => void; children: ReactNode; wide?: boolean;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    dialog?.querySelector<HTMLElement>("[data-initial-focus]")?.focus();
    return () => dialog?.close();
  }, []);

  return <dialog ref={dialogRef} className={`runtime-dialog${wide ? " workspace-dialog-wide" : ""}`} aria-labelledby="workspace-dialog-title"
    onCancel={(event) => {
      event.preventDefault();
      if (!pending) onClose();
    }}>
    <h2 id="workspace-dialog-title">{title}</h2>
    {children}
  </dialog>;
}

function DemoReview({ onClose, onPortfolio }: { onClose: () => void; onPortfolio: () => void }) {
  const position = demoPortfolio.positions[0];
  const { max_position_weight: limit } = JSON.parse(baselineRules) as { max_position_weight: number };
  return <WorkspaceDialog title="演示复盘" pending={false} onClose={onClose}>
    <section className="demo-review">
      <p>示例行情与持仓 · {demoPortfolio.as_of}</p>
      <h3>浦发银行仓位超限</h3>
      <p>实际 {rulePercent(position.weight)}，示例规则上限 {rulePercent(limit)}。</p>
      <details>
        <summary>查看示例依据</summary>
        <p>浦发银行市值 {position.market_value.toLocaleString("zh-CN")} 元，示例组合总值 {demoPortfolio.total_value.toLocaleString("zh-CN")} 元。</p>
        <p>在你的复盘里，可以对照当时的持仓与规则，并在决策日志记录实际动作。</p>
      </details>
    </section>
    <div className="runtime-dialog-actions">
      <button className="quiet-button" onClick={onClose}>关闭</button>
      <button className="primary-button" onClick={onPortfolio}>添加我的持仓</button>
    </div>
  </WorkspaceDialog>;
}

function PortfolioPositionDialog({ draft, onClose, onChanged }: {
  draft: PortfolioPositionDraft;
  onClose: () => void;
  onChanged: (snapshot?: Record<string, unknown>) => void;
}) {
  const api = useWorkspaceApi();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { position, snapshotId, asOf, mode, positionIndex } = draft;
  const [date, setDate] = useState(asOf);
  const deleting = mode === "delete";
  const title = { add: "新增持仓", edit: "编辑持仓", delete: "删除持仓" }[mode];

  return <WorkspaceDialog title={title} pending={saving} onClose={onClose}>
    <form onSubmit={async (event) => {
      event.preventDefault();
      if (saving) return;
      const fields = new FormData(event.currentTarget);
      const quantity = Number(fields.get("quantity"));
      if (!deleting && quantity <= 0) {
        setError("持有数量必须大于 0。");
        return;
      }
      setSaving(true);
      setError("");
      try {
        const target = {
          snapshot_id: snapshotId,
          as_of: date,
          symbol: String(position?.symbol ?? fields.get("symbol")),
          position_index: positionIndex,
        };
        const { portfolio } = await api.savePortfolioPosition(deleting ? { ...target, mode } : {
          ...target,
          mode,
          quantity,
          avg_cost: Number(fields.get("avg_cost")),
          market_value: Number(fields.get("market_value")),
          sector: String(fields.get("sector") ?? "").trim(),
        });
        onChanged(portfolio);
        onClose();
      } catch (error) {
        setError(friendlyError(error, deleting ? "删除失败，请重试。" : "保存失败，请检查持仓数据后重试。"));
        if (error instanceof Error && error.message.includes('"PORTFOLIO_CHANGED"')) onChanged();
      } finally {
        setSaving(false);
      }
    }}>
      {deleting && <p className="portfolio-dialog-hint">从所选日期的持仓中移除 <strong>{String(position?.symbol)}</strong>。已有研究仍可查看原持仓快照。</p>}
      <fieldset className="runtime-fields dialog-fields" disabled={saving}>
        {!deleting && <label>股票或 ETF 代码<input name="symbol" defaultValue={String(position?.symbol ?? "")} readOnly={!!position} required
          placeholder="例如 000001" pattern={position ? undefined : "[0-9]{6}(\\.([sS][hHzZ]|[bB][jJ]))?"} autoComplete="off" /></label>}
        <label>持仓日期<input name="as_of" type="date" value={date} onChange={(event) => setDate(event.target.value)}
          min={snapshotId ? asOf : undefined} max={shanghaiDate()} required /></label>
        {snapshotId && date > asOf && <small>新日期会沿用其他持仓原有的数量、成本和市值。</small>}
        {!deleting && <>
          <label>持有数量（股 / 份）<input name="quantity" type="number" min="0" step="any" required defaultValue={String(position?.quantity ?? "")} /></label>
          <label>平均成本（元 / 股或份）<input name="avg_cost" type="number" min="0" step="any" required defaultValue={String(position?.avg_cost ?? "")} /></label>
          <label>持仓总市值（元）<input name="market_value" type="number" min="0" step="any" required defaultValue={String(position?.market_value ?? "")} /></label>
          <label>所属行业（股票）<input name="sector" maxLength={80} defaultValue={position?.sector === "unknown" ? "" : String(position?.sector ?? "")} /></label>
        </>}
      </fieldset>
      {error && <p className="auth-error" role="alert">{error}</p>}
      <div className="runtime-dialog-actions">
        <button type="button" className="quiet-button" data-initial-focus={deleting || undefined} disabled={saving} onClick={onClose}>取消</button>
        <button className={deleting ? "danger-button" : "primary-button"} disabled={saving}>
          {deleting ? (saving ? "正在删除…" : "确认删除") : (saving ? "正在保存…" : "保存持仓")}
        </button>
      </div>
    </form>
  </WorkspaceDialog>;
}

function PortfolioImportDialog({ defaultDate, onClose, onImported }: {
  defaultDate: string;
  onClose: () => void;
  onImported: (snapshot: Record<string, unknown>, asOf: string) => void;
}) {
  const api = useWorkspaceApi();
  const [source, setSource] = useState<"file" | "paste">("file");
  const [pasteFormat, setPasteFormat] = useState<"csv" | "manual">("csv");
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");

  return <WorkspaceDialog title="批量导入持仓" pending={importing} onClose={onClose} wide>
    <p className="portfolio-dialog-hint">导入会为所选日期保存一份完整快照，请包含该日期的全部持仓。</p>
    <form onSubmit={async (event) => {
      event.preventDefault();
      if (importing) return;
      const fields = new FormData(event.currentTarget);
      const asOf = String(fields.get("as_of"));
      setImporting(true);
      setError("");
      try {
        let format: "csv" | "xlsx" | "manual" = pasteFormat;
        let content: string | { encoding: "base64"; data: string };
        if (source === "file") {
          const file = fields.get("file");
          if (!(file instanceof File) || !file.size) {
            setError("请选择有内容的持仓文件。");
            return;
          }
          const extension = file.name.toLowerCase().split(".").pop();
          if (extension === "xlsx") {
            const bytes = new Uint8Array(await file.arrayBuffer());
            let binary = "";
            const chunkSize = 0x8000;
            for (let index = 0; index < bytes.length; index += chunkSize) {
              binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
            }
            format = "xlsx";
            content = { encoding: "base64", data: btoa(binary) };
          } else if (extension === "csv") {
            format = "csv";
            content = await file.text();
          } else {
            setError("请选择 CSV 或 Excel（.xlsx）文件。");
            return;
          }
        } else {
          content = String(fields.get("content")).trim();
          if (!content) {
            setError("请粘贴持仓数据。");
            return;
          }
        }
        const { portfolio } = await api.importPortfolio(format, content, asOf);
        onImported(portfolio, asOf);
      } catch (error) {
        setError(friendlyError(error, "导入失败，请检查文件格式、持仓数据和日期。"));
      } finally {
        setImporting(false);
      }
    }}>
      <fieldset className="runtime-fields dialog-fields" disabled={importing}>
        <label>持仓日期<input name="as_of" type="date" defaultValue={defaultDate} max={shanghaiDate()} required /></label>
        <div className="portfolio-import-sources" role="group" aria-label="导入方式">
          <button type="button" aria-pressed={source === "file"} onClick={() => { setSource("file"); setError(""); }}>上传文件</button>
          <button type="button" aria-pressed={source === "paste"} onClick={() => { setSource("paste"); setError(""); }}>粘贴数据</button>
        </div>
        {source === "file" ? <label>持仓文件（CSV 或 Excel）
          <input name="file" type="file" accept=".csv,.xlsx" required />
        </label> : <>
          <label>数据格式<select value={pasteFormat} onChange={(event) => setPasteFormat(event.target.value as "csv" | "manual")}>
            <option value="csv">CSV</option>
            <option value="manual">JSON</option>
          </select></label>
          <label>持仓数据<textarea name="content" className="portfolio-import-content" required
            placeholder={pasteFormat === "csv" ? "symbol,quantity,avg_cost,market_value,sector" : undefined} /></label>
        </>}
      </fieldset>
      {error && <p className="auth-error" role="alert">{error}</p>}
      <div className="runtime-dialog-actions">
        <button type="button" className="quiet-button" disabled={importing} onClick={onClose}>取消</button>
        <button className="primary-button" disabled={importing}>{importing ? "正在导入…" : "导入持仓"}</button>
      </div>
    </form>
  </WorkspaceDialog>;
}

function PortfolioView({ portfolio, demoDate, onChanged }: {
  portfolio: Record<string, unknown> | null;
  demoDate?: string;
  onChanged: (snapshot?: Record<string, unknown>) => void;
}) {
  const addButtonRef = useRef<HTMLButtonElement>(null);
  const [editor, setEditor] = useState<PortfolioPositionDraft | "import" | null>(null);
  const [status, setStatus] = useState("");
  const snapshotId = portfolio?.source !== "fixture" && typeof portfolio?.snapshot_id === "string" ? portfolio.snapshot_id : null;
  const snapshot = snapshotId ? portfolio : null;
  const positions = (snapshot?.positions as Array<Record<string, unknown>> | undefined) ?? [];
  const asOf = snapshot ? String(snapshot.as_of) : demoDate ?? shanghaiDate();
  const totalValue = typeof snapshot?.total_value === "number" ? snapshot.total_value.toLocaleString() : "—";
  const drawdown = typeof snapshot?.drawdown === "number" ? rulePercent(snapshot.drawdown) : "—";
  const openEditor = (mode: PortfolioPositionDraft["mode"], position?: Record<string, unknown>, positionIndex?: number) => {
    setStatus("");
    setEditor({ snapshotId, asOf, mode, position, positionIndex });
  };
  const closeEditor = () => setEditor(null);

  return <section className="control-grid portfolio-grid">
    <Panel title="我的持仓" eyebrow={snapshot ? asOf : "暂无快照"} wide actions={
      <div className="workspace-actions">
        <button type="button" className="quiet-button" onClick={() => { setStatus(""); setEditor("import"); }}>批量导入</button>
        <button ref={addButtonRef} type="button" className="primary-button" disabled={!portfolio} onClick={() => openEditor("add")}>
          <PlusIcon size={16} aria-hidden="true" />新增持仓
        </button>
      </div>
    }>
      {snapshot && <div className="snapshot-head compact">
        <div><strong className="big-number">{totalValue}</strong><span>总市值</span></div>
        <div><strong className="big-number">{drawdown}</strong><span>回撤</span></div>
      </div>}
      {positions.length > 0 ? <table className="portfolio-positions" aria-label="持仓列表">
        <thead><tr>
          <th scope="col">标的</th>
          <th scope="col">数量</th>
          <th scope="col" className="portfolio-position-detail">平均成本</th>
          <th scope="col" className="portfolio-position-detail">市值</th>
          <th scope="col" className="portfolio-position-weight">仓位</th>
          <th scope="col">操作</th>
        </tr></thead>
        <tbody>{positions.map((position, index) => {
          const symbol = String(position.symbol);
          const sector = typeof position.sector === "string" && position.sector !== "unknown" ? position.sector : "";
          return <tr key={`${symbol}-${index}`}>
            <th scope="row"><strong>{symbol}</strong>{sector && <small>{sector}</small>}</th>
            <td>{Number(position.quantity).toLocaleString()} {position.asset_type === "etf" ? "份" : "股"}</td>
            <td className="portfolio-position-detail">{Number(position.avg_cost).toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
            <td className="portfolio-position-detail">{Number(position.market_value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
            <td className="portfolio-position-weight">{(Number(position.weight) * 100).toFixed(1)}%</td>
            <td><div className="portfolio-row-actions">
              <button className="text-button" type="button" aria-label={`编辑持仓 ${symbol}`} onClick={() => openEditor("edit", position, index)}>编辑</button>
              <button className="text-button portfolio-delete" type="button" aria-label={`删除持仓 ${symbol}`} onClick={() => openEditor("delete", position, index)}>删除</button>
            </div></td>
          </tr>;
        })}</tbody>
      </table> : <p className="form-hint">{portfolio ? "暂无持仓。可以逐条新增，或导入持仓文件。" : "正在读取持仓快照。"}</p>}
      <p className={status ? "form-hint portfolio-position-status" : undefined} role="status">{status}</p>
    </Panel>
    {positions.length > 0 && <div className="portfolio-charts wide"><PortfolioCharts portfolio={snapshot} positions={positions} /></div>}
    {editor === "import" && <PortfolioImportDialog defaultDate={demoDate ?? shanghaiDate()} onClose={closeEditor} onImported={(imported, intendedDate) => {
      const importedDate = String(imported.as_of ?? "未知");
      setStatus(importedDate === intendedDate
        ? `已导入 ${importedDate} 的持仓快照。`
        : `持仓快照已导入，服务返回的日期为 ${importedDate}，请核对。`);
      closeEditor();
      onChanged(!snapshot || importedDate >= asOf ? imported : undefined);
    }} />}
    {editor && editor !== "import" && <PortfolioPositionDialog draft={editor} onClose={closeEditor} onChanged={(saved) => {
      if (saved) {
        setStatus({ add: "持仓已添加。", edit: "持仓已更新。", delete: "持仓已删除。" }[editor.mode]);
        if (editor.mode === "delete") requestAnimationFrame(() => addButtonRef.current?.focus());
      }
      onChanged(saved);
    }} />}
  </section>;
}

function ProfileView({ profile, load, onReload, onCredentialsSaved, localCredentials = false }: {
  profile: Record<string, unknown> | null;
  load?: ResourceStatus;
  onReload: () => void;
  onCredentialsSaved: () => void;
  localCredentials?: boolean;
}) {
  const api = useWorkspaceApi();
  const savedObjective = String((profile?.payload as Record<string, unknown> | undefined)?.investment_objective ?? DEFAULT_INVESTMENT_OBJECTIVE);
  const displayedObjective = displayInvestmentObjective(savedObjective);
  const [objective, setObjective] = useState(displayedObjective);
  const [riskTolerance, setRiskTolerance] = useState("moderate");
  const [drawdownLimit, setDrawdownLimit] = useState("0.15");
  const [assetTypes, setAssetTypes] = useState<string[]>(["stock", "etf"]);
  const [universe, setUniverse] = useState<string[]>(["main", "chinext", "star", "bse", "etf"]);
  const [status, setStatus] = useState("");
  useEffect(() => {
    const payload = (profile?.payload ?? {}) as Record<string, unknown>;
    setObjective(displayedObjective);
    setRiskTolerance(String(payload.risk_tolerance ?? "moderate"));
    setDrawdownLimit(String(payload.drawdown_limit ?? "0.15"));
    setAssetTypes(Array.isArray(payload.allowed_asset_types) ? payload.allowed_asset_types.map(String) : ["stock", "etf"]);
    setUniverse(Array.isArray(payload.universe) ? payload.universe.map(String) : ["main", "chinext", "star", "bse", "etf"]);
  }, [profile, displayedObjective]);
  const toggleValue = (values: string[], value: string) =>
    values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
  const save = async () => {
    try {
      const parsedDrawdown = Number(drawdownLimit);
      if (!Number.isFinite(parsedDrawdown) || parsedDrawdown <= 0 || parsedDrawdown > 1) {
        setStatus("最大回撤请输入 0 到 1 之间的小数，例如 0.15");
        return;
      }
      await api.updateProfile({
        ...(profile?.payload as Record<string, unknown> | undefined),
        investment_objective: objective === displayedObjective ? savedObjective : objective,
        risk_tolerance: riskTolerance,
        drawdown_limit: parsedDrawdown,
        allowed_asset_types: assetTypes,
        universe,
      });
      setStatus("投资设置已保存");
      onReload();
    } catch (error) {
      setStatus(friendlyError(error, "保存失败，请检查设置"));
    }
  };
  return <section className="control-grid">
    <Panel title="投资设置" eyebrow={`版本 ${String(profile?.version ?? "—")}`}>
      <fieldset className="profile-form" disabled={!load || Boolean(load.error)}>
        <label><span>你希望 Pia 如何帮助你</span><textarea value={objective} onChange={(event) => setObjective(event.target.value)} placeholder={`例如：${DEFAULT_INVESTMENT_OBJECTIVE_LABEL}`} /></label>
        <label><span>风险偏好</span><select value={riskTolerance} onChange={(event) => setRiskTolerance(event.target.value)}><option value="conservative">保守</option><option value="moderate">稳健</option><option value="aggressive">积极</option></select></label>
        <label><span>你能接受的最大回撤</span><div className="input-with-suffix"><input value={drawdownLimit} onChange={(event) => setDrawdownLimit(event.target.value)} inputMode="decimal" /><em>小数，例如 0.15 = 15%</em></div></label>
        <fieldset><legend>允许研究的资产</legend><div className="choice-grid">{[["stock", "股票"], ["etf", "ETF"]].map(([value, label]) => <button type="button" aria-pressed={assetTypes.includes(value)} className={`choice-chip ${assetTypes.includes(value) ? "selected" : ""}`} key={value} onClick={() => setAssetTypes(toggleValue(assetTypes, value))}><span><CheckIcon size={16} aria-hidden="true" /></span>{label}</button>)}</div></fieldset>
        <fieldset><legend>股票范围</legend><div className="choice-grid">{[["main", "沪深主板"], ["chinext", "创业板"], ["star", "科创板"], ["bse", "北交所"], ["etf", "ETF"]].map(([value, label]) => <button type="button" aria-pressed={universe.includes(value)} className={`choice-chip ${universe.includes(value) ? "selected" : ""}`} key={value} onClick={() => setUniverse(toggleValue(universe, value))}><span><CheckIcon size={16} aria-hidden="true" /></span>{label}</button>)}</div></fieldset>
      </fieldset>
      <div className="form-row">
        <button className="primary-button" disabled={!load || Boolean(load.error)} onClick={() => void save()}>保存设置</button>
        {load?.error
          ? <button className="quiet-button" onClick={onReload}>重试读取投资设置</button>
          : <span className="form-hint">{status || (load ? "设置会保存为新版本，只影响之后的研究。" : "正在读取投资设置…")}</span>}
      </div>
    </Panel>
    {localCredentials && <>
      <CredentialSettings kind="tushare" onSaved={onCredentialsSaved} />
      <CredentialSettings kind="deepseek" onSaved={onCredentialsSaved} />
    </>}
    <Panel title="研究上下文" eyebrow="当前快照">
      <div className="rationale"><span>✓</span><p>你的风险偏好、目标、资产范围和股票范围会参与每次研究的风险审核。</p></div>
      <div className="rationale"><span>✓</span><p>Pia 只给研究建议，不会替你提交真实订单。</p></div>
    </Panel>
  </section>;
}

const localCredentialSettings = {
  deepseek: {
    title: "DeepSeek", subtitle: "本地模型凭据", id: "deepseek-api-key", label: "API 密钥", secretName: "API 密钥",
    environment: "DEEPSEEK_API_KEY", placeholder: "sk-...", read: "deepseekCredential",
    save: "saveDeepseekCredential", clear: "clearDeepseekCredential",
  },
  tushare: {
    title: "Tushare", subtitle: "本地行情数据", id: "tushare-token", label: "访问令牌", secretName: "访问令牌",
    environment: "TUSHARE_TOKEN", placeholder: "输入 Tushare Token", read: "tushareCredential",
    save: "saveTushareCredential", clear: "clearTushareCredential",
  },
} as const;

function CredentialSettings({ kind, onSaved }: { kind: keyof typeof localCredentialSettings; onSaved: () => void }) {
  const api = useWorkspaceApi();
  const settings = localCredentialSettings[kind];
  const [credential, setCredential] = useState<LocalCredentialStatus | null>(null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setPending(true);
    setError("");
    api[settings.read]().then((value) => {
      if (!cancelled) setCredential(value);
    }).catch(() => {
      if (!cancelled) setError("无法读取凭据状态，请重试。");
    }).finally(() => {
      if (!cancelled) setPending(false);
    });
    return () => { cancelled = true; };
  }, [api, reload, settings]);

  const update = async (clear: boolean) => {
    setPending(true);
    setError("");
    setMessage("");
    try {
      const next = await (clear ? api[settings.clear]() : api[settings.save](draft.trim()));
      setCredential(next);
      setDraft("");
      setMessage(clear ? `已清除保存的 ${settings.secretName}。` : `${settings.secretName} 已保存，后续请求立即生效。`);
      onSaved();
    } catch {
      setError(clear ? "清除失败，请检查系统凭据存储后重试。" : `保存失败，请检查 ${settings.secretName} 和系统凭据存储后重试。`);
    } finally {
      setPending(false);
    }
  };
  const source = credential?.source === "saved" ? "已保存的凭据"
    : credential?.source === "environment" ? `环境变量 ${settings.environment}`
    : credential ? "未配置" : "正在读取";

  return <Panel title={settings.title} eyebrow={settings.subtitle}>
    <form onSubmit={(event) => { event.preventDefault(); if (!pending && draft.trim()) void update(false); }}>
      <div className="profile-form">
        <label htmlFor={settings.id}><span>{settings.label}</span>
          <input id={settings.id} type="password" value={draft} disabled={pending || !credential} autoComplete="off" spellCheck={false} maxLength={1024}
            placeholder={credential?.source === "saved" ? `已保存，输入新 ${settings.secretName} 可替换` : settings.placeholder}
            onChange={(event) => { setDraft(event.target.value); setMessage(""); setError(""); }} />
        </label>
        <p className="form-hint">当前来源：{source}</p>
        {kind === "tushare" && <p className="form-hint">同步真实行情时，A 股股票日线优先使用 Tushare 免费接口。指数、交易日历和 ETF 仍由 AKShare 提供。</p>}
      </div>
      <div className="form-row">
        <button className="primary-button" disabled={pending || !credential || !draft.trim()}><FloppyDiskIcon size={16} aria-hidden="true" />保存 {settings.secretName}</button>
        <button type="button" className="quiet-button" disabled={pending || credential?.source !== "saved"} onClick={() => void update(true)}><TrashIcon size={16} aria-hidden="true" />清除 {settings.secretName}</button>
        {error ? <button type="button" className="icon-button" title="重新读取凭据状态" aria-label="重新读取凭据状态" disabled={pending} onClick={() => setReload((value) => value + 1)}><ArrowClockwiseIcon size={16} aria-hidden="true" /></button> : null}
      </div>
      {error ? <p className="credential-message auth-error" role="alert">{error}</p>
        : <p className="credential-message form-hint" role="status">{pending ? "正在处理…" : message || (credential?.configured ? "凭据已配置" : `尚未配置 ${settings.secretName}`)}</p>}
    </form>
  </Panel>;
}

function RulesView({ rules, evaluation, onSaved }: { rules: Record<string, unknown> | null; evaluation?: RuleResult | null; onSaved: () => void }) {
  const api = useWorkspaceApi();
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");
  const [positionLimit, setPositionLimit] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setDraft(JSON.stringify(rules, null, 2));
    setPositionLimit(typeof rules?.max_position_weight === "number" ? String(Math.round(rules.max_position_weight * 10000) / 100) : "");
  }, [rules]);
  const save = async (definition: Record<string, unknown>) => {
    setSaving(true);
    try {
      await api.updateRules(definition);
      setStatus("规则版本已保存");
      onSaved();
    } catch (error) {
      setStatus(friendlyError(error, "无法保存规则版本"));
    } finally {
      setSaving(false);
    }
  };
  if (!rules) return <section className="single-panel panel"><EmptyState message="规则快照不可用" /></section>;
  const weight = Number(positionLimit);
  const validLimit = positionLimit !== "" && Number.isFinite(weight) && weight >= 0 && weight <= 100;
  const marketGate = rules.market_gate as Record<string, unknown> | undefined;
  const thresholds = [
    ["单只股票仓位上限", rulePercent(rules.max_position_weight)],
    ["单只 ETF 仓位上限", rulePercent(rules.max_etf_weight)],
    ["行业仓位上限", rulePercent(rules.max_sector_weight)],
    ["回撤预警", rulePercent(rules.drawdown_warning)],
    ["回撤限制", rulePercent(rules.drawdown_limit)],
    ["严重回撤阈值", rulePercent(rules.critical_drawdown)],
    ["市场宽度下限", rulePercent(marketGate?.breadth_min)],
    ["波动率上限", rulePercent(marketGate?.volatility_max)],
  ];
  return <section className="control-grid">
    <Panel title={`规则集 ${String(rules.version)}`} eyebrow="当前配置">
      <dl className="rule-config-grid">{thresholds.map(([label, value]) => <div className="config-item" key={label}>
        <dt>{label}</dt><dd>{value}</dd>
      </div>)}</dl>
      <form className="form-row" onSubmit={(event) => {
        event.preventDefault();
        if (validLimit && !saving) void save({ ...rules, version: `position-${Date.now()}`, max_position_weight: weight / 100 });
      }}>
        <label htmlFor="position-limit">单只股票仓位上限（%）</label>
        <input id="position-limit" type="number" min="0" max="100" step="0.01" required value={positionLimit} onChange={(event) => setPositionLimit(event.target.value)} />
        <button className="primary-button" type="submit" disabled={!validLimit || saving || weight / 100 === rules.max_position_weight}>保存新版本</button>
        <span className="form-hint" role="status">{status || "新版本应用于之后创建的研究。"}</span>
      </form>
      <details className="technical-disclosure">
        <summary>查看和编辑完整规则（JSON）</summary>
        <textarea aria-label="规则 JSON" className="import-area" value={draft} onChange={(event) => setDraft(event.target.value)} />
        <div className="form-row">
          <button className="primary-button" disabled={saving} onClick={() => {
            try {
              void save(JSON.parse(draft) as Record<string, unknown>);
            } catch {
              setStatus("规则必须是有效 JSON");
            }
          }}>保存 JSON 版本</button>
        </div>
      </details>
    </Panel>
    <Panel title="当前研究的规则检查" eyebrow={evaluation?.rule_snapshot_id ?? "研究快照"}>
      {evaluation ? <RuleList rules={evaluation} /> : <EmptyState message="选择一条研究，查看当时执行的规则。" />}
    </Panel>
  </section>;
}

const syncLabels: Record<string, string> = {
  market_snapshot: "市场快照", trading_calendar: "交易日历", universe: "标的列表",
  daily_bars: "个股日线", fundamentals: "基本面", research_sources: "资讯与公告",
  news: "资讯", filing: "公告", filings: "公告", request: "复盘日期", finalizing: "整理同步结果",
};

const syncFailureReasons: Record<string, string> = {
  Push2RateLimitError: "东财接口限流，请稍后重试。",
  CapabilityUnavailable: "当前没有可用数据源，请检查数据源连接。",
  ConnectionError: "数据源连接失败，请检查网络连接。",
  STAGE_TIMEOUT: "等待数据源响应超时，请稍后重试。",
  StageTimeout: "等待数据源响应超时，请稍后重试。",
  TimeoutError: "等待数据源响应超时，请稍后重试。",
  UNIVERSE_COVERAGE_MISSING: "标的列表缺少部分市场。",
  POINT_IN_TIME_UNAVAILABLE: "数据源未提供该复盘日的市场快照。",
  FIELD_MISSING: "数据源返回的快照缺少必需字段。",
  AS_OF_IN_FUTURE: "复盘日期晚于当前日期。",
  TEMPORAL_METADATA_INVALID: "数据日期或采集时间未通过校验。",
  DATA_QUALITY_INCOMPLETE: "数据源未返回通过校验的数据。",
};

function syncIssue(failure: Record<string, unknown>) {
  const source = scanSourceLabels[failure.provider_id as keyof typeof scanSourceLabels];
  const code = typeof failure.code === "string" ? failure.code : "";
  const temporalReason = typeof failure.reason === "string" ? syncFailureReasons[failure.reason] : undefined;
  const reason = temporalReason ?? syncFailureReasons[code] ?? (code && code !== "RuntimeError"
    ? `数据源返回异常（${code}）。` : "数据源未返回可用数据。");
  return [failure.symbol, source, reason].filter(Boolean).join(" · ");
}

const syncStepLabels = {
  running: "同步中", validating: "校验中", done: "已完成", reused: "已复用",
  partial: "部分完成", failed: "失败", skipped: "已跳过",
};

function MarketSyncSteps({ steps, failures, running, canRetry, onSync }: {
  steps: Record<string, MarketSyncProgress>;
  failures: Array<Record<string, unknown>>;
  running: boolean;
  canRetry: boolean;
  onSync: (stage: MarketSyncStage) => Promise<void>;
}) {
  return <ol className="market-sync-steps" aria-label="行情同步步骤">
    {marketSyncStages.map((stage) => {
      const step = steps[stage];
      const status = step?.status;
      const inProgress = status === "running" || status === "validating" || Boolean(step && !status);
      const label = inProgress && !running ? "进度中断" : status ? syncStepLabels[status] : "等待";
      const fetched = step?.fetched ?? 0;
      const reused = step?.reused ?? 0;
      const failed = step?.failed ?? 0;
      const done = fetched + reused + failed;
      const detail = status === "skipped" ? (step?.reason === "no_symbols" ? "无持仓或自选标的"
        : step?.reason === "outside_scope" ? "本次未选择此项" : "数据源未提供此项")
        : status === "validating" ? "正在核对交易日和标的覆盖"
        : status === "reused" && (step?.total ?? 0) <= 1 ? "使用本地已验证的数据"
        : stage === "market_snapshot" && status === "done" ? "行情已保存"
        : step?.total && step.total > 1 ? `已处理 ${done}/${step.total} · 新拉取 ${fetched} · 复用 ${reused} · 失败 ${failed}`
        : step?.saved_rows ? `已保存 ${step.saved_rows.toLocaleString("zh-CN")} 条`
        : inProgress ? (step?.symbol ? `正在处理 ${step.symbol}` : "等待数据源响应")
        : status === "done" ? "查询完成，无新增记录" : "";
      const issues = Array.from(new Set(failures
        .filter((failure) => failure.kind === stage || stage === "filing" && failure.kind === "filings")
        .map(syncIssue)));
      return <li key={stage}>
        <div className="market-sync-step">
          <span className="market-sync-state" data-status={status}>{label}</span>
          <div>
            <strong>{syncLabels[stage]}</strong>
            {detail && <small>{detail}{inProgress && running && step?.symbol && (step.total ?? 0) > 1 && ` · 正在处理 ${step.symbol}`}</small>}
            {step?.total && step.total > 1 && status !== "skipped" && <progress
              className="market-sync-progress" value={done} max={step.total}
              aria-label={`${syncLabels[stage]}处理进度`} aria-valuetext={`已处理 ${done}/${step.total} 个标的`} />}
          </div>
          {canRetry && status && !inProgress && (status !== "skipped" || step.reason === "outside_scope") && <button type="button" className="text-button"
            title="重新拉取此项"
            aria-label={`重新拉取${syncLabels[stage]}`} onClick={() => void onSync(stage)}>重拉</button>}
        </div>
        {issues.length > 0 && <details className="market-sync-issues">
          <summary>{issues.length} 个问题</summary>
          <ul>{issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
        </details>}
      </li>;
    })}
  </ol>;
}

function DataHealthView({
  health, market, session, marketLabel, syncResult, marketSync, syncError, syncSteps, onSync, onSchedulerChange, onOpenSettings, onOpenAnomalies,
}: {
  health: WorkspaceHealth | null;
  market: MarketWorkspace | null;
  session: ReturnType<typeof reviewSession>;
  marketLabel: string;
  syncResult: Record<string, unknown> | null;
  marketSync: ActiveMarketSync | null;
  syncError: string;
  syncSteps: Record<string, MarketSyncProgress>;
  onSync: (stage?: MarketSyncStage) => Promise<void>;
  onSchedulerChange: (value: SchedulerResponse) => void;
  onOpenSettings: () => void;
  onOpenAnomalies: () => void;
}) {
  const api = useWorkspaceApi();
  const [schedulerPending, setSchedulerPending] = useState(false);
  const [status, setStatus] = useState("");
  const [now, setNow] = useState(Date.now);
  const startedAt = marketSync?.startedAt;
  useEffect(() => {
    if (startedAt === undefined) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  const elapsed = startedAt === undefined ? 0 : Math.max(0, Math.floor((now - startedAt) / 1000));
  const demo = health?.provider.provider_id === "fixture";
  const lastVerified = market?.last_verified ?? (market?.as_of && market.as_of <= session.as_of
    && market.quality === "verified" && (demo || !isDemoMarket(market)) ? market : null);
  const failures = Array.isArray(syncResult?.failures) ? syncResult.failures as Array<Record<string, unknown>> : [];
  const storedSteps = Array.isArray(syncResult?.stages) ? syncResult.stages as MarketSyncProgress[] : [];
  const steps = storedSteps.length ? Object.fromEntries(storedSteps.map((step) => [step.stage, step])) : syncSteps;
  const hasSteps = Boolean(storedSteps.length || Object.values(syncSteps).some((step) =>
    step.stage !== "finalizing" && step.status,
  ) || marketSync && !Object.keys(syncSteps).length);
  const legacyProgress = marketSync && !hasSteps ? Object.values(syncSteps).at(-1) : undefined;
  const finished = marketSyncStages.filter((stage) => {
    const status = steps[stage]?.status;
    return status && status !== "running" && status !== "validating";
  }).length;
  const issues = failures.filter((failure) => !hasSteps || !Object.hasOwn(steps, String(failure.kind)));
  const saved = Object.entries((syncResult?.counts ?? {}) as Record<string, number>)
    .filter(([kind, count]) => syncLabels[kind] && count > 0)
    .map(([kind, count]) => `${syncLabels[kind]} ${count.toLocaleString("zh-CN")} 条`);
  const toggleScheduler = async () => {
    setSchedulerPending(true);
    setStatus("");
    try {
      const result = await (health?.scheduler?.enabled ? api.stopScheduler() : api.startScheduler());
      onSchedulerChange(result);
      setStatus(result.enabled ? "已开启收盘调度。" : "已停止收盘调度。");
    } catch (error) {
      setStatus(friendlyError(error, "调度状态更新失败"));
    } finally {
      setSchedulerPending(false);
    }
  };
  return <section className="control-grid">
    <Panel title="复盘行情" wide>
      <div className="health-list">
        <div><span>{demo ? "演示日期" : "拟复盘日"}</span><strong>{session.as_of}{!session.calendar_verified && " · 待日历确认"}</strong></div>
        <div><span>当前状态</span><strong>{marketLabel}</strong></div>
        <div><span>最近可用行情</span><strong>{lastVerified?.as_of ? [lastVerified.as_of, localizedLabel(scanSourceLabels, lastVerified.source, "来源未知")].join(" · ") : "暂无快照"}</strong></div>
        {lastVerified?.observed_at && <div><span>数据时间</span><strong>{formatDate(lastVerified.observed_at)}</strong></div>}
        {syncResult && <div><span>最近一次同步</span><strong>{String(syncResult.as_of ?? session.as_of)} · {syncResult.quality === "partial" ? "部分完成" : syncResult.quality === "verified" ? "已完成" : localizedLabel(qualityLabels, syncResult.quality, "未知")}</strong></div>}
        {market?.price_volume_anomalies?.as_of === (syncResult?.as_of ?? session.as_of) && <div>
          <span>市场异动</span><button type="button" className="text-button" onClick={onOpenAnomalies}>
            查看 {market.price_volume_anomalies.items.length} 个异动标的
          </button>
        </div>}
      </div>
      {(marketSync || hasSteps) && <div className="form-hint">
        <strong role="status">{marketSync && `${marketSync.asOf} · `}{legacyProgress
          ? `${syncLabels[legacyProgress.stage] ?? "同步中"}${legacyProgress.symbol ? ` · ${legacyProgress.symbol}` : ""}`
          : `${finished}/${marketSyncStages.length} 项已结束`}
          {marketSync && syncSteps.finalizing && " · 正在整理结果"}</strong>
        {hasSteps && <progress className="market-sync-progress" value={finished} max={marketSyncStages.length}
          aria-label="行情同步总进度" aria-valuetext={`${finished}/${marketSyncStages.length} 项已结束`} />}
        {marketSync && <div>已用时 {Math.floor(elapsed / 60)} 分 {elapsed % 60} 秒</div>}
      </div>}
      {hasSteps && <MarketSyncSteps steps={steps} failures={failures} running={Boolean(marketSync)}
        canRetry={!marketSync && !schedulerPending && syncResult?.as_of === session.as_of} onSync={onSync} />}
      {syncError && <p className="sync-failures" role="alert">{syncError}</p>}
      {syncResult && <p className="form-hint" role="status">
        {syncResult.market_snapshot_quality === "verified" ? "复盘行情已就绪。"
          : steps.market_snapshot?.status === "skipped" ? "本次未更新市场快照。" : "本次市场快照未通过校验。"}
        {saved.length > 0 && ` 本次新保存 ${saved.join("、")}。`}
      </p>}
      {issues.length > 0 && <div className="sync-failures">
          <strong>同步遇到的问题</strong>
          <ul>{Array.from(new Set(issues.map((issue) =>
            `${syncLabels[String(issue.kind)] ?? "部分数据"} · ${syncIssue(issue)}`,
          ))).map((issue) => <li key={issue}>{issue}</li>)}</ul>
      </div>}
      <div className="form-row">
        <button className="primary-button" disabled={Boolean(marketSync) || schedulerPending} onClick={() => void onSync()}>
          {marketSync ? "正在同步…" : syncResult?.as_of === session.as_of ? "补齐缺失数据" : "同步市场数据"}
        </button>
        <button className="quiet-button" onClick={onOpenSettings}>数据源设置</button>
      </div>
    </Panel>
    <Panel title="收盘调度">
      <div className="health-list">
        <div><span>状态</span><strong>{health?.scheduler?.enabled ? "运行中" : "已停止"}</strong></div>
        <div><span>运行时间</span><strong>{health?.scheduler?.close_time ?? "15:05"} · {health?.scheduler?.timezone ?? "Asia/Shanghai"}</strong></div>
        <div><span>上次触发</span><strong>{health?.scheduler?.last_dispatched_date ?? "尚未运行"}</strong></div>
      </div>
      <div className="form-row">
        <button className="quiet-button" disabled={Boolean(marketSync) || schedulerPending} onClick={() => void toggleScheduler()}>{health?.scheduler?.enabled ? "停止调度" : "开启调度"}</button>
      </div>
    </Panel>
    <Panel title="连接">
      <div className="health-list">
        <div><span>运行时</span><strong>{localizedLabel(healthLabels, health?.status, "未知")}</strong></div>
        <div><span>数据源连接</span><strong>{localizedLabel(scanSourceLabels, health?.provider.provider_id, "未知")} · {localizedLabel(healthLabels, health?.provider.status, "未知")}</strong></div>
        <div><span>模型凭据</span><strong>{health?.llm.credentials_configured ? health.llm.model : "未配置"}</strong></div>
      </div>
    </Panel>
    {status && <p className="form-hint wide" role="status">{status}</p>}
  </section>;
}

const auditEventLabels: Record<string, string> = {
  TASK_QUEUED: "任务进入队列",
  TASK_STATUS: "任务状态更新",
  STAGE_STARTED: "阶段开始",
  STAGE_COMPLETED: "阶段完成",
  STAGE_TIMEOUT: "阶段超时",
  PROVIDER_ATTEMPT: "请求数据源",
  PROVIDER_FALLBACK: "切换备用数据源",
  DATA_SNAPSHOT_READY: "数据快照就绪",
  EVIDENCE_SAVED: "保存证据",
  RULES_EVALUATED: "完成规则检查",
  AGENT_STARTED: "开始分析",
  AGENT_COMPLETED: "分析完成",
  DECISION_SYNTHESIZED: "生成研究结论",
  HUMAN_APPROVAL_REQUESTED: "等待人工审批",
  APPROVAL_RECORDED: "保存审批记录",
  RETROSPECTIVE_RECORDED: "保存复盘记录",
};

function AuditView({ detail }: { detail: TaskDetail | null }) {
  if (!detail) return <section className="single-panel panel"><EmptyState message="选择任务查看不可变审计轨迹。" /></section>;
  return <section className="single-panel panel" key={detail.task.id}>
    <div className="panel-header">
      <div><span className="eyebrow">审计 · {detail.events.length} 条事件</span><h2>{detail.task.id}</h2></div>
      <StatusBadge status={detail.task.status} />
    </div>
    <div className="audit-list">{detail.events.map((event, index) => <details className="audit-row" key={`${event.created_at}-${index}`}>
      <summary>
        <time dateTime={event.created_at}>{formatDate(event.created_at)}</time>
        <strong>{localizedLabel(auditEventLabels, event.event_type)}</strong>
        {typeof event.payload.status === "string" && <span>{statusLabel(event.payload.status)}</span>}
      </summary>
      <div className="audit-payload"><code>{event.event_type}</code><pre>{JSON.stringify(event.payload, null, 2)}</pre></div>
    </details>)}</div>
  </section>;
}

function ResearchDetail({ detail, busy, rawData, onApprove, onControl, onCancel, onRetry, onTakeover, onExport, onReplay, onRawData, onCopyLink, onCopyEvidenceLink, onRetrospective, onOpenJournal, onOpenPortfolio, onHoldingsConfirmed, onHoldingsRetry }: { detail: TaskDetail; busy: boolean; rawData: TaskDataResponse | null; onApprove: (action: "APPROVE" | "REJECT" | "NO_ACTION" | "REQUEST_MORE_RESEARCH" | "MARK_AS_WATCH") => void; onControl: (action: "pause" | "resume") => void; onCancel: () => void; onRetry: () => void; onTakeover: () => void; onExport: () => void; onReplay: () => void; onRawData: () => void; onCopyLink: () => void; onCopyEvidenceLink: (evidenceId: string) => void; onRetrospective: (payload: RetrospectiveInput) => Promise<void>; onOpenJournal: () => void; onOpenPortfolio: () => void; onHoldingsConfirmed: () => Promise<void>; onHoldingsRetry: () => void }) {
  const holdingsReview = detail.holdings_review;
  const decision = detail.decision;
  const rules = decision?.rationale.rules;
  const ruleReasons = [...(rules?.reasons ?? []), ...(rules?.warnings ?? [])];
  const rationaleItems = decision?.rationale.items ?? [];
  const processItems = rationaleItems.filter((item) => /^[^\n]+ observations recorded in task trace\.$/.test(item));
  const keyRationale = rationaleItems.filter((item) => !processItems.includes(item));
  const firstBlocker = rules?.reasons[0];
  const needsReview = detail.task.status === "WAITING_APPROVAL";
  const canApprove = needsReview && detail.result_metadata?.action_eligible === true;
  const symbol = String(detail.task.target.symbol ?? "").trim();
  const dataDate = String(detail.task.target.as_of ?? "—");
  const portfolioEvidence = detail.evidence.find((item) => item.source_type === "portfolio");
  const usesDemoPortfolio = portfolioEvidence?.source === "fixture" || portfolioEvidence?.provider_id === "fixture";
  const positionBlocker = firstBlocker && ["POSITION_LIMIT_EXCEEDED", "ETF_POSITION_LIMIT", "SECTOR_CONCENTRATION"].includes(firstBlocker.code);
  const marketDate = detail.evidence.find((item) => item.source_type === "market")?.as_of;
  const usesDemoMarket = detail.evidence.some((item) => item.source_type === "market" && (item.source === "fixture" || item.provider_id === "fixture"));
  const taskTitle = holdingsReview ? "收盘持仓复核" : detail.task.trigger_type === "MarketClose" ? "收盘市场复盘" : symbol ? `${symbol} 研究` : detail.task.trigger_type;
  const [evidenceQuery, setEvidenceQuery] = useState("");
  const [evidenceQualityFilter, setEvidenceQualityFilter] = useState("all");
  const [quickNoteOpen, setQuickNoteOpen] = useState(false);
  const [quickNote, setQuickNote] = useState("");
  const [quickError, setQuickError] = useState("");
  const [saved, setSaved] = useState(false);
  const latestRetrospective = detail.retrospectives[0];
  const evidence = detail.evidence.filter((item) => {
    const query = evidenceQuery.trim().toLowerCase();
    const matchesQuery = !query || [item.title, item.source, item.excerpt].some((value) => value.toLowerCase().includes(query));
    const matchesQuality = evidenceQualityFilter === "all" || evidenceQuality(item) === evidenceQualityFilter;
    return matchesQuery && matchesQuality;
  });
  return <div className="detail-content">
    <div className="detail-heading">
      <div><span className="eyebrow">研究简报 · {dataDate}</span><h2>{taskTitle}</h2><span className="detail-id">{detail.task.trigger_type} · {detail.task.id}</span></div>
      <div className="detail-actions">
        {!holdingsReview && <StatusBadge status={detail.task.status} />}
        <button className="icon-button" title="复制链接" aria-label="复制链接" onClick={onCopyLink} disabled={busy}><LinkSimpleIcon size={16} aria-hidden="true" /></button>
        <button className="icon-button" title="原始数据" aria-label="原始数据" onClick={onRawData} disabled={busy}><DatabaseIcon size={16} aria-hidden="true" /></button>
        <button className="icon-button" title="回放研究" aria-label="回放研究" onClick={onReplay} disabled={busy}><ArrowCounterClockwiseIcon size={16} aria-hidden="true" /></button>
        <button className="icon-button" title="导出上下文" aria-label="导出上下文" onClick={onExport} disabled={busy}><ExportIcon size={16} aria-hidden="true" /></button>
        {detail.task.status === "QUEUED" && <button className="danger-button" onClick={onCancel} disabled={busy}>取消</button>}
        {["PLANNING", "RUNNING", "REVIEWING"].includes(detail.task.status) && <><button className="quiet-button" onClick={() => onControl("pause")} disabled={busy}>暂停</button><button className="danger-button" onClick={onCancel} disabled={busy}>取消</button></>}
        {detail.task.status === "PAUSED" && <><button className="primary-button" onClick={() => onControl("resume")} disabled={busy}>继续</button><button className="danger-button" onClick={onCancel} disabled={busy}>取消</button></>}
        {!holdingsReview && ["RETRYABLE", "FAILED", "TIMEOUT"].includes(detail.task.status) && <><button className="quiet-button" onClick={onTakeover} disabled={busy}>接管研究</button><button className="primary-button" onClick={onRetry} disabled={busy}>重试</button></>}
      </div>
    </div>
    {holdingsReview && <HoldingsReviewResult review={holdingsReview} onConfirmed={onHoldingsConfirmed}
      onOpenPortfolio={onOpenPortfolio} onRetry={onHoldingsRetry} />}
    {!holdingsReview && <div className="decision-strip">
      <div><span className="eyebrow">研究结论</span><strong className={`decision-${(decision?.status ?? "PENDING").toLowerCase()}`}>{statusLabel(decision?.status ?? "PENDING")}</strong>
        {firstBlocker && <p className="decision-reason">{ruleReasonLabel(firstBlocker)} · {ruleComparison(firstBlocker)}{(rules?.reasons.length ?? 0) > 1 && <> · <a href="#research-rules">查看全部 {rules?.reasons.length} 项</a></>}</p>}
        <span>{detail.task.error?.code === "PORTFOLIO_AS_OF_UNAVAILABLE" ? `没有 ${dataDate} 或更早的持仓快照。请导入对应日期的持仓，再重试。` : decision?.next_action ? `下一步：${nextActionLabel(decision.next_action)}` : "当前尚无研究结论"}</span></div>
      <div className="decision-meta"><span>信心 <b>{localizedLabel(levelLabels, decision?.confidence)}</b></span><span>风险 <b>{localizedLabel(levelLabels, decision?.risk_level)}</b></span>{marketDate && <span>{usesDemoMarket ? "演示行情" : "行情日期"} <b>{marketDate}</b></span>}{portfolioEvidence && <span>{usesDemoPortfolio ? "示例持仓" : "持仓日期"} <b>{portfolioEvidence.as_of}</b></span>}</div>
    </div>}
    {decision && (!holdingsReview || holdingsReview.confirmed_at) && <section className="research-next panel" aria-label="处理研究">
      <div className="research-next-actions">
        {detail.evidence.length > 0 && <a className="quiet-button"
          href={positionBlocker && portfolioEvidence ? `#evidence-${portfolioEvidence.id}` : "#research-evidence"}
          onClick={() => {
            setEvidenceQuery("");
            setEvidenceQualityFilter("all");
          }}>{positionBlocker && portfolioEvidence ? "查看持仓依据" : "查看依据"}</a>}
        {usesDemoPortfolio && <button className="quiet-button" onClick={onOpenPortfolio}>添加我的持仓</button>}
        {needsReview && <a className="quiet-button" href="#research-approval">查看处理选项</a>}
        {!needsReview && <button className="primary-button" disabled={busy} onClick={() => {
          setQuickNoteOpen(true);
          setSaved(false);
        }}>记录不行动</button>}
        {(latestRetrospective || saved) && <button className="quiet-button" onClick={onOpenJournal}>查看本次决策日志</button>}
      </div>
      {saved && <p role="status">已记录不行动。</p>}
      {quickNoteOpen && <form className="quick-retrospective" onSubmit={async (event) => {
        event.preventDefault();
        setQuickError("");
        try {
          await onRetrospective({
            action_taken: "NOT_TAKEN",
            outcome: { status: "unknown", horizon: "USER_RECORDED" },
            notes: quickNote.trim(),
          });
          setQuickNote("");
          setQuickNoteOpen(false);
          setSaved(true);
        } catch (error) {
          setQuickError(friendlyError(error, "保存失败，可以重试。"));
        }
      }}>
        <label>不行动的原因<textarea rows={2} value={quickNote} autoFocus placeholder="可选" onChange={(event) => setQuickNote(event.target.value)} /></label>
        {quickError && <p role="alert">{quickError}</p>}
        <div className="research-next-actions">
          <button className="primary-button" disabled={busy}>保存不行动记录</button>
          <button type="button" className="quiet-button" disabled={busy} onClick={() => setQuickNoteOpen(false)}>取消</button>
        </div>
      </form>}
    </section>}
    {!holdingsReview && <>
    <div className="result-summary" role="status">
      <strong>结果：{["QUEUED", "PLANNING", "RUNNING", "REVIEWING", "PAUSED"].includes(detail.task.status) ? "处理中" : ({ complete: "完整", partial: "部分结果", none: "无可用结果", unknown: "历史完整性未知" })[detail.result_metadata?.completion ?? "unknown"]}</strong>
      <span> · 数据 {localizedLabel(qualityLabels, detail.result_metadata?.quality_summary, "未知")} · {canApprove ? "可确认建议" : needsReview ? "待处理 · 仅供研究" : "仅供研究"}</span>
      {!!detail.result_metadata?.reasons?.length && <div className="result-limitations"><strong>限制与缺口 ({detail.result_metadata.reasons.length})</strong>
        {detail.result_metadata.reasons.map((reason, index) => <p key={`${reason.code}-${index}`}>
          <a href="#research-flow" onClick={() => document.getElementById("research-flow")?.setAttribute("open", "")}>{reason.code === "CAPABILITY_UNAVAILABLE" ? "数据能力不可用" : reason.code}</a>
          {" · "}{({ fundamentals: "基本面数据", sources: "来源数据" } as Record<string, string>)[reason.capability ?? ""] ?? reason.capability ?? reason.stage_id ?? "context"}
          {reason.retryable && <button className="quiet-button" onClick={onRetry} disabled={busy}>新建重试</button>}
        </p>)}
      </div>}
    </div>
    <div className="detail-grid">
      <Panel title="为什么得到这个结论" eyebrow="结论依据">
        {keyRationale.length ? keyRationale.map((item) => {
          const reason = ruleReasons.find((candidate) => candidate.message === item);
          return <p className="rationale" key={item}><span>•</span>{reason ? ruleReasonLabel(reason) : item.replace(/^Research coverage missing: /, "研究覆盖缺失：")}</p>;
        }) : <EmptyState message={decision ? "暂无线索摘要，请查看来源和研究过程。" : "等待结构化结论"} />}
        {processItems.length > 0 && <details className="rationale-process"><summary>研究过程记录 ({processItems.length})</summary>
          {processItems.map((item) => <p key={item}>{researchAgentLabel(item.replace(/ observations recorded in task trace\.$/, ""))}：结果已记录在研究过程中。</p>)}
        </details>}
      </Panel>
      <Panel title="规则检查" eyebrow={rules?.rule_snapshot_id ?? "等待审核"}>
        <span id="research-rules" />
        <RuleList rules={rules} />
      </Panel>
      <Panel title="多空观点" eyebrow="结构化分歧" wide>
        <DebateView debate={detail.debate ?? {}} />
      </Panel>
    </div>
    {needsReview && <section className="approval-bar" id="research-approval" tabIndex={-1} aria-labelledby="research-approval-heading">
      <div>
        <h3 id="research-approval-heading">{canApprove ? "确认研究建议" : "处理研究结果"}</h3>
        <strong>{canApprove ? "确认会记录你的研究决定。" : "当前结果仅供研究，可记录处理决定。"}</strong>
        <small>风险 {localizedLabel(levelLabels, decision?.risk_level)} · 规则版本 {detail.task.rule_snapshot_id ?? "—"} · 数据日期 {dataDate}</small>
        <small>数据快照 {detail.task.data_snapshot_id ?? "—"}</small>
      </div>
      <div className="approval-actions">
        <button className="quiet-button" onClick={() => onApprove("REQUEST_MORE_RESEARCH")} disabled={busy}>继续研究</button>
        {symbol && <button className="quiet-button" onClick={() => onApprove("MARK_AS_WATCH")} disabled={busy}>加入观察</button>}
        <button className="quiet-button" onClick={() => onApprove("NO_ACTION")} disabled={busy}>暂不行动</button>
        <button className="danger-button" onClick={() => onApprove("REJECT")} disabled={busy}>拒绝</button>
        {canApprove && <button className="primary-button" onClick={() => onApprove("APPROVE")} disabled={busy}>确认建议</button>}
      </div>
    </section>}
    </>}
    <Panel title="依据" eyebrow={`${evidence.length} / ${detail.evidence.length} 条引用来源`} wide>
        <span id="research-evidence" />
        <div className="evidence-filters">
          <input value={evidenceQuery} placeholder="筛选来源或文本" onChange={(event) => setEvidenceQuery(event.target.value)} />
          <select value={evidenceQualityFilter} onChange={(event) => setEvidenceQualityFilter(event.target.value)}>
            <option value="all">全部质量</option>
            <option value="verified">已验证</option>
            <option value="partial">部分验证</option>
            <option value="stale">已过期</option>
            <option value="unavailable">不可用</option>
          </select>
        </div>
        <div className="evidence-list">{evidence.map((item) => <EvidenceRow key={item.id} evidence={item} onCopyLink={() => onCopyEvidenceLink(item.id)} />)}</div>
    </Panel>
    <RunFlow taskId={detail.task.id} revision={detail.events.length} />
    <AgentTimelineChart
      trace={detail.trace}
      asOf={String(detail.task.target.as_of ?? "—")}
      source={String(detail.task.data_snapshot_id ?? "任务快照")}
    />
    <Panel title="研究过程" eyebrow={`${detail.trace.length} 次运行`} wide>
      <span id="research-trace" />
      <div className="trace-list">{detail.trace.map((trace) => <TraceRowView key={trace.id ?? trace.agent_name} trace={trace} toolCalls={(detail.tool_calls ?? []).filter((call) => call.agent_run_id === trace.id)} />)}</div>
      {detail.llm_usage && detail.llm_usage.records > 0 && <div className="trace-usage">
        <span>模型用量</span>
        <strong>{detail.llm_usage.total_tokens.toLocaleString("zh-CN")} 个词元</strong>
        <small>{detail.llm_usage.request_count} 次请求 · ${detail.llm_usage.cost_usd.toFixed(4)}</small>
      </div>}
      {detail.llm_ledger && <p className="form-hint">费用 ${detail.llm_ledger.known_cost_usd} · 保守占用 ${detail.llm_ledger.conservative_reserved_usd} · {detail.llm_ledger.unknown_count} 次费用未知 · 日预算按 UTC 结算</p>}
    </Panel>
    {rawData && <TaskDataPanel data={rawData} />}
    {(!holdingsReview || holdingsReview.confirmed_at) && <RetrospectivePanel retrospectives={detail.retrospectives ?? []} busy={busy} onSubmit={onRetrospective} onOpenJournal={onOpenJournal} />}
  </div>;
}

function TaskDataPanel({ data }: { data: TaskDataResponse }) {
  return <Panel title="原始数据与回放输入" eyebrow={`${data.bundles.length} 个快照`} wide>
    <div className="snapshot-bundle-list">{data.bundles.map((bundle) => {
      const snapshot = bundle.snapshot;
      return <details className="snapshot-bundle" key={String(snapshot.snapshot_id)}>
        <summary><strong>{String(snapshot.snapshot_id)}</strong><span>{String(snapshot.kind ?? "快照")} · {String(snapshot.quality ?? "未知")} · {String(snapshot.as_of ?? "—")}</span></summary>
        <div className="snapshot-bundle-body">
          <pre>{JSON.stringify(snapshot.payload ?? snapshot, null, 2)}</pre>
          <span className="eyebrow">数据源原始载荷（{bundle.raw_payloads.length}）</span>
          {bundle.raw_payloads.map((raw) => <details className="raw-payload" key={String(raw.id)}>
            <summary>{String(raw.id)} · {String(raw.provider_id)}</summary>
            <pre>{JSON.stringify(raw.payload ?? raw, null, 2)}</pre>
          </details>)}
        </div>
      </details>;
    })}</div>
  </Panel>;
}

function RetrospectivePanel({ retrospectives, busy, onSubmit, onOpenJournal }: {
  retrospectives: TaskDetail["retrospectives"];
  busy: boolean;
  onSubmit: (payload: RetrospectiveInput) => Promise<void>;
  onOpenJournal: () => void;
}) {
  const [action, setAction] = useState("NOT_TAKEN");
  const [horizon, setHorizon] = useState("USER_RECORDED");
  const [outcomeStatus, setOutcomeStatus] = useState("observed");
  const [returnPct, setReturnPct] = useState("");
  const [benchmarkReturnPct, setBenchmarkReturnPct] = useState("");
  const [marketRegime, setMarketRegime] = useState("");
  const [positionSizePct, setPositionSizePct] = useState("");
  const [notes, setNotes] = useState("");
  const [saveStatus, setSaveStatus] = useState<{ error?: string } | null>(null);
  const submit = async () => {
    const outcome: Record<string, unknown> = {
      status: outcomeStatus,
      horizon,
    };
    for (const [key, rawValue] of [
      ["return_pct", returnPct],
      ["benchmark_return_pct", benchmarkReturnPct],
      ["position_size_pct", positionSizePct],
    ] as const) {
      if (rawValue.trim()) {
        const parsed = Number(rawValue);
        if (Number.isFinite(parsed)) outcome[key] = parsed;
      }
    }
    if (marketRegime.trim()) outcome.market_regime = marketRegime.trim();
    setSaveStatus(null);
    try {
      await onSubmit({ action_taken: action, outcome, notes: notes.trim() });
    } catch (error) {
      setSaveStatus({ error: friendlyError(error, "保存复盘失败，可以重试。") });
      return;
    }
    setSaveStatus({});
    setNotes("");
    setReturnPct("");
    setBenchmarkReturnPct("");
    setMarketRegime("");
    setPositionSizePct("");
  };
  return <Panel title="规则复盘" eyebrow="实际行动与结果" wide>
    <div className="retrospective-form">
      <select value={action} onChange={(event) => setAction(event.target.value)}>
        <option value="NOT_TAKEN">未采取行动</option>
        <option value="APPROVE">采纳建议</option>
        <option value="REJECT">拒绝建议</option>
        <option value="NO_ACTION">记录为暂不行动</option>
        <option value="OTHER">其他行动</option>
      </select>
      <select value={outcomeStatus} onChange={(event) => setOutcomeStatus(event.target.value)}>
        <option value="observed">已观察</option>
        <option value="positive">正向</option>
        <option value="negative">负向</option>
        <option value="mixed">混合</option>
        <option value="unknown">未知</option>
      </select>
      <select value={horizon} onChange={(event) => setHorizon(event.target.value)}>
        <option value="USER_RECORDED">实际记录</option>
        <option value="T+5">T+5</option>
        <option value="T+20">T+20</option>
      </select>
      <input
        type="number"
        step="0.01"
        value={returnPct}
        placeholder="收益率 %"
        onChange={(event) => setReturnPct(event.target.value)}
      />
      <input
        type="number"
        step="0.01"
        value={benchmarkReturnPct}
        placeholder="基准收益 %"
        onChange={(event) => setBenchmarkReturnPct(event.target.value)}
      />
      <input
        type="number"
        step="0.01"
        min="0"
        max="100"
        value={positionSizePct}
        placeholder="仓位 %"
        onChange={(event) => setPositionSizePct(event.target.value)}
      />
      <input
        value={marketRegime}
        placeholder="市场环境"
        onChange={(event) => setMarketRegime(event.target.value)}
      />
      <input
        value={notes}
        placeholder="复盘备注"
        onChange={(event) => setNotes(event.target.value)}
      />
      <button className="primary-button" onClick={() => void submit()} disabled={busy}>保存复盘</button>
    </div>
    {saveStatus?.error && <p className="form-hint" role="alert">{saveStatus.error}</p>}
    {saveStatus && !saveStatus.error && <div className="form-row" role="status">已保存复盘。<button className="quiet-button" onClick={onOpenJournal}>查看本次决策日志</button></div>}
    <span className="form-hint">每次保存都会追加一条观察记录；收益和基准收益只描述结果，不代表决策正确。</span>
    {retrospectives.length === 0 ? <EmptyState message="还没有实际操作或结果记录。" /> :
      <div className="retrospective-list">{retrospectives.map((item) => <article className="retrospective-row" key={item.id}>
        <div><strong>{String(item.outcome.horizon ?? "USER_RECORDED")}</strong><span>{formatDate(item.observed_at)}</span></div>
        <p>{localizedLabel(retrospectiveActionLabels, item.action_taken)} · {localizedLabel({ observed: "已观察", positive: "正向", negative: "负向", mixed: "混合", unknown: "未知" }, item.outcome.status, "未知")}{item.outcome.return_pct !== undefined ? ` · 收益 ${String(item.outcome.return_pct)}%` : ""}{item.outcome.benchmark_return_pct !== undefined ? ` · 基准 ${String(item.outcome.benchmark_return_pct)}%` : ""}{item.outcome.excess_return_pct !== undefined ? ` · 超额 ${String(item.outcome.excess_return_pct)}%` : ""}</p>
        {item.notes && <small>{item.notes}</small>}
      </article>)}</div>}
  </Panel>;
}

function DebateView({ debate }: { debate: Record<string, Record<string, unknown>> }) {
  const rows = Object.entries(debate);
  if (!rows.length) return <EmptyState message="等待多空辩论结果" />;
  return <div className="debate-grid">{rows.map(([agent, output]) => {
    const points = Array.isArray(output.points) ? output.points : [];
    const unresolved = Array.isArray(output.unresolved_questions) ? output.unresolved_questions : [];
    return <article className="debate-case" key={agent}><strong>{researchAgentLabel(agent)}</strong><span>{localizedLabel({ bull: "看多", bear: "看空" }, output.stance ?? output.verdict, "")}</span>{points.map((point) => <p key={String(point)}>• {String(point)}</p>)}{unresolved.map((question) => <small key={String(question)}>待回答：{String(question)}</small>)}</article>;
  })}</div>;
}

function Panel({ title, eyebrow, wide, actions, children }: {
  title: string; eyebrow?: string; wide?: boolean; actions?: ReactNode; children: ReactNode;
}) {
  return <section className={`sub-panel ${wide ? "wide" : ""}`}><div className="panel-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h3>{title}</h3></div>{actions}</div>{children}</section>;
}

const ruleReasonLabels: Record<string, string> = {
  STALE_DATA: "行情快照已过期",
  DATA_UNAVAILABLE: "行情快照未通过验证",
  MARKET_VOLATILITY_FAILED: "市场波动率超过阈值",
  RISK_REVIEW_FAILED: "组合回撤触及严重阈值",
  DRAWDOWN_LIMIT: "组合回撤触及限制",
  DRAWDOWN_WARNING: "组合回撤触及预警阈值",
  EVIDENCE_INSUFFICIENT: "证据条数未达到最低要求",
  UNIVERSE_REJECTED: "标的不在允许研究范围内",
  NEW_LISTING: "标的尚未达到最短上市观察期",
  LOW_LIQUIDITY: "标的成交额低于最低要求",
};

function ruleReasonLabel(reason: RuleReason) {
  const position = reason.message.match(/^(\S+) weight exceeds the configured position limit\.$/);
  const sector = reason.message.match(/^Sector exposure for (.+) exceeds the configured limit\.$/);
  if (position) return `${position[1]} 仓位超限`;
  if (sector) return `${sector[1]}行业仓位超限`;
  if (reason.code === "MARKET_CONDITION_FAILED") {
    return typeof reason.actual === "number" ? "市场宽度低于阈值" : "指数趋势未满足规则";
  }
  return Object.hasOwn(ruleReasonLabels, reason.code) ? ruleReasonLabels[reason.code] : reason.message;
}

function rulePercent(value: unknown) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("zh-CN", { style: "percent", maximumFractionDigits: 2 })
    : "—";
}

function ruleComparison(reason: RuleReason) {
  const { code, actual, expected } = reason;
  const threshold = typeof expected === "string" ? expected.match(/^([<>]=?)\s*(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)$/i) : null;
  const ratio = [
    "POSITION_LIMIT_EXCEEDED", "ETF_POSITION_LIMIT", "SECTOR_CONCENTRATION", "DRAWDOWN_LIMIT",
    "DRAWDOWN_WARNING", "RISK_REVIEW_FAILED", "MARKET_VOLATILITY_FAILED", "MARKET_CONDITION_FAILED",
  ].includes(code) && typeof actual === "number" && threshold;
  const labels = { ...qualityLabels, ...trendLabels, eligible: "符合范围要求", "eligible for the user's Profile": "符合投资设置" };
  const actualLabel = ratio ? rulePercent(actual) : localizedLabel(labels, actual);
  const expectedLabel = threshold
    ? `${threshold[1].replace("<=", "≤").replace(">=", "≥")} ${ratio ? rulePercent(Number(threshold[2])) : threshold[2]}`
    : localizedLabel(labels, expected);
  return `实际 ${actualLabel} · 要求 ${expectedLabel}`;
}

function RuleList({ rules }: { rules?: RuleResult }) {
  if (!rules) return <EmptyState message="等待规则审核" />;
  const rows = [
    ...rules.reasons.map((reason) => ({ ...reason, state: "BLOCKED" })),
    ...rules.warnings.map((reason) => ({ ...reason, state: "WARN" })),
  ];
  if (!rows.length) return <p className="pass-line"><span>✓</span> 所有 P0 门禁通过</p>;
  return <div className="rule-list">{rows.map((row) => <div className="rule-row" key={`${row.code}-${row.message}`}>
    <span className={`rule-state ${row.state.toLowerCase()}`}>{row.state === "BLOCKED" ? "已拦截" : "警告"}</span>
    <div>
      <strong>{ruleReasonLabel(row)}</strong>
      <p>{ruleComparison(row)}</p>
      <details className="rule-original">
        <summary>规则详情</summary>
        <code>{row.code}</code>
        <p>{row.message}</p>
      </details>
    </div>
  </div>)}</div>;
}

function EvidenceRow({ evidence, onCopyLink }: { evidence: Evidence; onCopyLink: () => void }) {
  const quality = evidenceQuality(evidence);
  const usedBy = evidence.used_by?.length ? evidence.used_by.map(researchAgentLabel).join(" · ") : "尚未关联研究过程";
  return <article id={`evidence-${evidence.id}`} className="evidence-row" tabIndex={0} aria-label={`依据：${evidence.title}`}>
    <div className="evidence-icon"><ArrowUpRightIcon size={16} aria-hidden="true" /></div>
    <div>
      <strong>{evidence.title}</strong>
      <p>{evidence.excerpt}</p>
      <span>{evidence.source}{evidence.provider_id ? ` · 数据源 ${evidence.provider_id}` : ""} · {evidence.as_of} · 到期 {evidence.expires_at} · 快照 {evidence.snapshot_id}</span>
      <span className="evidence-used-by">关联研究过程：{usedBy}</span>
    </div>
    <button className="icon-button evidence-link-button" title="复制依据链接" aria-label="复制依据链接" onClick={onCopyLink}><LinkSimpleIcon size={16} aria-hidden="true" /></button>
    <span className={`quality ${quality}`}>{qualityLabels[quality] ?? quality}</span>
  </article>;
}

function TraceRowView({ trace, toolCalls }: { trace: TraceRow; toolCalls: Array<Record<string, unknown>> }) {
  return <details className="trace-entry">
    <summary className="trace-row"><CaretRightIcon className="trace-chevron" size={16} aria-hidden="true" /><div><strong>{researchAgentLabel(trace.agent_name)}</strong><span>{formatDate(trace.started_at)}</span></div><StatusBadge status={trace.status} /><small>{trace.finished_at ? `${Math.max(1, Math.round((new Date(trace.finished_at).getTime() - new Date(trace.started_at).getTime())))} 毫秒` : "—"}{trace.token_usage ? ` · ${trace.token_usage} 个词元` : ""}</small></summary>
    <div className="trace-expanded">
      <div><span className="eyebrow">工具调用</span><strong>{toolCalls.length}</strong></div>
      {toolCalls.map((call) => <div className="trace-tool" key={String(call.id)}><strong>{String(call.tool_name)}</strong><StatusBadge status={String(call.status ?? "DONE")} /></div>)}
      {trace.output_json && <pre>{trace.output_json}</pre>}
    </div>
  </details>;
}
