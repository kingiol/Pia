import { createContext, useContext } from "react";
import { PiaApiClient } from "../../../packages/contracts/generated/typescript/client";
export type { CandidateListResponse, LocalCredentialStatus } from "../../../packages/contracts/generated/typescript/client";
import type { DeviceRegistration } from "../../../packages/contracts/generated/typescript/models";
import type { ResultMetadata } from "../../../packages/contracts/generated/typescript/models";
import type {
  MemoryCandidate,
  DataSyncResponse,
  OrderPreviewResponse,
  OrderRequest,
  PaperOrderResponse,
  SchedulerResponse,
} from "../../../packages/contracts/generated/typescript/client";
export type { SchedulerResponse };

export const marketSyncStages = [
  "market_snapshot", "trading_calendar", "universe", "daily_bars", "fundamentals", "news", "filing",
] as const;
export type MarketSyncStage = (typeof marketSyncStages)[number];
export type MarketSyncProgress = {
  stage: string;
  status?: "running" | "validating" | "done" | "reused" | "partial" | "failed" | "skipped";
  symbol?: string | null;
  current?: number;
  total?: number;
  fetched?: number;
  reused?: number;
  failed?: number;
  saved_rows?: number;
  reason?: string;
};

export type TaskStatus =
  | "QUEUED"
  | "PLANNING"
  | "RUNNING"
  | "REVIEWING"
  | "PAUSED"
  | "WAITING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "BLOCKED"
  | "NO_ACTION"
  | "RETRYABLE"
  | "FAILED"
  | "TIMEOUT"
  | "CANCELLED"
  | "EXPIRED"
  | "DONE";

export type Task = {
  id: string;
  trigger_type: string;
  target: Record<string, unknown>;
  status: TaskStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  data_snapshot_id?: string | null;
  rule_snapshot_id?: string | null;
  error?: { code: string; message: string } | null;
  result_metadata?: ResultMetadata;
};

export type TaskDetail = {
  task: Task;
  result_metadata?: ResultMetadata;
  llm_ledger?: { known_cost_usd: string; conservative_reserved_usd: string; unknown_count: number; day_boundary: string };
  decision: {
    status: string;
    confidence: string;
    risk_level: string;
    next_action: string;
    rationale: { items: string[]; rules: RuleResult };
    invalidation: string[];
  } | null;
  evidence: Evidence[];
  trace: TraceRow[];
  approvals: Array<Record<string, string>>;
  retrospectives: Retrospective[];
  events: Array<{ event_type: string; payload: Record<string, unknown>; created_at: string }>;
  llm_usage?: {
    records: number;
    request_count: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
  };
  tool_calls?: Array<Record<string, unknown>>;
  debate?: Record<string, Record<string, unknown>>;
};

export type TaskDataResponse = {
  task_id: string;
  snapshot_ids: string[];
  bundles: Array<{
    snapshot: Record<string, unknown>;
    raw_payloads: Array<Record<string, unknown>>;
  }>;
};

export type Watchlist = {
  id: string;
  user_id: string;
  name: string;
  symbols: string[];
  created_at: string;
  updated_at: string;
};

export type Retrospective = {
  id: string;
  task_id: string;
  user_id: string;
  action_taken: string;
  outcome: Record<string, unknown>;
  notes: string;
  observed_at: string;
  rule_snapshot_id?: string | null;
  data_snapshot_id?: string | null;
  created_at: string;
};

export type JournalItem = {
  decision_record: {
    task: Task;
    subject: {
      symbol?: string | null;
      symbols: string[];
      target: Record<string, unknown>;
    };
    intent: string;
    rationale?: { items?: string[]; rules?: RuleResult } | null;
    confidence?: string;
    risk_level?: string;
    next_action?: string;
    created_at: string;
    rule_snapshot_id?: string | null;
    data_snapshot_id?: string | null;
  };
  retrospectives: Array<Retrospective & { outcome_status?: string }>;
  evidence_summary: {
    count: number;
    qualities: string[];
    latest_as_of?: string | null;
    ids: string[];
  };
  approvals: Array<Record<string, unknown>>;
  replay_refs: Record<string, unknown>;
};

export type JournalResponse = {
  items: JournalItem[];
  next_cursor: string | null;
};

export type JournalSummary = {
  decision_count: number;
  retrospective_count: number;
  intent_counts: Record<string, number>;
  action_counts: Record<string, number>;
  outcome_status_counts: Record<string, number>;
  comparable_outcome_count: number;
  average_return_pct?: number | null;
  rule_snapshot_counts: Record<string, number>;
  warnings: string[];
};

export type JournalPatterns = {
  intent_patterns: Array<Record<string, unknown>>;
  rule_patterns: Array<Record<string, unknown>>;
  memory_candidates: Array<Record<string, unknown>>;
  warnings: string[];
};

export type MemoryCandidateReviewAction = "CONFIRM" | "EDIT_AND_CONFIRM" | "REJECT" | "ARCHIVE";

export type Evidence = {
  id: string;
  source: string;
  provider_id?: string | null;
  source_type: string;
  source_uri?: string | null;
  title: string;
  observed_at: string;
  as_of: string;
  expires_at: string;
  quality: string;
  excerpt: string;
  snapshot_id: string;
  used_by?: string[];
};

export type RuleReason = {
  code: string;
  severity: string;
  actual: unknown;
  expected: unknown;
  message: string;
};

export type RuleResult = {
  decision: string;
  reasons: RuleReason[];
  warnings: RuleReason[];
  rule_snapshot_id: string;
};

export type TraceRow = {
  id?: string;
  agent_name: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  input_json?: string | null;
  output_json?: string | null;
  token_usage?: number | null;
};

export type TaskInput = {
  asOf: string;
  symbol?: string;
  marketSnapshotId?: string;
  fixture?: { market?: string; portfolio?: string };
};

export type MarketWorkspace = Record<string, unknown> & {
  snapshot_id?: string;
  as_of?: string;
  observed_at?: string;
  source?: string;
  provider_id?: string;
  quality?: string;
  instruments?: Array<{ symbol?: string; name?: string }>;
  review_session?: { as_of: string; calendar_verified: boolean };
  last_verified?: { as_of: string; observed_at: string; source: string };
};

function normalizeTaskDetail(value: Partial<TaskDetail>): TaskDetail {
  return {
    ...value,
    task: value.task as Task,
    decision: value.decision ?? null,
    evidence: Array.isArray(value.evidence) ? value.evidence : [],
    trace: Array.isArray(value.trace) ? value.trace : [],
    approvals: Array.isArray(value.approvals) ? value.approvals : [],
    retrospectives: Array.isArray(value.retrospectives) ? value.retrospectives : [],
    events: Array.isArray(value.events) ? value.events : [],
    tool_calls: Array.isArray(value.tool_calls) ? value.tool_calls : [],
    debate: value.debate ?? {},
  } as TaskDetail;
}

export function createWorkspaceApi(url: string, token?: string, signal?: AbortSignal) {
  const baseUrl = url.replace(/\/$/, "");
  const fetcher: typeof fetch = async (input, init) => {
    if (!baseUrl) throw new Error("桌面运行时尚未连接。");
    signal?.throwIfAborted();
    return fetch(input, signal ? { ...init, signal } : init);
  };
  const contractClient = new PiaApiClient({ baseUrl, token, fetcher });

  return {
    setToken: (token?: string) => contractClient.setToken(token),
    getToken: () => contractClient.getToken(),
    deepseekCredential: () => contractClient.deepseekCredential(),
    saveDeepseekCredential: (apiKey: string) => contractClient.saveDeepseekCredential(apiKey),
    clearDeepseekCredential: () => contractClient.clearDeepseekCredential(),
    tushareCredential: () => contractClient.tushareCredential(),
    saveTushareCredential: (token: string) => contractClient.saveTushareCredential(token),
    clearTushareCredential: () => contractClient.clearTushareCredential(),
    health: () => contractClient.health() as Promise<{
      status: string;
      runtime: string;
      provider: { status: string; provider_id?: string };
      llm: { model: string; credentials_configured: boolean };
      scheduler?: SchedulerResponse;
    }>,
    providers: () => contractClient.providers(),
    scheduler: () => contractClient.scheduler(),
    syncData: async (
      asOf: string, symbols: string[], onProgress: (progress: MarketSyncProgress) => void,
      refreshStage?: MarketSyncStage,
    ): Promise<DataSyncResponse> => {
      const token = contractClient.getToken();
      const response = await fetcher(`${baseUrl}/data/sync`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/x-ndjson",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          as_of: asOf, symbols, include_default_symbols: false, refresh_stage: refreshStage,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      if (!response.headers.get("Content-Type")?.includes("application/x-ndjson")) return response.json();
      if (!response.body) throw new Error("未收到同步结果。");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) throw new Error("同步连接中断，请刷新行情状态后重试。");
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            const frame = JSON.parse(line) as { progress?: MarketSyncProgress; result?: DataSyncResponse; error?: string };
            if (frame.error) throw new Error(line);
            if (frame.result) return frame.result;
            if (frame.progress) onProgress(frame.progress);
          }
        }
      } finally {
        await reader.cancel().catch(() => undefined);
      }
    },
    previewOrder: (order: OrderRequest) =>
      contractClient.previewOrder(order) as Promise<OrderPreviewResponse>,
    paperOrder: (order: OrderRequest) =>
      contractClient.paperOrder(order) as Promise<PaperOrderResponse>,
    startScheduler: () => contractClient.startScheduler(),
    stopScheduler: () => contractClient.stopScheduler(),
    tasks: () => contractClient.tasks() as Promise<{ tasks: Task[] }>,
    task: async (id: string) => normalizeTaskDetail(await contractClient.task(id) as Partial<TaskDetail>),
    taskContext: (id: string) => contractClient.taskContext(id),
    exportTask: (id: string) => contractClient.exportTaskText(id),
    screeningStrategies: () => contractClient.screeningStrategies(),
    createCandidateScan: (asOf: string, id?: string, version?: string, fixture?: string) =>
      contractClient.createCandidateScan(asOf, id, version, fixture),
    replayCandidateScan: (id: string) => contractClient.replayCandidateScan(id),
    taskFlow: (id: string, afterSeq = 0, limit = 100, snapshotSeq?: number) =>
      contractClient.taskFlow(id, afterSeq, limit, snapshotSeq),
    taskData: (id: string) => contractClient.taskData(id) as Promise<TaskDataResponse>,
    journal: (filters: {
      task_id?: string;
      symbol?: string;
      intent?: string;
      outcome_status?: string;
      rule_snapshot_id?: string;
      from?: string;
      to?: string;
      cursor?: string;
      limit?: number;
    } = {}) => contractClient.journal(filters) as Promise<JournalResponse>,
    journalSummary: (filters: {
      symbol?: string;
      intent?: string;
      outcome_status?: string;
      rule_snapshot_id?: string;
      from?: string;
      to?: string;
    } = {}) => contractClient.journalSummary(filters) as Promise<JournalSummary>,
    journalPatterns: (filters: {
      symbol?: string;
      intent?: string;
      outcome_status?: string;
      rule_snapshot_id?: string;
      from?: string;
      to?: string;
    } = {}) => contractClient.journalPatterns(filters) as Promise<JournalPatterns>,
    materializeJournalMemoryCandidate: (candidateKey: string) =>
      contractClient.materializeJournalMemoryCandidate(candidateKey) as Promise<MemoryCandidate>,
    reviewJournalMemoryCandidate: (
      candidateId: string,
      payload: {
        action: MemoryCandidateReviewAction;
        title?: string | null;
        content?: string | null;
        notes?: string;
      },
    ) => contractClient.reviewJournalMemoryCandidate(candidateId, payload),
    memoryCandidateUsage: (candidateId: string) =>
      contractClient.memoryCandidateUsage(candidateId),
    memoryCandidateFeedback: (
      candidateId: string,
      payload: {
        rating: "HELPFUL" | "NOT_HELPFUL" | "UNCERTAIN";
        usage_id?: string | null;
        notes?: string;
      },
    ) => contractClient.memoryCandidateFeedback(candidateId, payload),
    rules: () => contractClient.rules(),
    updateRules: (rules: Record<string, unknown>) => contractClient.updateRules(rules),
    portfolio: () => contractClient.portfolioSnapshot(),
    market: () => contractClient.market() as Promise<MarketWorkspace>,
    candidates: (asOf: string, fixture?: string) => contractClient.candidates(asOf, fixture),
    audit: () => contractClient.audit() as Promise<{ audit: Array<Record<string, string>> }>,
    notifications: () => contractClient.notifications(),
    watchlists: () => contractClient.watchlists(),
    saveWatchlist: (name: string, symbols: string[], append?: boolean) =>
      contractClient.saveWatchlist(name, symbols, append),
    searchMemory: (query = "", symbol?: string, limit = 50) =>
      contractClient.searchMemory(query, symbol, limit),
    saveMemory: (payload: {
      kind?: string;
      symbol?: string | null;
      title: string;
      content: string;
      source?: string;
      as_of?: string | null;
      observed_at?: string | null;
      quality?: string;
    }) => contractClient.saveMemory(payload),
    notificationDeliveries: (id: string) => contractClient.notificationDeliveries(id),
    registerDevice: (device: DeviceRegistration) =>
      contractClient.registerDevice(device),
    markNotificationRead: (id: string) =>
      contractClient.markNotificationRead(id) as Promise<{ status: string; notification_id: string }>,
    profile: () => contractClient.profile() as Promise<Record<string, unknown>>,
    updateProfile: (payload: Record<string, unknown>) =>
      contractClient.updateProfile(payload as never) as Promise<Record<string, unknown>>,
    importPortfolio: (
      format: "csv" | "xlsx" | "manual",
      content: string | Array<Record<string, unknown>> | { encoding: "base64"; data: string },
      asOf?: string,
    ) =>
      contractClient.importPortfolio(format, content, asOf) as Promise<{ portfolio: Record<string, unknown> }>,
    savePortfolioPosition: (payload: Parameters<typeof contractClient.savePortfolioPosition>[0]) =>
      contractClient.savePortfolioPosition(payload),
    createTask: (input: TaskInput) => {
      const target: Record<string, unknown> = {
        as_of: input.asOf,
      };
      if (input.marketSnapshotId) target._market_snapshot_id = input.marketSnapshotId;
      return contractClient.createTask({
        trigger_type: "MarketClose",
        target,
        ...(input.fixture ? { fixture: input.fixture } : {}),
      }) as Promise<{ task: Task }>;
    },
    createResearchTask: (symbol: string, input: TaskInput) => {
      const target: Record<string, unknown> = {
        as_of: input.asOf,
        symbol,
      };
      if (input.marketSnapshotId) target._market_snapshot_id = input.marketSnapshotId;
      return contractClient.createTask({
        trigger_type: "StockResearch",
        target,
        ...(input.fixture ? { fixture: input.fixture } : {}),
      }) as Promise<{ task: Task }>;
    },
    approve: (
      id: string,
      action: "APPROVE" | "REJECT" | "NO_ACTION" | "REQUEST_MORE_RESEARCH" | "MARK_AS_WATCH",
    ) =>
      contractClient.approve(id, action, "Reviewed in Pia Workspace").then((detail) => normalizeTaskDetail(detail as Partial<TaskDetail>)),
    pause: (id: string) => contractClient.pause(id) as Promise<{ task: Task }>,
    resume: (id: string) => contractClient.resume(id) as Promise<{ task: Task }>,
    retry: (id: string) => contractClient.retry(id) as Promise<{ task: Task }>,
    replay: (id: string) => contractClient.replay(id) as Promise<{ task: Task }>,
    cancel: (id: string, reason?: string) => contractClient.cancel(id, reason) as Promise<{ task: Task }>,
    takeover: (id: string, notes?: string) => contractClient.takeover(id, notes),
    recordRetrospective: (
      id: string,
      payload: {
        action_taken: string;
        outcome: Record<string, unknown>;
        notes?: string;
        observed_at?: string | null;
      },
    ) => contractClient.recordRetrospective(id, payload),
    subscribeTask: (id: string, onEvent: () => void) => {
      if (!baseUrl || signal?.aborted) return () => {};
      const token = contractClient.getToken();
      if (!token) {
        const source = new EventSource(`${baseUrl}/tasks/${id}/events`);
        source.onmessage = onEvent;
        source.addEventListener("TASK_STATUS", onEvent);
        source.onerror = () => source.close();
        return () => source.close();
      }
      const controller = new AbortController();
      void fetch(`${baseUrl}/tasks/${id}/events`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      }).then(async (response) => {
        if (!response.ok || !response.body) return;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!controller.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          frames.forEach((frame) => { if (frame.includes("data: ")) onEvent(); });
        }
      }).catch(() => undefined);
      return () => controller.abort();
    },
  };
}

const defaultApi = createWorkspaceApi(
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window
    ? "" : import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765/api",
  import.meta.env.VITE_API_TOKEN as string | undefined,
);

export type WorkspaceHealth = Awaited<ReturnType<ReturnType<typeof createWorkspaceApi>["health"]>>;
export const WorkspaceApiContext = createContext(defaultApi);
export function useWorkspaceApi() {
  return useContext(WorkspaceApiContext);
}
