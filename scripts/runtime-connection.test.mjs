import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import ts from "typescript";

// Transpile the dependency-free module so this check also runs on Node 22.
const source = await readFile(new URL("../apps/desktop/src/runtimeConnection.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { normalizeCloudUrl, readConnection, readCloudToken, saveConnection, saveCloudToken, waitForLocalRuntime } =
  await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

function storage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    values,
  };
}

test("normalizes root and prefixed API URLs without duplicating the API path", () => {
  assert.equal(normalizeCloudUrl(" https://pia.example.com/ "), "https://pia.example.com/api");
  assert.equal(normalizeCloudUrl("https://pia.example.com/pia/api///"), "https://pia.example.com/pia/api");
  assert.equal(normalizeCloudUrl("https://pia.example.com/pia"), "https://pia.example.com/pia/api");
  assert.equal(normalizeCloudUrl("http://127.0.0.1:8877"), "http://127.0.0.1:8877/api");
  assert.equal(normalizeCloudUrl("http://[::1]:8877/api"), "http://[::1]:8877/api");
});

test("rejects unsafe or ambiguous Cloud endpoints", () => {
  for (const value of [
    "", "pia.example.com", "file:///api", "javascript:alert(1)",
    "http://pia.example.com", "https://user:password@pia.example.com",
    "https://pia.example.com?token=secret", "https://pia.example.com#api",
  ]) assert.throws(() => normalizeCloudUrl(value), undefined, value);
});

test("persists the selected mode and URL without persisting credentials", () => {
  const local = storage();
  assert.equal(readConnection(local), null);
  saveConnection(local, { mode: "cloud", cloudUrl: "https://pia.example.com/api", token: "secret" });
  assert.deepEqual(readConnection(local), { mode: "cloud", cloudUrl: "https://pia.example.com/api" });
  assert.ok(![...local.values.values()].join("").includes("secret"));
  saveConnection(local, { mode: "local", cloudUrl: "https://pia.example.com/api" });
  assert.equal(readConnection(local).mode, "local");
});

test("forces Local in local-only mode without overwriting the saved Cloud connection", () => {
  const local = storage();
  const cloud = { mode: "cloud", cloudUrl: "https://pia.example.com/api" };
  saveConnection(local, cloud);
  assert.deepEqual(readConnection(local, true), { mode: "local", cloudUrl: "" });
  assert.deepEqual(readConnection(local), cloud);
});

test("shows only the runtime modes enabled by the desktop debug command", async () => {
  const previousWindow = globalThis.window;
  const previousFlag = process.env.VITE_DESKTOP_LOCAL_ONLY;
  try {
    for (const flag of ["1", "0"]) {
      process.env.VITE_DESKTOP_LOCAL_ONLY = flag;
      const server = await createServer({
        configFile: "apps/desktop/vite.config.ts",
        server: { middlewareMode: true, hmr: false, ws: false },
      });
      try {
        const local = storage();
        saveConnection(local, { mode: "cloud", cloudUrl: "https://pia.example.com/api" });
        globalThis.window = {
          location: { pathname: "/", search: "" },
          localStorage: local,
          sessionStorage: storage(),
        };
        const { DesktopApp } = await server.ssrLoadModule("/src/DesktopApp.tsx");
        const html = renderToStaticMarkup(createElement(DesktopApp));
        if (flag === "1") {
          assert.doesNotMatch(html, /云端<\/button>|id="runtime-dialog-title"/);
          assert.match(html, /aria-pressed="true"[^>]*>.*?本地<\/button>/);
        } else {
          assert.match(html, /云端<\/button>/);
          assert.match(html, /id="runtime-dialog-title"/);
        }
      } finally {
        await server.close();
      }
    }
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
    if (previousFlag === undefined) delete process.env.VITE_DESKTOP_LOCAL_ONLY;
    else process.env.VITE_DESKTOP_LOCAL_ONLY = previousFlag;
  }
});

test("binds session tokens to the exact Cloud endpoint", () => {
  const session = storage();
  saveCloudToken(session, "https://a.example.com/api", " token-a ");
  assert.equal(readCloudToken(session, "https://a.example.com/api"), "token-a");
  assert.equal(readCloudToken(session, "https://b.example.com/api"), undefined);
  assert.equal(readCloudToken(session, "https://a.example.com/other/api"), undefined);
  assert.equal(readCloudToken(storage(), "https://a.example.com/api"), undefined);
});

test("recovers safely from corrupt, invalid, and unavailable storage", () => {
  for (const value of ["{", "null", '{"mode":"auto"}', '{"mode":"cloud","cloudUrl":"file:///api"}']) {
    assert.equal(readConnection({ getItem: () => value }), null);
  }
  const unavailable = { getItem: () => { throw new Error("Storage unavailable"); } };
  assert.equal(readConnection(unavailable), null);
  assert.equal(readCloudToken(unavailable, "https://pia.example.com/api"), undefined);
});

async function withStartupClock(run) {
  let elapsed = 0;
  const originalNow = Date.now;
  const originalTimeout = globalThis.setTimeout;
  Date.now = () => elapsed;
  globalThis.setTimeout = (callback, delay) => {
    elapsed += delay;
    queueMicrotask(callback);
    return 0;
  };
  try {
    await run(() => elapsed);
  } finally {
    Date.now = originalNow;
    globalThis.setTimeout = originalTimeout;
  }
}

test("waits for a packaged sidecar that needs ten seconds to start", async () => {
  await withStartupClock(async (elapsed) => {
    await waitForLocalRuntime(async () => {
      if (elapsed() < 10000) throw new Error("Connection refused");
      return { runtime: "local" };
    });
    assert.equal(elapsed(), 10000);
  });
});

test("stops waiting when local startup reaches its deadline", async () => {
  await withStartupClock(async (elapsed) => {
    await assert.rejects(waitForLocalRuntime(async () => {
      throw new Error("Connection refused");
    }), /无法启动本地运行时/);
    assert.equal(elapsed(), 60000);
  });
});

test("rejects a Cloud runtime at the Local address without retrying", async () => {
  await withStartupClock(async (elapsed) => {
    await assert.rejects(waitForLocalRuntime(async () => ({ runtime: "cloud" })), /云端模式/);
    assert.equal(elapsed(), 0);
  });
});
