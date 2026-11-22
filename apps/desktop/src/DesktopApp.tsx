import { useEffect, useRef, useState } from "react";
import { CloudIcon, DesktopIcon, XIcon } from "@phosphor-icons/react";
import { PiaApiClient } from "../../../packages/contracts/generated/typescript/client";
import { App } from "./App";
import { api } from "./api";
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

async function startLocalRuntime(channel?: DesktopChannel) {
  let endpoint: DesktopEndpoint | undefined;
  if (channel) {
    const { invoke } = await import("@tauri-apps/api/core");
    endpoint = await invoke<DesktopEndpoint>("ensure_local_runtime");
    if (endpoint.channel !== channel) throw new Error("本地运行时与当前窗口不匹配，已停止连接。");
  }
  const baseUrl = endpoint?.base_url ?? LOCAL_API;
  const token = channel ? undefined : LOCAL_TOKEN;
  const client = new PiaApiClient({ baseUrl, token,
    fetcher: (input, init) => fetch(input, { ...init, signal: AbortSignal.timeout(1500) }),
  });
  await waitForLocalRuntime(() => client.health(), endpoint);
  return { baseUrl, token };
}

function connectionError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  if (/unauthorized|401/i.test(message)) return "访问令牌无效或已过期，请重新输入。";
  if (/fetch|network|timeout|aborted/i.test(message)) return "无法连接运行环境，请检查服务地址和网络后重试。";
  return /\p{Script=Han}/u.test(message) ? message : "连接运行环境失败，请检查服务后重试。";
}

export function DesktopApp({ channel }: { channel?: DesktopChannel } = {}) {
  const [connection] = useState<RuntimeConnection>(() =>
    readConnection(window.localStorage, LOCAL_ONLY, channel) ?? { mode: "local", cloudUrl: "" });
  const [choosing, setChoosing] = useState(false);
  const [ready, setReady] = useState(false);
  const [cloudUrl, setCloudUrl] = useState(connection.cloudUrl);
  const [token, setToken] = useState(() => readCloudToken(window.sessionStorage, connection.cloudUrl, channel) ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startupError, setStartupError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    let cancelled = false;
    const boot = async () => {
      try {
        const { baseUrl, token } = connection.mode === "local" ? await startLocalRuntime(channel) : {
          baseUrl: connection.cloudUrl,
          token: readCloudToken(window.sessionStorage, connection.cloudUrl, channel),
        };
        if (cancelled) return;
        api.configure(baseUrl, token);
        setReady(true);
      } catch (error) {
        if (!cancelled) setStartupError(connectionError(error));
      }
    };
    void boot();
    return () => { cancelled = true; };
  }, [channel, connection]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (choosing) dialog?.showModal();
    else dialog?.close();
  }, [choosing]);

  const connect = async (mode: RuntimeConnection["mode"]) => {
    setPending(true);
    setError(null);
    setStartupError(null);
    try {
      const next: RuntimeConnection = {
        mode,
        cloudUrl: mode === "cloud" ? normalizeCloudUrl(cloudUrl) : connection.cloudUrl,
      };
      if (mode === "local") {
        await startLocalRuntime(channel);
      } else {
        const client = new PiaApiClient({
          baseUrl: next.cloudUrl,
          token: token.trim(),
          fetcher: (input, init) => fetch(input, { ...init, signal: AbortSignal.timeout(10000) }),
        });
        const health = await client.health();
        if (health.runtime !== "cloud") throw new Error("请填写云端运行时的 API 地址。");
        await client.tasks();
        saveCloudToken(window.sessionStorage, next.cloudUrl, token, channel);
      }
      if (!LOCAL_ONLY) saveConnection(window.localStorage, next, channel);
      // Reload also disposes in-flight requests and subscriptions from the previous workspace.
      window.location.reload();
    } catch (error) {
      if (mode === "cloud") setError(connectionError(error));
      else setStartupError(connectionError(error));
      setPending(false);
    }
  };

  return <>
    <App runtimeReady={ready} runtimeMode={connection.mode} runtimeControl={<div className="runtime-control">
      <span className="eyebrow">{channel === "debug" ? "开发版 · Debug" : channel === "release" ? "正式版" : "运行环境"}</span>
      <div className="runtime-options" role="group" aria-label="运行环境">
        <button type="button" aria-pressed={connection.mode === "local"} disabled={pending} onClick={() => {
          if (connection.mode !== "local" || !ready) void connect("local");
        }}><DesktopIcon size={16} aria-hidden="true" />本地</button>
        {!LOCAL_ONLY && <button type="button" aria-pressed={connection.mode === "cloud"} disabled={pending} onClick={() => {
          setError(null);
          setCloudUrl(connection.cloudUrl);
          setToken(readCloudToken(window.sessionStorage, connection.cloudUrl, channel) ?? "");
          setChoosing(true);
        }}><CloudIcon size={16} aria-hidden="true" />云端</button>}
      </div>
      {startupError ? <p className="runtime-error" role="alert">{startupError}</p> : !ready ? <p className="runtime-starting" role="status">正在连接{connection.mode === "local" ? "本地" : "云端"}…</p> : null}
    </div>} />
    {!LOCAL_ONLY && <dialog ref={dialogRef} className="runtime-dialog" aria-labelledby="runtime-dialog-title" onCancel={(event) => {
      if (pending) event.preventDefault();
      else setChoosing(false);
    }} onClose={() => setChoosing(false)}>
      <form onSubmit={(event) => { event.preventDefault(); void connect("cloud"); }}>
        <div className="runtime-dialog-heading">
          <h2 id="runtime-dialog-title"><CloudIcon size={18} aria-hidden="true" />云端连接</h2>
          <button type="button" className="icon-button" aria-label="关闭云端配置" title="关闭" disabled={pending} onClick={() => setChoosing(false)}><XIcon size={16} aria-hidden="true" /></button>
        </div>
        <div className="runtime-fields">
          <label htmlFor="cloud-url">云端 API 地址</label>
          <input id="cloud-url" type="url" required placeholder="https://pia.example.com/api" value={cloudUrl} disabled={pending} onChange={(event) => { setCloudUrl(event.target.value); setToken(""); }} autoComplete="url" spellCheck={false} />
          <label htmlFor="cloud-token">访问令牌</label>
          <input id="cloud-token" type="password" required value={token} disabled={pending} onChange={(event) => setToken(event.target.value)} autoComplete="off" />
        </div>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <div className="runtime-dialog-actions">
          <button type="button" className="quiet-button" disabled={pending} onClick={() => setChoosing(false)}>取消</button>
          <button className="primary-button" disabled={pending || !cloudUrl.trim() || !token.trim()}>{pending ? "正在连接…" : "连接云端"}</button>
        </div>
      </form>
    </dialog>}
  </>;
}
