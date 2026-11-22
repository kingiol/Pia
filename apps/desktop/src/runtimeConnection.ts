export type RuntimeConnection = {
  mode: "local" | "cloud";
  cloudUrl: string;
};

const CONNECTION_KEY = "pia.desktop.runtime.v1";
const SESSION_KEY = "pia.desktop.cloud_session.v1";

export async function waitForLocalRuntime(readHealth: () => Promise<{ runtime: string }>): Promise<void> {
  // Packaged sidecars need time to extract their Python runtime on a cold launch.
  const deadline = Date.now() + 60000;
  while (true) {
    let health: { runtime: string };
    try {
      health = await readHealth();
    } catch {
      if (Date.now() >= deadline) throw new Error("无法启动本地运行时，请检查本地服务后重试。");
      await new Promise((resolve) => setTimeout(resolve, 250));
      continue;
    }
    if (health.runtime !== "local") throw new Error("本地 API 返回了云端模式，请检查本地端口配置。");
    return;
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

export function readConnection(storage: Pick<Storage, "getItem">, localOnly = false): RuntimeConnection | null {
  if (localOnly) return { mode: "local", cloudUrl: "" };
  try {
    const value = JSON.parse(storage.getItem(CONNECTION_KEY) ?? "null");
    if (value?.mode !== "local" && value?.mode !== "cloud") return null;
    return {
      mode: value.mode,
      cloudUrl: value.cloudUrl ? normalizeCloudUrl(value.cloudUrl) : "",
    };
  } catch {
    return null;
  }
}

export function readCloudToken(storage: Pick<Storage, "getItem">, cloudUrl: string): string | undefined {
  try {
    const session = JSON.parse(storage.getItem(SESSION_KEY) ?? "null");
    return session?.cloudUrl === cloudUrl && typeof session.token === "string"
      ? session.token.trim() || undefined
      : undefined;
  } catch {
    return undefined;
  }
}

export function saveCloudToken(storage: Pick<Storage, "setItem">, cloudUrl: string, token: string) {
  storage.setItem(SESSION_KEY, JSON.stringify({ cloudUrl, token: token.trim() }));
}

export function saveConnection(storage: Pick<Storage, "setItem">, connection: RuntimeConnection) {
  storage.setItem(CONNECTION_KEY, JSON.stringify({
    mode: connection.mode,
    cloudUrl: connection.cloudUrl,
  }));
}
