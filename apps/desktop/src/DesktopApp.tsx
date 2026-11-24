import { useCallback, useEffect, useRef, useState } from "react";
import { CloudIcon, DesktopIcon, XIcon } from "@phosphor-icons/react";
import { PiaApiClient } from "../../../packages/contracts/generated/typescript/client";
import { App, type WorkspaceView } from "./App";
import { createWorkspaceApi, WorkspaceApiContext, type WorkspaceHealth } from "./api";
import {
  normalizeCloudUrl,
  readCloudToken,
  readConnection,
  saveCloudToken,
  saveConnection,
  waitForLocalRuntime,
  type DesktopChannel,
  type DesktopEndpoint,
  type RuntimeConnection,
} from "./runtimeConnection";

const LOCAL_API = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765/api";
const LOCAL_TOKEN = import.meta.env.VITE_API_TOKEN as string | undefined;
const LOCAL_ONLY = import.meta.env.VITE_DESKTOP_LOCAL_ONLY === "1";
const disconnectedApi = createWorkspaceApi("");

function startupClient(baseUrl: string, token: string | undefined, signal: AbortSignal, timeout: number) {
  return new PiaApiClient({ baseUrl, token, fetcher: (input, init) => {
    signal.throwIfAborted();
    const deadline = AbortSignal.timeout(timeout);
    return fetch(input, { ...init, signal: AbortSignal.any?.([signal, deadline]) ?? deadline });
  } });
}

async function startLocalRuntime(channel: DesktopChannel | undefined, signal: AbortSignal) {
  let endpoint: DesktopEndpoint | undefined;
  if (channel) {
    const { invoke } = await import("@tauri-apps/api/core");
    signal.throwIfAborted();
    endpoint = await invoke<DesktopEndpoint>("ensure_local_runtime");
    if (endpoint.channel !== channel) throw new Error("本地运行时与当前窗口不匹配，已停止连接。");
  }
  const baseUrl = endpoint?.base_url ?? LOCAL_API;
  const token = channel ? undefined : LOCAL_TOKEN;
  const client = startupClient(baseUrl, token, signal, 1500);
  const health = await waitForLocalRuntime(() => client.health(), endpoint, signal);
  return { baseUrl, token, health: health as WorkspaceHealth };
}

async function startCloudRuntime(baseUrl: string, token: string | undefined, signal: AbortSignal) {
  if (!token) throw new Error("请输入云端访问令牌。");
  const client = startupClient(baseUrl, token, signal, 10000);
  const health = await client.health();
  if (health.runtime !== "cloud") throw new Error("请填写云端运行时的 API 地址。");
  // Health is public. Verify the token without loading the research queue.
  await client.scheduler();
  return { baseUrl, token, health: health as WorkspaceHealth };
}

function connectionError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  if (/unauthorized|401/i.test(message)) return "访问令牌无效或已过期，请重新输入。";
  if (/fetch|network|timeout|aborted/i.test(message)) return "无法连接运行环境，请检查服务地址和网络后重试。";
  return /\p{Script=Han}/u.test(message) ? message : "连接运行环境失败，请检查服务后重试。";
}

type ConnectionAttempt = { id: number; connection: RuntimeConnection; cloudToken?: string };
type ConnectionResult = { id: number } & (
  { api: ReturnType<typeof createWorkspaceApi>; health: WorkspaceHealth } | { error: string }
);

export function DesktopApp({ channel }: { channel?: DesktopChannel } = {}) {
  const [attempt, setAttempt] = useState<ConnectionAttempt>(() => {
    const connection = readConnection(window.localStorage, LOCAL_ONLY, channel) ?? { mode: "local", cloudUrl: "" };
    return { id: 0, connection, cloudToken: readCloudToken(window.sessionStorage, connection.cloudUrl, channel) };
  });
  const [result, setResult] = useState<ConnectionResult>();
  const [view, setView] = useState<WorkspaceView>();
  const [choosing, setChoosing] = useState(false);
  const [cloudUrl, setCloudUrl] = useState(attempt.connection.cloudUrl);
  const [token, setToken] = useState(attempt.cloudToken ?? "");
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const runtimeOptionsRef = useRef<HTMLDivElement>(null);
  const currentAttempt = useRef(0);
  const currentConnection = useRef<AbortController | null>(null);
  const { connection, cloudToken } = attempt;
  const ready = result?.id === attempt.id && "api" in result ? result : undefined;
  const startupError = result?.id === attempt.id && "error" in result ? result.error : undefined;

  useEffect(() => {
    const controller = new AbortController();
    currentConnection.current = controller;
    const { signal } = controller;
    const active = () => !signal.aborted && currentAttempt.current === attempt.id;
    const boot = async () => {
      try {
        const target = connection.mode === "local"
          ? await startLocalRuntime(channel, signal)
          : await startCloudRuntime(connection.cloudUrl, cloudToken, signal);
        if (!active()) return;
        if (!LOCAL_ONLY && attempt.id > 0) {
          if (connection.mode === "cloud" && cloudToken) {
            saveCloudToken(window.sessionStorage, connection.cloudUrl, cloudToken, channel);
          }
          saveConnection(window.localStorage, connection, channel);
        }
        setResult({ id: attempt.id, api: createWorkspaceApi(target.baseUrl, target.token, signal), health: target.health });
      } catch (error) {
        if (active()) setResult({ id: attempt.id, error: connectionError(error) });
      }
    };
    void boot();
    return () => controller.abort();
  }, [attempt, channel, cloudToken, connection]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (choosing) dialog?.showModal();
    else dialog?.close();
  }, [choosing]);

  useEffect(() => {
    if (attempt.id > 0) runtimeOptionsRef.current?.querySelector<HTMLButtonElement>("[aria-pressed='true']")?.focus();
  }, [attempt.id]);

  const switchWorkspace = (next: RuntimeConnection, nextCloudToken?: string) => {
    const id = ++currentAttempt.current;
    currentConnection.current?.abort();
    setChoosing(false);
    setAttempt({ id, connection: next, cloudToken: nextCloudToken });
  };

  const selectLocal = () => {
    if (connection.mode === "local" && !startupError) return;
    const savedUrl = readConnection(window.localStorage, LOCAL_ONLY, channel)?.cloudUrl ?? "";
    switchWorkspace({ mode: "local", cloudUrl: savedUrl }, readCloudToken(window.sessionStorage, savedUrl, channel));
  };

  const editCloud = () => {
    setError(null);
    setCloudUrl(connection.cloudUrl);
    setToken(cloudToken ?? "");
    setChoosing(true);
  };

  const selectCloud = () => {
    if (connection.mode === "local" && connection.cloudUrl && cloudToken) {
      switchWorkspace({ ...connection, mode: "cloud" }, cloudToken);
    } else {
      editCloud();
    }
  };

  const submitCloud = () => {
    try {
      switchWorkspace({ mode: "cloud", cloudUrl: normalizeCloudUrl(cloudUrl) }, token.trim());
    } catch (error) {
      setError(connectionError(error));
    }
  };

  const updateView = useCallback((next: WorkspaceView) => {
    if (currentAttempt.current === attempt.id) setView(next);
  }, [attempt.id]);

  return <>
    <WorkspaceApiContext.Provider value={ready?.api ?? disconnectedApi}>
      <App key={attempt.id} workspaceView={view} onWorkspaceViewChange={updateView}
      runtimeReady={Boolean(ready)} runtimeHealth={ready?.health} runtimeMode={connection.mode}
      runtimeError={startupError} onRuntimeRetry={connection.mode === "cloud" ? editCloud : selectLocal}
      runtimeControl={<div className="runtime-control">
        {channel !== "release" && <span className="eyebrow">{channel === "debug" ? "开发版 · Debug" : "运行环境"}</span>}
        <div ref={runtimeOptionsRef} className="runtime-options" role="group" aria-label="运行环境">
          <button type="button" aria-pressed={connection.mode === "local"} onClick={selectLocal}><DesktopIcon size={16} aria-hidden="true" />本地</button>
          {!LOCAL_ONLY && <button type="button" aria-pressed={connection.mode === "cloud"} onClick={selectCloud}><CloudIcon size={16} aria-hidden="true" />云端</button>}
        </div>
      </div>} />
    </WorkspaceApiContext.Provider>
    {!LOCAL_ONLY && <dialog ref={dialogRef} className="runtime-dialog" aria-labelledby="runtime-dialog-title"
      onCancel={() => setChoosing(false)} onClose={() => setChoosing(false)}>
      <form onSubmit={(event) => { event.preventDefault(); submitCloud(); }}>
        <div className="runtime-dialog-heading">
          <h2 id="runtime-dialog-title"><CloudIcon size={18} aria-hidden="true" />云端连接</h2>
          <button type="button" className="icon-button" aria-label="关闭云端配置" title="关闭" onClick={() => setChoosing(false)}><XIcon size={16} aria-hidden="true" /></button>
        </div>
        <div className="runtime-fields">
          <label htmlFor="cloud-url">云端 API 地址</label>
          <input id="cloud-url" type="url" required placeholder="https://pia.example.com/api"
            value={cloudUrl} onChange={(event) => { setCloudUrl(event.target.value); setToken(""); }} />
          <label htmlFor="cloud-token">访问令牌</label>
          <input id="cloud-token" type="password" required placeholder="输入访问令牌" autoComplete="off" spellCheck={false}
            value={token} onChange={(event) => setToken(event.target.value)} />
        </div>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <div className="runtime-dialog-actions">
          <button type="button" className="quiet-button" onClick={() => setChoosing(false)}>取消</button>
          <button className="primary-button" disabled={!cloudUrl.trim() || !token.trim()}>连接云端</button>
        </div>
      </form>
    </dialog>}
  </>;
}
