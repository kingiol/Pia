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
import { api, Evidence, JournalItem, JournalPatterns, JournalSummary, RuleResult, Task, TaskDataResponse, TaskDetail, TaskInput, TaskStatus, TraceRow, Watchlist } from "./api";
import type { LocalCredentialStatus, RuleReason } from "./api";
import { registerWebPushDevice } from "./push";
import { RunFlow } from "./components/RunFlow";

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

const webRoutes: Record<string, string> = {
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

function viewFromWebPath(pathname: string) {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  if (normalized.startsWith("/research/")) return "Research";
  return Object.entries(webRoutes).find(([, path]) => path === normalized)?.[0] ?? "Overview";
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
    const payload = JSON.parse(raw) as { error?: string; message?: string };
    const code = payload.error ?? payload.message;
    if (code === "task_not_found") return "这条研究记录已不存在。";
    if (code === "unauthorized") return "云端工作区需要重新连接，请输入访问令牌。";
    if (code) return `请求未完成：${code}`;
  } catch {
    // The runtime may return a plain-text transport error.
  }
  if (/failed to fetch|networkerror|connection refused/i.test(raw)) {
    return "无法连接运行时，请检查所选环境的服务地址和网络后重试。";
  }
  return raw.length > 220 ? `${raw.slice(0, 217)}…` : raw;
}

const REPLAY_AS_OF = "2026-11-05";

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
  market: Record<string, unknown> | null,
  requestedDate?: string,
): TaskInput {
  const demo = health?.provider?.provider_id === "fixture";
  const demoSnapshot = market?.provider_id === "fixture" || market?.source === "fixture";
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

function SetupGuide({ setup, onNavigate, onCreateReview }: {
  setup: SetupState;
  onNavigate: (view: string) => void;
  onCreateReview: () => void;
}) {
  const steps = [
    { key: "profile" as const, title: "告诉 Pia 你的投资方式", description: "风险偏好、投资目标和可研究范围", action: "去设置", onClick: () => onNavigate("Profile") },
    { key: "portfolio" as const, title: "导入你的持仓", description: "支持 CSV、Excel 或手工录入", action: "导入持仓", onClick: () => onNavigate("Portfolio") },
    { key: "rules" as const, title: "设置一条持仓规则", description: "为单只股票设置仓位上限", action: "设置规则", onClick: () => onNavigate("Rules") },
    { key: "data" as const, title: "确认数据准备好", description: "检查行情源、数据日期和模型凭据", action: "检查数据", onClick: () => onNavigate("Data Health") },
    { key: "review" as const, title: "完成第一次收盘复盘", description: "Pia 会给出结论、依据和风险提示", action: "开始复盘", onClick: onCreateReview },
  ];
  const completed = steps.filter((step) => setup[step.key]).length;
  const next = steps.find((step) => !setup[step.key]);
  return <section className={`welcome-panel panel ${completed === steps.length ? "setup-complete" : ""}`}>
    <div className="welcome-copy">
      <span className="eyebrow">{completed === steps.length ? "准备就绪" : "首次设置"}</span>
      <h2>{completed === steps.length ? "研究准备已完成" : "准备你的研究工作台"}</h2>
      <p>按你的投资纪律研究，由你确认行动</p>
      <progress className="setup-progress" value={completed} max={steps.length} aria-label="研究设置完成进度" />
      <small>{completed}/{steps.length} 已完成</small>
    </div>
    <div className="setup-steps">
      {steps.map((step, index) => <button className={`setup-step ${setup[step.key] ? "complete" : ""} ${next?.key === step.key ? "current" : ""}`} key={step.key} aria-current={next?.key === step.key ? "step" : undefined} onClick={step.onClick}>
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

export function App({ runtimeControl, runtimeReady = true, runtimeMode }: { runtimeControl?: ReactNode; runtimeReady?: boolean; runtimeMode?: "local" | "cloud" } = {}) {
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
  const [health, setHealth] = useState<{ status: string; runtime: string; provider: { status: string; provider_id?: string }; llm: { model: string; credentials_configured: boolean }; scheduler?: { enabled: boolean; timezone: string; close_time: string; last_dispatched_date: string | null } } | null>(null);
  const [rules, setRules] = useState<Record<string, unknown> | null>(null);
  const [market, setMarket] = useState<Record<string, unknown> | null>(null);
  const [portfolio, setPortfolio] = useState<Record<string, unknown> | null>(null);
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [candidates, setCandidates] = useState<Array<Record<string, unknown>>>([]);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [journalItems, setJournalItems] = useState<JournalItem[]>([]);
  const [journalSummary, setJournalSummary] = useState<JournalSummary | null>(null);
  const [journalPatterns, setJournalPatterns] = useState<JournalPatterns | null>(null);
  const [notifications, setNotifications] = useState<NotificationRow[]>([]);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [view, setView] = useState(() => {
    if (typeof window === "undefined" || isTauriRuntime()) return "Overview";
    return viewFromWebPath(window.location.pathname);
  });
  const [busy, setBusy] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [pushStatus, setPushStatus] = useState("");
  const [dataQuality, setDataQuality] = useState<Record<string, unknown> | null>(null);
  const [taskData, setTaskData] = useState<TaskDataResponse | null>(null);
  const [searchQuery, setSearchQuery] = useState(() => {
    if (typeof window === "undefined" || isTauriRuntime()) return "";
    return new URLSearchParams(window.location.search).get("q") ?? "";
  });
  const searchRef = useRef<HTMLInputElement>(null);

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
    if (typeof window !== "undefined" && isTauriRuntime()) {
      const url = new URL(window.location.href);
      if (taskId) url.searchParams.set("task", taskId);
      else url.searchParams.delete("task");
      window.history.replaceState({}, "", url);
    }
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
  }, [selectTask]);

  const openResearch = (taskId: string) => {
    selectTask(taskId);
    setMobileDetailOpen(true);
    if (window.matchMedia("(max-width: 700px)").matches) {
      window.requestAnimationFrame(() => document.getElementById("return-to-research-queue")?.focus());
    }
  };

  const returnToQueue = () => {
    setMobileDetailOpen(false);
    window.requestAnimationFrame(() => {
      const row = document.getElementById(`task-${selectedTaskRef.current}`);
      (row ?? document.getElementById("research-queue-heading"))?.focus();
    });
  };

  const refresh = useCallback(async () => {
    try {
      const [taskResult, healthResult, ruleResult, marketResult, portfolioResult, profileResult, watchlistResult, notificationResult, journalResult, journalSummaryResult, journalPatternsResult] = await Promise.all([
        api.tasks(),
        api.health(),
        api.rules(),
        api.market(),
        api.portfolio(),
        api.profile(),
        api.watchlists().catch(() => ({ watchlists: [] })),
        api.notifications().catch(() => ({ notifications: [] })),
        api.journal().catch(() => ({ items: [], next_cursor: null })),
        api.journalSummary().catch(() => ({
          decision_count: 0,
          retrospective_count: 0,
          intent_counts: {},
          action_counts: {},
          outcome_status_counts: {},
          comparable_outcome_count: 0,
          average_return_pct: null,
          rule_snapshot_counts: {},
          warnings: [],
        })),
        api.journalPatterns().catch(() => ({
          intent_patterns: [],
          rule_patterns: [],
          memory_candidates: [],
          warnings: [],
        })),
      ]);
      setTasks(taskResult.tasks);
      setHealth(healthResult);
      setRules(ruleResult.rules);
      setMarket(marketResult);
      setPortfolio(portfolioResult);
      setProfile(profileResult);
      setWatchlists(watchlistResult.watchlists);
      setJournalItems(journalResult.items);
      setJournalSummary(journalSummaryResult);
      setJournalPatterns(journalPatternsResult);
      const nextNotifications = notificationResult.notifications as NotificationRow[];
      setNotifications(nextNotifications);
      setUnreadNotifications(nextNotifications.filter((item) => !item.read_at).length);
      setError(null);
      if (!selectedTaskRef.current && taskResult.tasks[0]) selectTask(taskResult.tasks[0].id);
      const currentTaskInput = taskInput(healthResult, marketResult);
      try {
        const candidateResult = await api.candidates(
          currentTaskInput.asOf,
          currentTaskInput.fixture?.market,
        );
        setCandidates(candidateResult.candidates);
      } catch (candidateError) {
        setCandidates([]);
        const message = friendlyError(candidateError, "候选扫描失败");
        setError(message === "请求未完成：CapabilityUnavailable"
          ? "候选扫描所需的行情暂不可用，请检查数据源和网络，稍后重试。已有快照不代表最新行情。"
          : message);
      }
    } catch (requestError) {
      const message = friendlyError(requestError, "无法连接运行时");
      if (/云端工作区需要重新连接|unauthorized|401/i.test(message)) setAuthRequired(true);
      setError(message);
    }
  }, [selectTask]);

  useEffect(() => {
    if (runtimeControl) return;
    const storedToken = typeof window !== "undefined"
      ? window.sessionStorage.getItem("pia.cloud_token") ?? window.sessionStorage.getItem("pia.server_token")
      : null;
    if (storedToken) api.setToken(storedToken);
  }, [runtimeControl]);
  useEffect(() => { if (runtimeReady) void refresh(); }, [refresh, runtimeReady]);
  useEffect(() => {
    if (typeof window === "undefined" || isTauriRuntime()) return;
    const url = new URL(window.location.href);
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
    window.history.replaceState({}, "", url);
  }, [searchQuery, selectedId, view, mobileDetailOpen]);
  useEffect(() => {
    if (!selectedId || !runtimeReady) return;
    let loading = false;
    const update = async () => {
      if (loading) return;
      loading = true;
      await loadDetail(selectedId);
      loading = false;
    };
    const refreshSelection = () => {
      void update();
      void api.tasks().then((result) => setTasks(result.tasks)).catch(() => undefined);
    };
    void update();
    const unsubscribe = api.subscribeTask(selectedId, refreshSelection);
    const handle = window.setInterval(refreshSelection, 1200);
    return () => { unsubscribe(); window.clearInterval(handle); };
  }, [selectedId, runtimeReady, loadDetail]);

  const createTask = async () => {
    if (!runtimeReady) return;
    setBusy(true);
    try {
      const date = health?.provider?.provider_id === "fixture" ? REPLAY_AS_OF : shanghaiDate();
      const result = await api.createTask(taskInput(health, market, date));
      openResearch(result.task.id);
      setView("Overview");
      await refresh();
    } catch (requestError) {
      setError(friendlyError(requestError, "创建任务失败"));
    } finally {
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
          await refresh();
          return;
        }
        if (event.payload === "pause-scheduler") {
          try {
            await api.stopScheduler();
            setView("Data Health");
            await refresh();
            setError(null);
          } catch (requestError) {
            setError(friendlyError(requestError, "暂停调度器失败"));
          }
          return;
        }
        if (event.payload === "resume-scheduler") {
          try {
            await api.startScheduler();
            setView("Data Health");
            await refresh();
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
  }, [refresh]);

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
  }, []);

  const createResearch = async (symbol: string) => {
    setBusy(true);
    try {
      const result = await api.createResearchTask(symbol, taskInput(health, market));
      openResearch(result.task.id);
      setView("Research");
      await refresh();
    } catch (requestError) {
      setError(friendlyError(requestError, "创建个股研究失败"));
    } finally {
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
    try {
      const result = await api.retry(selectedId);
      selectTask(result.task.id);
      await refresh();
      await loadDetail(result.task.id);
    } catch (requestError) {
      setError(friendlyError(requestError, "重试任务失败"));
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

  const saveWatchlist = async (name: string, symbols: string[]) => {
    setBusy(true);
    try {
      await api.saveWatchlist(name, symbols);
      setWatchlists((await api.watchlists()).watchlists);
      setError(null);
    } catch (requestError) {
      setError(friendlyError(requestError, "保存关注列表失败"));
    } finally {
      setBusy(false);
    }
  };

  const saveJournalCandidate = async (candidateKey: string) => {
    setBusy(true);
    try {
      await api.materializeJournalMemoryCandidate(candidateKey);
      await refresh();
      setError(null);
    } catch (requestError) {
      setError(friendlyError(requestError, "保存 Memory candidate 失败"));
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
      setError(friendlyError(requestError, "审核 Memory candidate 失败"));
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
      setError(friendlyError(requestError, "保存 Memory 效果反馈失败"));
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

  const recordRetrospective = async (payload: {
    action_taken: string;
    outcome: Record<string, unknown>;
    notes?: string;
    observed_at?: string | null;
  }) => {
    if (!selectedId) return;
    setBusy(true);
    try {
      await api.recordRetrospective(selectedId, payload);
      await loadDetail(selectedId);
      setError(null);
    } catch (requestError) {
      setError(friendlyError(requestError, "保存复盘失败"));
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
      setUnreadNotifications((count) => Math.max(0, count - 1));
    } catch (requestError) {
      setError(friendlyError(requestError, "标记通知失败"));
    }
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
  const setup = useMemo<SetupState>(() => ({
    profile: Boolean(profile?.payload && Object.keys(profile.payload as Record<string, unknown>).length > 0),
    portfolio: Boolean(portfolio?.source === "import" && Array.isArray(portfolio.positions) && portfolio.positions.length > 0),
    rules: Boolean(rules?.version && rules.version !== "v1"),
    data: health?.status === "ok" && health.provider.status === "healthy" && market?.quality === "verified"
      && market.as_of === (health.provider.provider_id === "fixture" ? REPLAY_AS_OF : shanghaiDate()),
    review: tasks.some((task) => task.trigger_type === "MarketClose" && !task.target._replay_of
      && !task.error && ["BLOCKED", "NO_ACTION", "WAITING_APPROVAL", "DONE"].includes(task.status)),
  }), [health, market, portfolio, profile, rules, tasks]);
  const isReplayData = market?.provider_id === "fixture" || market?.source === "fixture" || health?.provider?.provider_id === "fixture";
  const dataState = !health
    ? { label: "等待行情数据", tone: "connecting", healthLabel: "正在连接运行环境" }
    : health.status !== "ok"
      ? { label: "数据不可用", tone: "unavailable", healthLabel: "运行时异常" }
      : health.provider.status !== "healthy" || !market?.snapshot_id
        ? { label: "数据降级", tone: "degraded", healthLabel: "需要检查" }
        : isReplayData
          ? { label: "回放数据", tone: "replay", healthLabel: health.provider.provider_id === "fixture" ? "回放就绪" : "非实时快照" }
          : market?.as_of === shanghaiDate() && market.quality === "verified"
            ? { label: "当日行情", tone: "live", healthLabel: "数据正常" }
            : { label: "已有行情快照", tone: "degraded", healthLabel: "请核对日期和质量" };
  const visibleTasks = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return tasks;
    return tasks.filter((task) => [
      task.id,
      task.trigger_type,
      task.status,
      JSON.stringify(task.target),
    ].join(" ").toLowerCase().includes(query));
  }, [searchQuery, tasks]);

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

  const showMobileDetail = Boolean(selectedId && mobileDetailOpen && (view === "Research" || view === "Overview"));
  const showWindowTitlebar = isTauriRuntime() && navigator.userAgent.includes("Macintosh");
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
          {nav.slice(0, 6).map(([label, key, icon]) => <button key={key} title={label} aria-label={label} aria-current={view === key ? "page" : undefined} className={`nav-item ${view === key ? "active" : ""}`} onClick={() => { setView(key); setMobileDetailOpen(false); setNavigationOpen(false); }}><span className="nav-glyph"><NavIcon name={icon} /></span><span className="nav-label">{label}</span></button>)}
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

      <main className={`main${showMobileDetail ? " research-detail-open" : ""}`}>
        <header className="topbar">
          <div className="page-heading">
            <h1 tabIndex={-1}>{view === "Overview" ? "研究总览" : nav.find(([, key]) => key === view)?.[0] ?? view}</h1>
            <div className="page-context">
              <span className="date-chip">{String(market?.as_of ?? taskInput(health, market).asOf)} · 收盘</span>
              <span className={`provenance-chip ${dataState.tone}`}><i />{dataState.label}</span>
              <span className={`health-chip ${dataState.tone}`}><i />{dataState.healthLabel}</span>
            </div>
          </div>
          <div className="topbar-actions">
            <div className="search-field">
              <MagnifyingGlassIcon size={16} aria-hidden="true" />
              <input
                ref={searchRef}
                className="global-search"
                aria-label="搜索研究或股票代码"
                placeholder="搜索研究或股票代码"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <button className="icon-button notification-button" title={`通知 · ${unreadNotifications} 条未读`} aria-label={`通知，${unreadNotifications} 条未读`} onClick={() => setView("Notifications")}><BellIcon size={16} aria-hidden="true" />{unreadNotifications > 0 ? <span className="notification-count">{unreadNotifications > 99 ? "99+" : unreadNotifications}</span> : null}</button>
            <button className="icon-button" title="刷新" aria-label="刷新" onClick={() => void refresh()}><ArrowClockwiseIcon size={16} aria-hidden="true" /></button>
            <button className={`primary-button${view === "Overview" || view === "Research" ? "" : " shortcut-only"}`} data-shortcut="new-review" onClick={() => void createTask()} disabled={busy || !runtimeReady}><PlusIcon size={16} aria-hidden="true" />{health?.provider?.provider_id === "fixture" ? "开始演示复盘" : "开始今日复盘"}</button>
          </div>
        </header>

        {error && <div className="error-banner" role="alert"><WarningCircleIcon size={16} aria-hidden="true" /><strong>需要处理</strong><span>{error}</span><button onClick={() => void refresh()}>重试</button><button className="icon-button" title="关闭提示" aria-label="关闭提示" onClick={() => setError(null)}><XIcon size={16} aria-hidden="true" /></button></div>}

        {view === "Overview" && !Object.values(setup).every(Boolean) && <SetupGuide setup={setup} onNavigate={setView} onCreateReview={() => void createTask()} />}
        {view === "Overview" && <AttentionFeed notifications={notifications} onOpenTask={(taskId) => {
          openResearch(taskId);
          setView("Overview");
        }} />}

        {view === "Overview" && <section className="metrics" aria-label="研究统计">
          <div className="metric"><span>进行中的研究</span><strong>{counts.running}</strong><small>实时更新进度</small></div>
          <div className="metric"><span>等你确认</span><strong>{counts.approval}</strong><small>需要人工判断</small></div>
          <div className="metric"><span>被规则拦截</span><strong>{counts.blocked}</strong><small>先解决风险再行动</small></div>
          <div className="metric"><span>当前规则</span><strong>{String((rules as { version?: unknown } | null)?.version ?? "v1")}</strong><small>每次研究固定版本</small></div>
        </section>}

        {view === "Journal" ? <JournalView items={journalItems} summary={journalSummary} patterns={journalPatterns} onSaveCandidate={(candidateKey) => void saveJournalCandidate(candidateKey)} onReviewCandidate={(candidateId, payload) => void reviewJournalCandidate(candidateId, payload)} onFeedbackCandidate={(candidateId, usageId, rating) => void feedbackJournalCandidate(candidateId, usageId, rating)} onOpenTask={(taskId) => { openResearch(taskId); setView("Research"); }} /> :
          view === "Market" ? <MarketView market={market} candidates={candidates} onResearch={(symbol) => void createResearch(symbol)} onWatch={(symbol) => void saveWatchlist("Research watchlist", [symbol, ...(watchlists.find((list) => list.name === "Research watchlist")?.symbols ?? [])])} /> :
          view === "Watchlist" ? <WatchlistView watchlists={watchlists} candidates={candidates} onSaved={(name, symbols) => void saveWatchlist(name, symbols)} onResearch={(symbol) => void createResearch(symbol)} /> :
          view === "Portfolio" ? <PortfolioView portfolio={portfolio} demoDate={health?.provider?.provider_id === "fixture" ? REPLAY_AS_OF : undefined} onImported={() => void refresh()} /> :
          view === "Profile" ? <ProfileView profile={profile} onSaved={() => void refresh()} localCredentials={runtimeMode === "local" && runtimeReady} /> :
          view === "Rules" ? <RulesView rules={rules} evaluation={detail?.decision?.rationale.rules} onSaved={() => void refresh()} /> :
          view === "Data Health" ? <DataHealthView health={health} syncResult={dataQuality} onSyncResult={(result) => { setDataQuality(result); void refresh(); }} /> :
          view === "Audit" ? <AuditView detail={detail} /> :
          view === "Notifications" ? <NotificationsView
            notifications={notifications}
            onRead={(notification) => void markNotificationRead(notification)}
            onEnablePush={() => void enablePush()}
            pushStatus={pushStatus}
            onOpenTask={(taskId) => {
              openResearch(taskId);
              setView("Overview");
            }}
          /> :
        <div className="workspace">
          <section className="queue-panel panel">
            <div className="panel-header"><div><span className="eyebrow">研究记录</span><h2 id="research-queue-heading" tabIndex={-1}>你的研究</h2></div><span className="count">{tasks.length}</span></div>
            <div className="queue-list">
              {visibleTasks.length === 0 ? <EmptyState message={tasks.length === 0 ? "完成上面的设置后，开始第一次收盘复盘。" : "没有匹配的研究记录。"} /> : <TaskQueue tasks={visibleTasks} selectedId={selectedId} onSelect={selectTask} onOpen={openResearch} />}
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
              : <ResearchDetail key={detail.task.id} detail={detail} busy={busy} rawData={taskData?.task_id === detail.task.id ? taskData : null} onApprove={(action) => void approve(detail.task.id, action)} onControl={controlTask} onCancel={() => void cancelTask()} onRetry={() => void retryTask()} onTakeover={() => void takeoverTask()} onExport={() => void exportTaskContext()} onReplay={() => void replayTask()} onRawData={() => void loadTaskData()} onCopyLink={() => void copyTaskLink()} onCopyEvidenceLink={(evidenceId) => void copyEvidenceLink(evidenceId)} onRetrospective={(payload) => void recordRetrospective(payload)} />}
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
      </main>
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
};

function notificationLabel(eventType: string) {
  const labels: Record<string, string> = {
    MarketClose: "收盘复盘",
    PortfolioRiskChanged: "持仓风险",
    FilingPublished: "公告事件",
    DataQualityDegraded: "数据质量",
    TaskFailed: "任务失败",
    TaskWaitingApproval: "等待确认",
  };
  return labels[eventType] ?? eventType;
}

function AttentionFeed({ notifications, onOpenTask }: {
  notifications: NotificationRow[];
  onOpenTask: (taskId: string) => void;
}) {
  const latest = notifications.slice(0, 3);
  return <section className="attention-panel panel">
    <div className="panel-header">
      <div><span className="eyebrow">Pia 正在关注</span><h2>需要你留意的变化</h2></div>
      <span className="attention-count">{notifications.filter((item) => !item.read_at).length} 未读</span>
    </div>
    {latest.length === 0 ? <div className="attention-empty"><strong>今天还没有需要处理的事件</strong><span>收盘、持仓风险和数据质量变化会自动出现在这里。</span></div> :
      <div className="attention-list">{latest.map((notification) => <article className={`attention-row ${notification.read_at ? "read" : ""}`} key={notification.id}>
        <div className="attention-mark">{notification.read_at ? <CheckIcon size={16} aria-hidden="true" /> : <WarningCircleIcon size={16} aria-hidden="true" />}</div>
        <div className="attention-copy">
          <div><span className="attention-type">{notificationLabel(notification.event_type)}</span><time>{formatDate(notification.created_at)}</time></div>
          <strong>{notification.title}</strong>
          <p>{notification.body}</p>
        </div>
        {notification.task_id && <button className="quiet-button" onClick={() => onOpenTask(notification.task_id as string)}>查看研究</button>}
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
  onNavigate: (view: string) => void;
}) {
  const profilePayload = (profile?.payload ?? {}) as Record<string, unknown>;
  const objective = String(profilePayload.investment_objective ?? "").trim();
  const objectiveLabel = /capital preservation|disciplined growth/i.test(objective)
    ? "稳健增值，优先控制回撤"
    : objective || "还没有设置投资目标";
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
      <div className="strategy-agent-heading"><span className="eyebrow">你的 Agent</span><span className={`agent-status ${agentStatusTone}`}><i className="agent-status-dot" />{agentStatus}</span></div>
      <p className="agent-summary">关注 {watchedSymbols} 个自选标的、{positions} 个持仓</p>
      <div className="agent-details">
        <div><span>上次检查</span><strong>{lastCheck}</strong></div>
        <div><span>当前规则</span><strong>{String(rules?.version ?? "v1")}</strong></div>
      </div>
      {activeTasks.length > 0 ? <div className="agent-tasks"><span>进行中的研究</span>{activeTasks.slice(0, 2).map((task) => <div key={task.id}><strong>{targetLabel(task)}</strong><span>{statusLabel(task.status)}</span></div>)}</div> : <div className="agent-next"><span>下一步</span><strong>{schedulerEnabled ? "等待市场变化或收盘调度" : "去数据页开启调度"}</strong></div>}
    </div>
  </section>;
}

function JournalView({ items, summary, patterns, onSaveCandidate, onReviewCandidate, onFeedbackCandidate, onOpenTask }: {
  items: JournalItem[];
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
    return symbolMatch && intentMatch;
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
      <Panel title="决策时间线" eyebrow={`${visibleItems.length} 条记录`}>
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
                  <strong>{record.subject.symbol ?? (record.subject.symbols.join(", ") || "未命名标的")}</strong>
                  <span className={`decision-pill decision-${String(record.intent).toLowerCase()}`}>{statusLabel(record.intent)}</span>
                </div>
                <p>{record.next_action ? nextActionLabel(record.next_action) : "没有记录下一步动作。"}</p>
                <div className="journal-meta">
                  <span>规则 {String(record.rule_snapshot_id ?? "—")}</span>
                  <span>依据 {item.evidence_summary.count}</span>
                  {latestOutcome && <span>结果 {String(latestOutcome.outcome_status ?? latestOutcome.outcome.status ?? "未知")}</span>}
                </div>
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
                <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} aria-label="Memory title" />
                <textarea value={editContent} onChange={(event) => setEditContent(event.target.value)} aria-label="Memory content" rows={3} />
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
}: {
  notifications: NotificationRow[];
  onRead: (notification: NotificationRow) => void;
  onEnablePush: () => void;
  pushStatus: string;
  onOpenTask: (taskId: string) => void;
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
        <div className="notification-mark">{notification.read_at ? <CheckIcon size={16} aria-hidden="true" /> : <WarningCircleIcon size={16} aria-hidden="true" />}</div>
        <div className="notification-copy">
          <div className="notification-heading"><strong>{notification.title}</strong><time>{formatDate(notification.created_at)}</time></div>
          <p>{notification.body}</p>
          <span>{notification.event_type}{notification.task_id ? ` · ${notification.task_id}` : ""}</span>
        </div>
        <div className="notification-actions">
          {notification.task_id && <button className="quiet-button" onClick={() => onOpenTask(notification.task_id as string)}>查看研究</button>}
          {!notification.read_at && <button className="quiet-button" onClick={() => onRead(notification)}>标为已读</button>}
        </div>
      </article>)}</div>}
  </section>;
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
  return <div className="task-groups" role="listbox" aria-label="Research tasks" tabIndex={0} onKeyDown={handleKeyDown}>{TASK_GROUPS.map((group) => {
    const grouped = tasks.filter((task) => group.statuses.includes(task.status));
    if (!grouped.length) return null;
    return <section className="task-group" key={group.key}>
      <div className="task-group-heading"><span>{group.label}</span><strong>{grouped.length}</strong></div>
      {grouped.map((task) => <button id={`task-${task.id}`} role="option" aria-selected={selectedId === task.id} key={task.id} className={`queue-row ${selectedId === task.id ? "selected" : ""}`} onClick={() => onOpen(task.id)}>
        <div className="queue-row-top"><StatusBadge status={task.status} /><time>{formatDate(task.created_at)}</time></div>
        <strong>{task.trigger_type === "MarketClose" ? "收盘市场复盘" : task.trigger_type === "StockResearch" && task.target.symbol ? `${String(task.target.symbol)} 研究` : task.trigger_type}</strong>
        <span>{String(task.target.as_of ?? "Local fixture")} · {task.id.slice(-6)}</span>
      </button>)}
    </section>;
  })}</div>;
}

function WatchlistView({ watchlists, candidates, onSaved, onResearch }: {
  watchlists: Watchlist[];
  candidates: Array<Record<string, unknown>>;
  onSaved: (name: string, symbols: string[]) => void;
  onResearch: (symbol: string) => void;
}) {
  const [name, setName] = useState("Research watchlist");
  const [symbols, setSymbols] = useState("");
  const [status, setStatus] = useState("");
  const save = () => {
    const values = symbols.split(/[,\s]+/).map((value) => value.trim().toUpperCase()).filter(Boolean);
    if (!values.length) {
      setStatus("至少添加一个标的");
      return;
    }
    onSaved(name, values);
    setSymbols("");
    setStatus("自选列表已保存");
  };
  return <section className="control-grid">
    <Panel title="自选列表" eyebrow="按用户保存的标的">
      <div className="form-row">
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="自选列表名称" />
        <input value={symbols} onChange={(event) => setSymbols(event.target.value)} placeholder="600000.SH, 510300.SH" />
        <button className="primary-button" onClick={save}>保存</button>
      </div>
      <span className="form-hint">{status || "自选列表会按用户分别保存。"}</span>
      {watchlists.length === 0 ? <EmptyState message="还没有关注列表。" /> :
        <div className="watchlist-list">{watchlists.map((watchlist) => <article className="watchlist-row" key={watchlist.id}>
          <div><strong>{watchlist.name}</strong><span>{watchlist.symbols.length} 个标的</span></div>
          <div className="watchlist-symbols">{watchlist.symbols.map((symbol) => <button className="quiet-button" key={symbol} onClick={() => onResearch(symbol)}>{symbol}</button>)}</div>
        </article>)}</div>}
    </Panel>
    <Panel title="候选快捷操作" eyebrow="从排序扫描结果添加">
      {candidates.length === 0 ? <EmptyState message="暂无候选。" /> :
        <div className="data-table">{candidates.slice(0, 12).map((candidate) => <div className="data-row" key={String(candidate.symbol)}>
          <strong>{String(candidate.symbol)}</strong><span>{String(candidate.name)}</span><button className="quiet-button" onClick={() => {
            const existing = watchlists.find((watchlist) => watchlist.name === name)?.symbols ?? [];
            onSaved(name, [String(candidate.symbol), ...existing]);
          }}>加入</button>
        </div>)}</div>}
    </Panel>
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
      label: row.agent_name,
      value: Math.max(1, finished - started),
      display: `${Math.max(1, finished - started)} ms`,
      tone: row.status === "FAILED" ? "negative" as const : row.status === "RUNNING" ? "positive" as const : "neutral" as const,
    };
  });
  return <ChartFrame title="Agent 时间线" unit="耗时" asOf={asOf} source={source}>
    <HorizontalBars items={durations} empty="还没有 Agent 过程记录" />
  </ChartFrame>;
}

function MarketView({ market, candidates, onResearch, onWatch }: { market: Record<string, unknown> | null; candidates: Array<Record<string, unknown>>; onResearch: (symbol: string) => void; onWatch: (symbol: string) => void }) {
  const [strategies, setStrategies] = useState<Array<{ strategy_id: string; version: string }>>([]);
  const [strategy, setStrategy] = useState("legacy_momentum_v1@1.0.0");
  const [scan, setScan] = useState<{ candidates: Array<Record<string, unknown>>; scan_id?: string; excluded?: Array<Record<string, unknown>> } | null>(null);
  const [scanBusy, setScanBusy] = useState(false);
  const [scanError, setScanError] = useState("");
  useEffect(() => { void api.screeningStrategies().then((result) => setStrategies(result.strategies)).catch(() => setScanError("策略暂不可用")); }, []);
  const executeScan = async (replay = false) => {
    setScanBusy(true);
    try {
      const [id, version] = strategy.split("@");
      const result = replay && scan?.scan_id ? await api.replayCandidateScan(scan.scan_id)
        : await api.createCandidateScan(String(market?.as_of ?? "2026-11-05"), id, version);
      setScan(result);
      setScanError("");
    } catch (error) { setScanError(friendlyError(error, "扫描失败")); }
    finally { setScanBusy(false); }
  };
  const displayedCandidates = scan?.candidates ?? candidates;
  if (!market || market.status === "unavailable") return <section className="single-panel panel"><EmptyState message="还没有市场快照。先运行一次收盘复盘。" /></section>;
  const sectors = (market.sectors as Array<{ name: string; change_pct: number; breadth: number }> | undefined) ?? [];
  const indices = (market.indices as Array<{ name: string; close: number; change_pct: number }> | undefined) ?? [];
  return <section className="control-grid">
    <Panel title="市场快照" eyebrow={`截至 ${String(market.as_of)}`} wide>
      <div className="snapshot-head">
        <div><strong className="big-number">{Math.round(Number(market.breadth) * 100)}%</strong><span>市场宽度</span></div>
        <div><strong className="big-number">{localizedLabel(trendLabels, market.index_trend)}</strong><span>指数趋势</span></div>
        <div><strong className="big-number">{rulePercent(market.volatility)}</strong><span>波动率</span></div>
        <div><strong className="big-number">{market.source === "fixture" ? "回放数据" : String(market.source)}</strong><span>数据来源</span></div>
      </div>
    </Panel>
    <div className="wide"><MarketCharts market={market} indices={indices} /></div>
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
    <Panel title="候选扫描" eyebrow="可回放的排序">
      <div className="scan-controls">
        <label>策略 <select value={strategy} onChange={(event) => setStrategy(event.target.value)}>
          {(strategies.length ? strategies : [{ strategy_id: "legacy_momentum_v1", version: "1.0.0" }]).map((item) =>
            <option key={`${item.strategy_id}@${item.version}`} value={`${item.strategy_id}@${item.version}`}>{item.strategy_id} · {item.version}</option>)}
        </select></label>
        <button className="quiet-button" onClick={() => void executeScan()} disabled={scanBusy}><MagnifyingGlassIcon size={16} />扫描</button>
        {scan?.scan_id && <button className="quiet-button" onClick={() => void executeScan(true)} disabled={scanBusy}><ArrowCounterClockwiseIcon size={16} />复算</button>}
      </div>
      {scanError && <p role="status">{scanError}</p>}
      <div className="data-table">{displayedCandidates.map((candidate) => <div className="data-row candidate-row" key={String(candidate.symbol)}>
        <strong>{String(candidate.symbol)}</strong>
        <span>{String(candidate.name)} · score {Number(candidate.score).toFixed(2)}</span>
        <button className="quiet-button" onClick={() => onWatch(String(candidate.symbol))}>加入观察</button>
        <button className="quiet-button" onClick={() => onResearch(String(candidate.symbol))}>开始研究</button>
        <details className="candidate-factors"><summary>评分依据</summary>
          {Array.isArray(candidate.factors) && candidate.factors.map((factor) => <p key={String(factor.id)}>
            {String(factor.id)} · {Number(factor.value).toLocaleString(undefined, { maximumFractionDigits: 6 })} × {Number(factor.weight).toLocaleString(undefined, { maximumFractionDigits: 6 })} = {Number(factor.contribution).toLocaleString(undefined, { maximumFractionDigits: 6 })}
          </p>)}
          <small>{String(candidate.snapshot_id)} · {String(candidate.quality ?? "unknown")}</small>
          {Array.isArray(candidate.warnings) && candidate.warnings.map((warning) => <p key={String(warning)}>{String(warning)}</p>)}
        </details>
      </div>)}</div>
      {scan?.excluded && scan.excluded.length > 0 && <details><summary>已排除 {scan.excluded.length} 个标的</summary>
        {scan.excluded.map((item) => <p key={String(item.symbol)}>{String(item.symbol)} · {Array.isArray(item.reason_codes) ? item.reason_codes.join(" · ") : ""}</p>)}
      </details>}
    </Panel>
  </section>;
}

function PortfolioView({ portfolio, demoDate, onImported }: { portfolio: Record<string, unknown> | null; demoDate?: string; onImported: () => void }) {
  const [format, setFormat] = useState<"csv" | "xlsx" | "manual">("csv");
  const [asOf, setAsOf] = useState(shanghaiDate);
  const [content, setContent] = useState<string | { encoding: "base64"; data: string }>("");
  const [fileName, setFileName] = useState("");
  const [status, setStatus] = useState("");
  const [importing, setImporting] = useState(false);
  const positions = (portfolio?.positions as Array<Record<string, unknown>> | undefined) ?? [];
  const totalValue = typeof portfolio?.total_value === "number" ? portfolio.total_value.toLocaleString() : "—";
  const drawdown = typeof portfolio?.drawdown === "number" ? rulePercent(portfolio.drawdown) : "—";
  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setFileName(file.name);
    if (format === "xlsx" || file.name.toLowerCase().endsWith(".xlsx")) {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      const chunkSize = 0x8000;
      for (let index = 0; index < bytes.length; index += chunkSize) {
        binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
      }
      setFormat("xlsx");
      setContent({ encoding: "base64", data: btoa(binary) });
      setStatus(`已读取 ${file.name}`);
      return;
    }
    setFormat("csv");
    setContent(await file.text());
    setStatus(`已读取 ${file.name}`);
  };
  const importPortfolio = async () => {
    setImporting(true);
    try {
      const result = await api.importPortfolio(format, content, asOf);
      setStatus(result.portfolio.as_of === asOf
        ? `已导入 ${asOf} 的持仓快照`
        : `服务返回的持仓日期为 ${String(result.portfolio.as_of ?? "未知")}，请核对日期和服务版本。`);
      onImported();
    } catch (error) {
      setStatus(friendlyError(error, "导入失败，请检查持仓文件和日期"));
    } finally {
      setImporting(false);
    }
  };
  return <section className="control-grid portfolio-grid">
    <Panel title="持仓快照" eyebrow={String(portfolio?.as_of ?? "暂无快照")}>
      <div className="snapshot-head compact"><div><strong className="big-number">{totalValue}</strong><span>总市值</span></div><div><strong className="big-number">{drawdown}</strong><span>回撤</span></div></div>
      <div className="data-table">{positions.map((position) => <div className="data-row" key={String(position.symbol)}><strong>{String(position.symbol)}</strong><span>{String(position.sector)}</span><span>{(Number(position.weight) * 100).toFixed(1)}%</span></div>)}</div>
    </Panel>
    <div className="portfolio-charts"><PortfolioCharts portfolio={portfolio} positions={positions} /></div>
    <Panel title="导入持仓" eyebrow="CSV、Excel 或手工 JSON" wide>
      <div className="form-row">
        <label htmlFor="portfolio-as-of">持仓日期</label>
        <input id="portfolio-as-of" type="date" value={asOf} max={shanghaiDate()} onChange={(event) => setAsOf(event.target.value)} />
        {demoDate && <button className="quiet-button" onClick={() => setAsOf(demoDate)}>填入演示日期</button>}
        <select aria-label="持仓格式" value={format} onChange={(event) => { setFormat(event.target.value as typeof format); setContent(""); }}><option value="csv">CSV</option><option value="xlsx">Excel (.xlsx)</option><option value="manual">手工 JSON</option></select>
        <input type="file" aria-label="持仓文件" accept=".csv,.xlsx" onChange={(event) => void handleFile(event.target.files?.[0])} />
        <button className="primary-button" onClick={() => void importPortfolio()} disabled={importing || !asOf || !content}>导入</button>
      </div>
      <textarea className="import-area" aria-label="持仓内容" placeholder={format === "csv" ? "symbol,quantity,avg_cost,market_value,sector,asset_type" : undefined} value={typeof content === "string" ? content : `[${fileName || "Excel 文件"}已加载]`} onChange={(event) => setContent(event.target.value)} readOnly={typeof content !== "string"} />
      <span className="form-hint" role="status">{status || "填写持仓实际对应的日期。"}{demoDate && ` 演示行情日期为 ${demoDate}，请使用对应日期的测试持仓。`}</span>
    </Panel>
  </section>;
}

function ProfileView({ profile, onSaved, localCredentials = false }: { profile: Record<string, unknown> | null; onSaved: () => void; localCredentials?: boolean }) {
  const [objective, setObjective] = useState("capital preservation with disciplined growth");
  const [riskTolerance, setRiskTolerance] = useState("moderate");
  const [drawdownLimit, setDrawdownLimit] = useState("0.15");
  const [assetTypes, setAssetTypes] = useState<string[]>(["stock", "etf"]);
  const [universe, setUniverse] = useState<string[]>(["main", "chinext", "star", "bse", "etf"]);
  const [status, setStatus] = useState("");
  useEffect(() => {
    const payload = (profile?.payload ?? {}) as Record<string, unknown>;
    setObjective(String(payload.investment_objective ?? "capital preservation with disciplined growth"));
    setRiskTolerance(String(payload.risk_tolerance ?? "moderate"));
    setDrawdownLimit(String(payload.drawdown_limit ?? "0.15"));
    setAssetTypes(Array.isArray(payload.allowed_asset_types) ? payload.allowed_asset_types.map(String) : ["stock", "etf"]);
    setUniverse(Array.isArray(payload.universe) ? payload.universe.map(String) : ["main", "chinext", "star", "bse", "etf"]);
  }, [profile]);
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
        investment_objective: objective,
        risk_tolerance: riskTolerance,
        drawdown_limit: parsedDrawdown,
        allowed_asset_types: assetTypes,
        universe,
      });
      setStatus("投资设置已保存");
      onSaved();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "保存失败，请检查设置");
    }
  };
  return <section className="control-grid">
    <Panel title="投资设置" eyebrow={`版本 ${String(profile?.version ?? "—")}`}>
      <div className="profile-form">
        <label><span>你希望 Pia 如何帮助你</span><textarea value={objective} onChange={(event) => setObjective(event.target.value)} placeholder="例如：稳健增值，优先控制回撤" /></label>
        <label><span>风险偏好</span><select value={riskTolerance} onChange={(event) => setRiskTolerance(event.target.value)}><option value="conservative">保守</option><option value="moderate">稳健</option><option value="aggressive">积极</option></select></label>
        <label><span>你能接受的最大回撤</span><div className="input-with-suffix"><input value={drawdownLimit} onChange={(event) => setDrawdownLimit(event.target.value)} inputMode="decimal" /><em>小数，例如 0.15 = 15%</em></div></label>
        <fieldset><legend>允许研究的资产</legend><div className="choice-grid">{[["stock", "股票"], ["etf", "ETF"]].map(([value, label]) => <button type="button" aria-pressed={assetTypes.includes(value)} className={`choice-chip ${assetTypes.includes(value) ? "selected" : ""}`} key={value} onClick={() => setAssetTypes(toggleValue(assetTypes, value))}><span><CheckIcon size={16} aria-hidden="true" /></span>{label}</button>)}</div></fieldset>
        <fieldset><legend>股票范围</legend><div className="choice-grid">{[["main", "沪深主板"], ["chinext", "创业板"], ["star", "科创板"], ["bse", "北交所"], ["etf", "ETF"]].map(([value, label]) => <button type="button" aria-pressed={universe.includes(value)} className={`choice-chip ${universe.includes(value) ? "selected" : ""}`} key={value} onClick={() => setUniverse(toggleValue(universe, value))}><span><CheckIcon size={16} aria-hidden="true" /></span>{label}</button>)}</div></fieldset>
      </div>
      <div className="form-row"><button className="primary-button" onClick={() => void save()}>保存设置</button><span className="form-hint">{status || "设置会保存为新版本，只影响之后的研究。"}</span></div>
    </Panel>
    {localCredentials && <>
      <CredentialSettings kind="tushare" onSaved={onSaved} />
      <CredentialSettings kind="deepseek" onSaved={onSaved} />
    </>}
    <Panel title="研究上下文" eyebrow="当前快照">
      <div className="rationale"><span>✓</span><p>你的风险偏好、目标、资产范围和股票范围会参与每次研究的风险审核。</p></div>
      <div className="rationale"><span>✓</span><p>Pia 只给研究建议，不会替你提交真实订单。</p></div>
    </Panel>
  </section>;
}

const localCredentialSettings = {
  deepseek: {
    title: "DeepSeek", subtitle: "Local 模型凭据", id: "deepseek-api-key", label: "API Key", secretName: "Key",
    environment: "DEEPSEEK_API_KEY", placeholder: "sk-...", read: api.deepseekCredential,
    save: api.saveDeepseekCredential, clear: api.clearDeepseekCredential,
  },
  tushare: {
    title: "Tushare", subtitle: "Local 行情数据", id: "tushare-token", label: "Token", secretName: "Token",
    environment: "TUSHARE_TOKEN", placeholder: "输入 Tushare Token", read: api.tushareCredential,
    save: api.saveTushareCredential, clear: api.clearTushareCredential,
  },
};

function CredentialSettings({ kind, onSaved }: { kind: keyof typeof localCredentialSettings; onSaved: () => void }) {
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
    settings.read().then((value) => {
      if (!cancelled) setCredential(value);
    }).catch(() => {
      if (!cancelled) setError("无法读取凭据状态，请重试。");
    }).finally(() => {
      if (!cancelled) setPending(false);
    });
    return () => { cancelled = true; };
  }, [reload, settings]);

  const update = async (clear: boolean) => {
    setPending(true);
    setError("");
    setMessage("");
    try {
      const next = await (clear ? settings.clear() : settings.save(draft.trim()));
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

function DataHealthView({ health, syncResult, onSyncResult }: {
  health: { status: string; runtime: string; provider: { status: string; provider_id?: string }; llm: { model: string; credentials_configured: boolean }; scheduler?: { enabled: boolean; timezone: string; close_time: string; last_dispatched_date: string | null } } | null;
  syncResult: Record<string, unknown> | null;
  onSyncResult: (result: Record<string, unknown>) => void;
}) {
  const [status, setStatus] = useState("");
  const sync = async () => {
    try {
      const date = health?.provider.provider_id === "fixture" ? REPLAY_AS_OF : shanghaiDate();
      const result = await api.syncData(date, ["600000.SH", "510300.SH"]);
      onSyncResult(result as Record<string, unknown>);
      const attempts = result.provider_attempts;
      const tushareDaily = Array.isArray(attempts) ? attempts.filter((attempt) =>
        attempt.capability === "daily_bars" && attempt.provider_id === "tushare") : [];
      const summary = result.market_snapshot_quality === "verified" ? `已同步 ${date} 的市场数据。` : `${date} 的行情快照未通过质量检查。`;
      const dailyStatus = tushareDaily.some((attempt) => attempt.outcome === "success") ? " 已收到 Tushare 股票日线。"
        : tushareDaily.length ? " Tushare 股票日线请求失败，请核对 Token 权限和行情入库时间。" : "";
      setStatus(summary + dailyStatus);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "市场数据同步失败");
    }
  };
  const toggleScheduler = async () => {
    try {
      if (health?.scheduler?.enabled) await api.stopScheduler();
      else await api.startScheduler();
      setStatus("调度状态已更新");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "调度状态更新失败");
    }
  };
  const marketQuality = (syncResult?.market_quality as Record<string, unknown> | undefined) ?? {};
  const completeness = Number(marketQuality.field_completeness ?? 0);
  const failures = Array.isArray(syncResult?.failures) ? syncResult.failures.length : 0;
  return <section className="control-grid"><Panel title="运行时" eyebrow={health?.runtime === "cloud" ? "云端执行环境" : health?.runtime === "local" ? "本地执行环境" : "执行环境"}><div className="health-list"><div><span>状态</span><strong>{localizedLabel(healthLabels, health?.status, "未知")}</strong></div><div><span>模式</span><strong>{localizedLabel(healthLabels, health?.runtime, "未知")}</strong></div><div><span>数据源</span><strong>{localizedLabel(healthLabels, health?.provider.status, "未知")}</strong></div><div><span>模型</span><strong>{health?.llm.model ?? "deepseek-flash"} · {health?.llm.credentials_configured ? "已配置" : "需要凭据"}</strong></div></div></Panel><Panel title="调度与数据" eyebrow="数据源同步控制"><div className="health-list"><div><span>调度</span><strong>{health?.scheduler?.enabled ? "运行中" : "已停止"}</strong></div><div><span>收盘时间</span><strong>{health?.scheduler?.close_time ?? "15:05"}</strong></div><div><span>时区</span><strong>{health?.scheduler?.timezone ?? "Asia/Shanghai"}</strong></div><div><span>最近质量</span><strong>{localizedLabel(qualityLabels, syncResult?.quality, "尚未同步")}</strong></div><div><span>字段完整度</span><strong>{syncResult ? `${(completeness * 100).toFixed(1)}%` : "—"}</strong></div><div><span>失败数</span><strong>{syncResult ? failures : "—"}</strong></div></div><div className="form-row"><button className="quiet-button" onClick={() => void toggleScheduler()}>{health?.scheduler?.enabled ? "停止调度" : "开启调度"}</button><button className="primary-button" onClick={() => void sync()}>同步市场数据</button></div><span className="form-hint">{status || "实时同步会记录原始载荷、标准化数据和质量状态。"}</span></Panel><Panel title="数据质量约定" eyebrow="快照检查"><div className="rationale"><span>✓</span><p>每个快照都会保存 as_of、observed_at、source 和 quality。</p></div><div className="rationale"><span>✓</span><p>未来时间或无效时间戳会被降级并显示为失败。</p></div><div className="rationale"><span>✓</span><p>过期或不可用的数据会阻止受影响的研究。</p></div></Panel></section>;
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
  AGENT_STARTED: "Agent 开始分析",
  AGENT_COMPLETED: "Agent 完成分析",
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

function ResearchDetail({ detail, busy, rawData, onApprove, onControl, onCancel, onRetry, onTakeover, onExport, onReplay, onRawData, onCopyLink, onCopyEvidenceLink, onRetrospective }: { detail: TaskDetail; busy: boolean; rawData: TaskDataResponse | null; onApprove: (action: "APPROVE" | "REJECT" | "NO_ACTION" | "REQUEST_MORE_RESEARCH" | "MARK_AS_WATCH") => void; onControl: (action: "pause" | "resume") => void; onCancel: () => void; onRetry: () => void; onTakeover: () => void; onExport: () => void; onReplay: () => void; onRawData: () => void; onCopyLink: () => void; onCopyEvidenceLink: (evidenceId: string) => void; onRetrospective: (payload: { action_taken: string; outcome: Record<string, unknown>; notes?: string; observed_at?: string | null }) => void }) {
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
  const portfolioDate = detail.evidence.find((item) => item.source_type === "portfolio")?.as_of;
  const marketDate = detail.evidence.find((item) => item.source_type === "market")?.as_of;
  const usesDemoMarket = detail.evidence.some((item) => item.source_type === "market" && (item.source === "fixture" || item.provider_id === "fixture"));
  const taskTitle = detail.task.trigger_type === "MarketClose" ? "收盘市场复盘" : symbol ? `${symbol} 研究` : detail.task.trigger_type;
  const [evidenceQuery, setEvidenceQuery] = useState("");
  const [evidenceQualityFilter, setEvidenceQualityFilter] = useState("all");
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
        <StatusBadge status={detail.task.status} />
        <button className="icon-button" title="复制链接" aria-label="复制链接" onClick={onCopyLink} disabled={busy}><LinkSimpleIcon size={16} aria-hidden="true" /></button>
        <button className="icon-button" title="原始数据" aria-label="原始数据" onClick={onRawData} disabled={busy}><DatabaseIcon size={16} aria-hidden="true" /></button>
        <button className="icon-button" title="回放研究" aria-label="回放研究" onClick={onReplay} disabled={busy}><ArrowCounterClockwiseIcon size={16} aria-hidden="true" /></button>
        <button className="icon-button" title="导出上下文" aria-label="导出上下文" onClick={onExport} disabled={busy}><ExportIcon size={16} aria-hidden="true" /></button>
        {detail.task.status === "QUEUED" && <button className="danger-button" onClick={onCancel} disabled={busy}>取消</button>}
        {["PLANNING", "RUNNING", "REVIEWING"].includes(detail.task.status) && <><button className="quiet-button" onClick={() => onControl("pause")} disabled={busy}>暂停</button><button className="danger-button" onClick={onCancel} disabled={busy}>取消</button></>}
        {detail.task.status === "PAUSED" && <><button className="primary-button" onClick={() => onControl("resume")} disabled={busy}>继续</button><button className="danger-button" onClick={onCancel} disabled={busy}>取消</button></>}
        {["RETRYABLE", "FAILED", "TIMEOUT"].includes(detail.task.status) && <><button className="quiet-button" onClick={onTakeover} disabled={busy}>接管研究</button><button className="primary-button" onClick={onRetry} disabled={busy}>重试</button></>}
      </div>
    </div>
    <div className="decision-strip">
      <div><span className="eyebrow">研究结论</span><strong className={`decision-${(decision?.status ?? "PENDING").toLowerCase()}`}>{statusLabel(decision?.status ?? "PENDING")}</strong>
        {firstBlocker && <p className="decision-reason">{ruleReasonLabel(firstBlocker)} · {ruleComparison(firstBlocker)}{(rules?.reasons.length ?? 0) > 1 && <> · <a href="#research-rules">查看全部 {rules?.reasons.length} 项</a></>}</p>}
        <span>{detail.task.error?.code === "PORTFOLIO_AS_OF_UNAVAILABLE" ? `没有 ${dataDate} 或更早的持仓快照。请导入对应日期的持仓，再重试。` : decision?.next_action ? `下一步：${nextActionLabel(decision.next_action)}` : "当前尚无研究结论"}</span></div>
      <div className="decision-meta"><span>信心 <b>{localizedLabel(levelLabels, decision?.confidence)}</b></span><span>风险 <b>{localizedLabel(levelLabels, decision?.risk_level)}</b></span>{marketDate && <span>{usesDemoMarket ? "演示行情" : "行情日期"} <b>{marketDate}</b></span>}{portfolioDate && <span>持仓日期 <b>{portfolioDate}</b></span>}</div>
    </div>
    <div className="result-summary" role="status">
      <strong>结果：{["QUEUED", "PLANNING", "RUNNING", "REVIEWING", "PAUSED"].includes(detail.task.status) ? "处理中" : ({ complete: "完整", partial: "部分结果", none: "无可用结果", unknown: "历史完整性未知" })[detail.result_metadata?.completion ?? "unknown"]}</strong>
      <span> · 数据 {localizedLabel(qualityLabels, detail.result_metadata?.quality_summary, "未知")} · {canApprove ? "可确认建议" : needsReview ? "待处理 · 仅供研究" : "仅供研究"}</span>
      {needsReview && <div className="review-jump">
        <a className="quiet-button" href="#research-approval" onClick={() => document.getElementById("research-approval")?.focus()}>查看处理选项</a>
      </div>}
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
          {processItems.map((item) => <p key={item}>{item}</p>)}
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
      source={String(detail.task.data_snapshot_id ?? "task snapshot")}
    />
    <Panel title="研究过程" eyebrow={`${detail.trace.length} 次运行`} wide>
      <span id="research-trace" />
      <div className="trace-list">{detail.trace.map((trace) => <TraceRowView key={trace.id ?? trace.agent_name} trace={trace} toolCalls={(detail.tool_calls ?? []).filter((call) => call.agent_run_id === trace.id)} />)}</div>
      {detail.llm_usage && detail.llm_usage.records > 0 && <div className="trace-usage">
        <span>模型用量</span>
        <strong>{detail.llm_usage.total_tokens.toLocaleString()} tokens</strong>
        <small>{detail.llm_usage.request_count} 次请求 · ${detail.llm_usage.cost_usd.toFixed(4)}</small>
      </div>}
      {detail.llm_ledger && <p className="form-hint">费用 ${detail.llm_ledger.known_cost_usd} · 保守占用 ${detail.llm_ledger.conservative_reserved_usd} · {detail.llm_ledger.unknown_count} 次费用未知 · 日预算按 UTC 结算</p>}
    </Panel>
    {rawData && <TaskDataPanel data={rawData} />}
    <RetrospectivePanel retrospectives={detail.retrospectives ?? []} busy={busy} onSubmit={onRetrospective} />
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

function RetrospectivePanel({ retrospectives, busy, onSubmit }: {
  retrospectives: TaskDetail["retrospectives"];
  busy: boolean;
  onSubmit: (payload: { action_taken: string; outcome: Record<string, unknown>; notes?: string; observed_at?: string | null }) => void;
}) {
  const [action, setAction] = useState("NOT_TAKEN");
  const [horizon, setHorizon] = useState("USER_RECORDED");
  const [outcomeStatus, setOutcomeStatus] = useState("observed");
  const [returnPct, setReturnPct] = useState("");
  const [benchmarkReturnPct, setBenchmarkReturnPct] = useState("");
  const [marketRegime, setMarketRegime] = useState("");
  const [positionSizePct, setPositionSizePct] = useState("");
  const [notes, setNotes] = useState("");
  const submit = () => {
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
    onSubmit({
      action_taken: action,
      outcome,
      notes: notes.trim(),
      observed_at: new Date().toISOString(),
    });
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
      <button className="primary-button" onClick={submit} disabled={busy}>保存复盘</button>
    </div>
    <span className="form-hint">每次保存都会追加一条观察记录；收益和基准收益只描述结果，不代表决策正确。</span>
    {retrospectives.length === 0 ? <EmptyState message="还没有实际操作或结果记录。" /> :
      <div className="retrospective-list">{retrospectives.map((item) => <article className="retrospective-row" key={item.id}>
        <div><strong>{String(item.outcome.horizon ?? "USER_RECORDED")}</strong><span>{formatDate(item.observed_at)}</span></div>
        <p>{({ NOT_TAKEN: "未采取行动", APPROVE: "采纳建议", REJECT: "拒绝建议", NO_ACTION: "暂不行动", OTHER: "其他行动" } as Record<string, string>)[item.action_taken] ?? item.action_taken} · {({ observed: "已观察", positive: "正向", negative: "负向", mixed: "混合", unknown: "未知" } as Record<string, string>)[String(item.outcome.status ?? "observed")] ?? String(item.outcome.status ?? "observed")}{item.outcome.return_pct !== undefined ? ` · 收益 ${String(item.outcome.return_pct)}%` : ""}{item.outcome.benchmark_return_pct !== undefined ? ` · 基准 ${String(item.outcome.benchmark_return_pct)}%` : ""}{item.outcome.excess_return_pct !== undefined ? ` · 超额 ${String(item.outcome.excess_return_pct)}%` : ""}</p>
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
    return <article className="debate-case" key={agent}><strong>{agent}</strong><span>{String(output.stance ?? output.verdict ?? "")}</span>{points.map((point) => <p key={String(point)}>• {String(point)}</p>)}{unresolved.map((question) => <small key={String(question)}>待回答：{String(question)}</small>)}</article>;
  })}</div>;
}

function Panel({ title, eyebrow, wide, children }: { title: string; eyebrow: string; wide?: boolean; children: ReactNode }) {
  return <section className={`sub-panel ${wide ? "wide" : ""}`}><div className="panel-header"><div><span className="eyebrow">{eyebrow}</span><h3>{title}</h3></div></div>{children}</section>;
}

const ruleReasonLabels: Record<string, string> = {
  STALE_DATA: "行情快照已过期",
  DATA_UNAVAILABLE: "行情快照未通过验证",
  MARKET_VOLATILITY_FAILED: "市场波动率超过阈值",
  RISK_REVIEW_FAILED: "组合回撤触及严重阈值",
  DRAWDOWN_LIMIT: "组合回撤触及限制",
  DRAWDOWN_WARNING: "组合回撤触及预警阈值",
  EVIDENCE_INSUFFICIENT: "证据条数未达到最低要求",
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
  const labels = { ...qualityLabels, ...trendLabels };
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
  const usedBy = evidence.used_by?.length ? evidence.used_by.join(" · ") : "尚未关联研究过程";
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
    <summary className="trace-row"><CaretRightIcon className="trace-chevron" size={16} aria-hidden="true" /><div><strong>{trace.agent_name}</strong><span>{formatDate(trace.started_at)}</span></div><StatusBadge status={trace.status} /><small>{trace.finished_at ? `${Math.max(1, Math.round((new Date(trace.finished_at).getTime() - new Date(trace.started_at).getTime())))} ms` : "—"}{trace.token_usage ? ` · ${trace.token_usage} tokens` : ""}</small></summary>
    <div className="trace-expanded">
      <div><span className="eyebrow">工具调用</span><strong>{toolCalls.length}</strong></div>
      {toolCalls.map((call) => <div className="trace-tool" key={String(call.id)}><strong>{String(call.tool_name)}</strong><StatusBadge status={String(call.status ?? "DONE")} /></div>)}
      {trace.output_json && <pre>{trace.output_json}</pre>}
    </div>
  </details>;
}
