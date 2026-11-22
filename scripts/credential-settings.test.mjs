import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

test("renders investment defaults and Local credential settings without workspace health data", async () => {
  const server = await createServer({
    configFile: "apps/desktop/vite.config.ts",
    server: { middlewareMode: true, hmr: false },
  });
  const previousWindow = globalThis.window;
  try {
    const { App } = await server.ssrLoadModule("/src/App.tsx");
    globalThis.window = { location: { pathname: "/profile", search: "" } };
    const render = (props) => renderToStaticMarkup(createElement(App, props));
    const profileMarkup = render({});
    assert.match(profileMarkup, /<textarea[^>]*>稳健增值，优先控制回撤<\/textarea>/);
    assert.doesNotMatch(profileMarkup, /capital preservation with disciplined growth/);
    assert.match(render({ runtimeMode: "local" }), /id="deepseek-api-key"/);
    assert.doesNotMatch(render({ runtimeMode: "cloud" }), /id="deepseek-api-key"/);
    assert.doesNotMatch(profileMarkup, /id="deepseek-api-key"/);
    assert.doesNotMatch(render({ runtimeMode: "local", runtimeReady: false }), /id="deepseek-api-key"/);
    assert.match(render({ runtimeMode: "local" }), /id="tushare-token" type="password"/);
    assert.doesNotMatch(render({ runtimeMode: "cloud" }), /id="tushare-token"/);
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
    await server.close();
  }
});
