#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"

if ! command -v pnpm >/dev/null 2>&1; then
  echo "DESKTOP UI SMOKE FAIL: pnpm is required" >&2
  exit 1
fi

root_tmp="$(mktemp -d)"
api_port="${PIA_UI_SMOKE_API_PORT:-8874}"
web_port="${PIA_UI_SMOKE_WEB_PORT:-5176}"
session="pia-ui-smoke-${$}"
fixtures="$root_tmp/fixtures"
cp -R tests/fixtures "$fixtures"

cleanup() {
  "$PWCLI" --session "$session" close >/dev/null 2>&1 || true
  kill "${vite_pid:-}" "${runtime_pid:-}" 2>/dev/null || true
  wait "${vite_pid:-}" "${runtime_pid:-}" 2>/dev/null || true
  rm -rf "$root_tmp"
}
trap cleanup EXIT

export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export PWCLI="${CODEX_HOME}/skills/playwright/scripts/playwright_cli.sh"

PIA_PORT="$api_port" \
PIA_DB_PATH="$root_tmp/pia.sqlite3" \
PIA_DUCKDB_PATH="$root_tmp/pia.duckdb" \
PIA_FIXTURE_DIR="$fixtures" \
PIA_DATA_PROVIDER=fixture \
PIA_CREDENTIAL_SERVICE="com.pia.ui-smoke" \
PIA_AUTOSTART_TASKS=1 \
  "$PWD/scripts/python.sh" -m pia_runtime.cli serve >"$root_tmp/runtime.log" 2>&1 &
runtime_pid=$!

VITE_API_BASE="http://127.0.0.1:${api_port}/api" \
VITE_DESKTOP_LOCAL_ONLY=1 \
  pnpm exec vite --config apps/desktop/vite.config.ts --host 127.0.0.1 --port "$web_port" >"$root_tmp/vite.log" 2>&1 &
vite_pid=$!

for _ in $(seq 1 40); do
  if curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS \
      "http://127.0.0.1:${api_port}/api/health" >/dev/null 2>&1 &&
     curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS \
      "http://127.0.0.1:${web_port}/" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

cd "$root_tmp"
"$PWCLI" --session "$session" open "http://127.0.0.1:${web_port}/" --browser chrome >/dev/null

read -r -d '' flow <<'JS' || true
async page => {
  const button = name => page.getByRole("button", { name, exact: true });
  const nav = page.getByRole("navigation", { name: "主导航" });
  const stockResearch = page.getByRole("heading", { name: "600000.SH 研究" });
  const search = page.getByRole("searchbox", { name: "搜索名称、代码或研究" });

  await button("体验演示复盘").click();
  const demo = page.getByRole("dialog", { name: "演示复盘" });
  await demo.getByText("查看示例依据").click();
  await demo.getByText(/示例组合总值/).waitFor();
  await demo.getByRole("button", { name: "关闭" }).click();

  await page.route("**/api/profile", route => route.abort());
  await button("刷新").click();
  await page.getByText("部分准备信息暂不可用。").waitFor();
  await page.route("**/api/tasks", route => route.request().method() === "GET" ? route.abort() : route.continue());
  await button("开始演示复盘").click();
  await page.waitForURL("**/research/task_*");
  await page.getByRole("heading", { name: "收盘市场复盘" }).waitFor();
  await page.getByText("研究列表暂不可用。", { exact: false }).waitFor();
  await page.getByText("示例持仓", { exact: false }).first().waitFor();
  await page.getByText(/实际 37.32% · 要求 ≤ 10%/).first().waitFor();
  const reviewId = new URL(page.url()).pathname.split("/").at(-1);
  await page.unroute("**/api/tasks");
  await page.unroute("**/api/profile");

  await button("记录不行动").click();
  const reason = "Position limit exceeded";
  await page.getByLabel("不行动的原因").fill(reason);
  await page.route("**/api/tasks/*/retrospectives", route => route.abort());
  await button("保存不行动记录").click();
  await page.locator(".quick-retrospective").getByRole("alert").waitFor();
  if (await page.getByLabel("不行动的原因").inputValue() !== reason) throw Error("Failed save discarded the draft");
  await page.unroute("**/api/tasks/*/retrospectives");
  await button("保存不行动记录").click();
  await button("查看本次决策日志").click();
  await page.getByRole("heading", { name: "这次研究的记录" }).waitFor();
  await page.getByText(reason, { exact: true }).waitFor();
  if (new URL(page.url()).searchParams.get("journal_task") !== reviewId) throw Error("Incorrect journal target");
  await button("查看研究").click();
  await button("原始数据").click();
  await page.getByText(/回放输入/).first().waitFor();
  await page.reload();
  await page.getByRole("heading", { name: "收盘市场复盘" }).waitFor();
  await page.getByRole("listbox", { name: "研究任务" }).press("ArrowDown");

  await nav.getByRole("button", { name: "数据", exact: true }).click();
  await button("开启调度").click();
  await button("停止调度").click();
  await button("开启调度").waitFor();
  await button("同步市场数据").click();
  await page.getByText("最近一次同步", { exact: true }).waitFor();

  await nav.getByRole("button", { name: "市场", exact: true }).click();
  await button("加入自选 600000.SH").click();
  await button("600000.SH 已在自选").waitFor();
  await nav.getByRole("button", { name: "自选", exact: true }).click();
  const stock = () => page.getByRole("button", { name: /浦发银行/ });
  await stock().click();
  await stockResearch.waitFor();
  const researchUrl = page.url();
  await nav.getByRole("button", { name: "自选", exact: true }).click();
  await stock().click();
  await stockResearch.waitFor();
  if (page.url() !== researchUrl) throw Error("Watchlist reopened a different task");
  await nav.getByRole("button", { name: "市场", exact: true }).click();
  await page.keyboard.press("Control+k");
  if (!await search.evaluate(element => element === document.activeElement)) throw Error("Search shortcut did not focus the search box");
  await search.fill("浦发银行");
  await page.locator(".search-result").getByRole("button", { name: "打开研究" }).waitFor();
  await search.press("Enter");
  await stockResearch.waitFor();
  if (page.url() !== researchUrl) throw Error("Search reopened a different task");
  await page.keyboard.press("Control+p");
  await page.getByRole("heading", { name: "持仓", exact: true }).waitFor();

  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.body.scrollWidth > window.innerWidth + 1)) throw Error("Mobile layout overflows horizontally");
  await search.fill("浦发银行");
  const popup = await page.locator(".search-results").boundingBox();
  if (!popup || popup.x < 0 || popup.x + popup.width > 391) throw Error("Mobile search results are clipped");
  return "DESKTOP UI SMOKE PASS";
}
JS

result="$("$PWCLI" --session "$session" run-code "$flow" 2>&1)" || {
  echo "$result" >&2
  tail -60 "$root_tmp/runtime.log" "$root_tmp/vite.log" >&2
  exit 1
}
if ! sed -n '/^### Result$/{n;p;}' <<<"$result" | grep -Fq 'DESKTOP UI SMOKE PASS'; then
  echo "$result" >&2
  exit 1
fi
echo "DESKTOP UI SMOKE PASS"
