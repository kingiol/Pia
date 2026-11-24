export type RuntimeConnection = {
  mode: "local" | "cloud";
  cloudUrl: string;
};

export type DesktopChannel = "debug" | "release";

export type DesktopEndpoint = {
  base_url: string;
  channel: DesktopChannel;
  instance_id: string;
};

const CONNECTION_KEY = "pia.desktop.runtime.v1";
const SESSION_KEY = "pia.desktop.cloud_session.v1";

type LocalHealth = { runtime: string; desktop_runtime?: unknown };

export async function waitForLocalRuntime<T extends LocalHealth>(readHealth: () => Promise<T>, expected?: DesktopEndpoint, signal?: AbortSignal): Promise<T> {
  // Packaged sidecars need time to extract their Python runtime on a cold launch.
  const deadline = Date.now() + 60000;
  while (true) {
    signal?.throwIfAborted();
    let health: T;
    try {
      health = await readHealth();
    } catch {
      signal?.throwIfAborted();
      if (Date.now() >= deadline) throw new Error("无法启动本地运行时，请检查本地服务后重试。");
      await new Promise((resolve) => setTimeout(resolve, 250));
      continue;
    }
    signal?.throwIfAborted();
    if (health.runtime !== "local") throw new Error("本地 API 返回了云端模式，请检查本地端口配置。");
    const identity = health.desktop_runtime as { channel?: unknown; instance_id?: unknown } | undefined;
    if (expected && (identity?.channel !== expected.channel || identity?.instance_id !== expected.instance_id)) {
      throw new Error("本地运行时与当前窗口不匹配，已停止连接。");
    }
    return health;
  }
}

export function normalizeCloudUrl(value: string): string {
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new Error("请输入有效的云端 API 地址。");
  }
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) {
    throw new Error("云端地址需要使用 HTTPS；本机调试可使用 HTTP。");
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("API 地址不能包含凭据、查询参数或片段。");
  }
  const path = url.pathname.replace(/\/+$/, "");
  url.pathname = path.endsWith("/api") ? path : `${path}/api`;
  return url.toString().replace(/\/$/, "");
}

function scopedKey(key: string, channel?: DesktopChannel) {
  return channel === "debug" ? `${key}.debug` : key;
}

export function readConnection(storage: Pick<Storage, "getItem">, localOnly = false, channel?: DesktopChannel): RuntimeConnection | null {
  if (localOnly) return { mode: "local", cloudUrl: "" };
  try {
    const value = JSON.parse(storage.getItem(scopedKey(CONNECTION_KEY, channel)) ?? "null");
    if (value?.mode !== "local" && value?.mode !== "cloud") return null;
    return {
      mode: value.mode,
      cloudUrl: value.cloudUrl ? normalizeCloudUrl(value.cloudUrl) : "",
    };
  } catch {
    return null;
  }
}

export function readCloudToken(storage: Pick<Storage, "getItem">, cloudUrl: string, channel?: DesktopChannel): string | undefined {
  try {
    const session = JSON.parse(storage.getItem(scopedKey(SESSION_KEY, channel)) ?? "null");
    return session?.cloudUrl === cloudUrl && typeof session.token === "string"
      ? session.token.trim() || undefined
      : undefined;
  } catch {
    return undefined;
  }
}

export function saveCloudToken(storage: Pick<Storage, "setItem">, cloudUrl: string, token: string, channel?: DesktopChannel) {
  storage.setItem(scopedKey(SESSION_KEY, channel), JSON.stringify({ cloudUrl, token: token.trim() }));
}

export function saveConnection(storage: Pick<Storage, "setItem">, connection: RuntimeConnection, channel?: DesktopChannel) {
  storage.setItem(scopedKey(CONNECTION_KEY, channel), JSON.stringify({
    mode: connection.mode,
    cloudUrl: connection.cloudUrl,
  }));
}
