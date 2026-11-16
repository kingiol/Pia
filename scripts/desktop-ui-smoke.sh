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
PIA_AUTOSTART_TASKS=1 \
  "$PWD/scripts/python.sh" -m pia_runtime.cli serve >"$root_tmp/runtime.log" 2>&1 &
runtime_pid=$!

VITE_API_BASE="http://127.0.0.1:${api_port}/api" \
  pnpm run dev -- --host 127.0.0.1 --port "$web_port" >"$root_tmp/vite.log" 2>&1 &
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

"$PWCLI" --session "$session" open "http://127.0.0.1:${web_port}/" >/dev/null
ui_code_output="$("$PWCLI" --session "$session" run-code \
  "async page => { await page.getByRole('button', {name: '+ New review'}).click(); await page.getByText('POSITION_LIMIT_EXCEEDED', {exact: true}).waitFor({timeout: 10000}); }" 2>&1)" || {
  echo "$ui_code_output" >&2
  cat "$root_tmp/runtime.log" "$root_tmp/vite.log" >&2
  exit 1
}

body="$("$PWCLI" --session "$session" eval "document.body.innerText")"
grep -q "收盘市场复盘" <<<"$body"
grep -q "POSITION_LIMIT_EXCEEDED" <<<"$body"
grep -q "Blocked" <<<"$body"

deep_link_output="$("$PWCLI" --session "$session" run-code \
  "async page => { const task = new URL(page.url()).searchParams.get('task'); if (!task) throw new Error('task deep link missing'); await page.reload(); await page.getByRole('option').first().waitFor({timeout: 5000}); await page.getByRole('button', {name: 'Raw data'}).waitFor({timeout: 5000}); }" 2>&1)" || {
  echo "$deep_link_output" >&2
  cat "$root_tmp/runtime.log" "$root_tmp/vite.log" >&2
  exit 1
}

raw_data_output="$("$PWCLI" --session "$session" run-code \
  "async page => { await page.getByRole('button', {name: 'Raw data'}).click(); await page.getByText('Raw data and replay inputs').waitFor({timeout: 5000}); }" 2>&1)" || {
  echo "$raw_data_output" >&2
  cat "$root_tmp/runtime.log" "$root_tmp/vite.log" >&2
  exit 1
}

workspace_accessibility_output="$("$PWCLI" --session "$session" run-code \
  "async page => { await page.getByRole('button', {name: 'Copy evidence link'}).first().waitFor({timeout: 5000}); await page.getByText(/Used by:/).first().waitFor({timeout: 5000}); const taskList = page.getByRole('listbox', {name: 'Research tasks'}); await taskList.focus(); await taskList.press('ArrowDown'); }" 2>&1)" || {
  echo "$workspace_accessibility_output" >&2
  cat "$root_tmp/runtime.log" "$root_tmp/vite.log" >&2
  exit 1
}

watchlist_output="$("$PWCLI" --session "$session" run-code \
  "async page => { await page.getByRole('button', {name: 'W Watchlist'}).click(); await page.getByRole('heading', {name: 'Watchlists'}).waitFor({timeout: 5000}); await page.getByPlaceholder('600000.SH, 510300.SH').fill('600000.SH'); await page.getByRole('button', {name: 'Save', exact: true}).click(); await page.getByText('Watchlist saved').waitFor({timeout: 5000}); }" 2>&1)" || {
  echo "$watchlist_output" >&2
  cat "$root_tmp/runtime.log" "$root_tmp/vite.log" >&2
  exit 1
}

rules_code_output="$("$PWCLI" --session "$session" run-code \
  "async page => { await page.getByRole('button', {name: 'R Rules'}).click(); await page.getByText('Selected task gate').waitFor({timeout: 5000}); }" 2>&1)" || {
  echo "$rules_code_output" >&2
  cat "$root_tmp/runtime.log" "$root_tmp/vite.log" >&2
  exit 1
}
rules_body="$("$PWCLI" --session "$session" eval "document.body.innerText")"
grep -q "Selected task gate" <<<"$rules_body"
grep -q "Showing the selected task's evaluated rules." <<<"$rules_body"

route_output="$("$PWCLI" --session "$session" run-code \
  "async page => { await page.getByRole('button', {name: 'M Market'}).click(); await page.getByRole('heading', {name: 'Market', exact: true}).waitFor({timeout: 5000}); await page.getByRole('article', {name: /Market breadth/}).waitFor({timeout: 5000}); if (new URL(page.url()).pathname !== '/market') throw new Error('market route missing'); await page.getByRole('button', {name: 'P Portfolio'}).click(); await page.getByRole('heading', {name: 'Portfolio', exact: true}).waitFor({timeout: 5000}); await page.getByRole('article', {name: /Portfolio exposure/}).waitFor({timeout: 5000}); await page.getByRole('button', {name: 'R Research'}).click(); await page.getByRole('heading', {name: 'Research', exact: true}).waitFor({timeout: 5000}); await page.getByRole('article', {name: /Agent timeline/}).waitFor({timeout: 5000}); if (!new URL(page.url()).pathname.startsWith('/research/')) throw new Error('research task route missing'); }" 2>&1)" || {
  echo "$route_output" >&2
  cat "$root_tmp/runtime.log" "$root_tmp/vite.log" >&2
  exit 1
}

shortcut_output="$("$PWCLI" --session "$session" run-code \
  "async page => { await page.keyboard.press('Control+k'); const search = page.getByRole('textbox', {name: 'Search tasks or symbols'}); await search.waitFor({timeout: 5000}); if (!(await search.evaluate(el => el === document.activeElement))) throw new Error('search shortcut did not focus search'); await page.keyboard.press('Control+p'); await page.getByRole('heading', {name: 'Portfolio', exact: true}).waitFor({timeout: 5000}); await page.keyboard.press('Control+Enter'); await page.getByText('POSITION_LIMIT_EXCEEDED', {exact: true}).waitFor({timeout: 10000}); }" 2>&1)" || {
  echo "$shortcut_output" >&2
  cat "$root_tmp/runtime.log" "$root_tmp/vite.log" >&2
  exit 1
}

mobile_code_output="$("$PWCLI" --session "$session" run-code \
  "async page => { await page.setViewportSize({width: 390, height: 844}); const dimensions = await page.evaluate(() => ({body: document.body.scrollWidth, viewport: window.innerWidth})); if (dimensions.body > dimensions.viewport + 1) throw new Error('mobile layout overflows horizontally: ' + JSON.stringify(dimensions)); await page.getByRole('button', {name: '+ New review'}).isVisible(); }" 2>&1)" || {
  echo "$mobile_code_output" >&2
  cat "$root_tmp/runtime.log" "$root_tmp/vite.log" >&2
  exit 1
}

echo "DESKTOP UI SMOKE PASS"
