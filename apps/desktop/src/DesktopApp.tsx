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
  type RuntimeConnection,
} from "./runtimeConnection";

const LOCAL_API = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765/api";
const LOCAL_TOKEN = import.meta.env.VITE_API_TOKEN as string | undefined;
const LOCAL_ONLY = import.meta.env.VITE_DESKTOP_LOCAL_ONLY === "1";

async function startLocalRuntime() {
  if ("__TAURI_INTERNALS__" in window) {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("ensure_local_runtime");
  }
  const client = new PiaApiClient({ baseUrl: LOCAL_API, token: LOCAL_TOKEN,
    fetcher: (input, init) => fetch(input, { ...init, signal: AbortSignal.timeout(1500) }),
  });
  await waitForLocalRuntime(() => client.health());
}

function connectionError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  if (/unauthorized|401/i.test(message)) return "访问令牌无效或已过期，请重新输入。";
  if (/fetch|network|timeout|aborted/i.test(message)) return "无法连接 Cloud，请检查 API 地址和网络后重试。";
  return message;
}

export function DesktopApp() {
  const [connection] = useState<RuntimeConnection>(() =>
    readConnection(window.localStorage, LOCAL_ONLY) ?? { mode: "local", cloudUrl: "" });
  const [choosing, setChoosing] = useState(false);
  const [ready, setReady] = useState(false);
  const [cloudUrl, setCloudUrl] = useState(connection.cloudUrl);
  const [token, setToken] = useState(() => readCloudToken(window.sessionStorage, connection.cloudUrl) ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startupError, setStartupError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    let cancelled = false;
    const boot = async () => {
      const cloudToken = readCloudToken(window.sessionStorage, connection.cloudUrl);
      api.configure(
        connection.mode === "local" ? LOCAL_API : connection.cloudUrl,
        connection.mode === "local" ? LOCAL_TOKEN : cloudToken,
      );
      try {
        if (connection.mode === "local") await startLocalRuntime();
        if (cancelled) return;
        setReady(true);
      } catch (error) {
        if (!cancelled) setStartupError(connectionError(error));
      }
    };
    void boot();
    return () => { cancelled = true; };
  }, [connection]);

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
        await startLocalRuntime();
      } else {
        const client = new PiaApiClient({
          baseUrl: next.cloudUrl,
          token: token.trim(),
          fetcher: (input, init) => fetch(input, { ...init, signal: AbortSignal.timeout(10000) }),
        });
        const health = await client.health();
        if (health.runtime !== "cloud") throw new Error("该地址不是 Cloud 运行时，请检查 API 地址。");
        await client.tasks();
        saveCloudToken(window.sessionStorage, next.cloudUrl, token);
      }
      if (!LOCAL_ONLY) saveConnection(window.localStorage, next);
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
      <span className="eyebrow">运行环境</span>
      <div className="runtime-options" role="group" aria-label="运行环境">
        <button type="button" aria-pressed={connection.mode === "local"} disabled={pending} onClick={() => {
          if (connection.mode !== "local" || !ready) void connect("local");
        }}><DesktopIcon size={16} aria-hidden="true" />Local</button>
        {!LOCAL_ONLY && <button type="button" aria-pressed={connection.mode === "cloud"} disabled={pending} onClick={() => {
          setError(null);
          setCloudUrl(connection.cloudUrl);
          setToken(readCloudToken(window.sessionStorage, connection.cloudUrl) ?? "");
          setChoosing(true);
        }}><CloudIcon size={16} aria-hidden="true" />Cloud</button>}
      </div>
      {startupError ? <p className="runtime-error" role="alert">{startupError}</p> : !ready ? <p className="runtime-starting" role="status">正在连接 {connection.mode === "local" ? "Local" : "Cloud"}…</p> : null}
    </div>} />
    {!LOCAL_ONLY && <dialog ref={dialogRef} className="runtime-dialog" aria-labelledby="runtime-dialog-title" onCancel={(event) => {
      if (pending) event.preventDefault();
      else setChoosing(false);
    }} onClose={() => setChoosing(false)}>
      <form onSubmit={(event) => { event.preventDefault(); void connect("cloud"); }}>
        <div className="runtime-dialog-heading">
          <h2 id="runtime-dialog-title"><CloudIcon size={18} aria-hidden="true" />Cloud 连接</h2>
          <button type="button" className="icon-button" aria-label="关闭 Cloud 配置" title="关闭" disabled={pending} onClick={() => setChoosing(false)}><XIcon size={16} aria-hidden="true" /></button>
        </div>
        <div className="runtime-fields">
          <label htmlFor="cloud-url">Cloud API 地址</label>
          <input id="cloud-url" type="url" required placeholder="https://pia.example.com/api" value={cloudUrl} disabled={pending} onChange={(event) => { setCloudUrl(event.target.value); setToken(""); }} autoComplete="url" spellCheck={false} />
          <label htmlFor="cloud-token">访问令牌</label>
          <input id="cloud-token" type="password" required value={token} disabled={pending} onChange={(event) => setToken(event.target.value)} autoComplete="off" />
        </div>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <div className="runtime-dialog-actions">
          <button type="button" className="quiet-button" disabled={pending} onClick={() => setChoosing(false)}>取消</button>
          <button className="primary-button" disabled={pending || !cloudUrl.trim() || !token.trim()}>{pending ? "正在连接…" : "连接 Cloud"}</button>
        </div>
      </form>
    </dialog>}
  </>;
}
