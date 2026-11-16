#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"

root_tmp="$(mktemp -d)"
api_port="${PIA_TRUST_API_PORT:-8894}"
web_port="${PIA_TRUST_WEB_PORT:-5184}"
session="pia-trust-smoke-${$}"
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
PIA_AUTOSTART_TASKS=0 \
  "$PWD/scripts/python.sh" -m pia_runtime.cli serve >"$root_tmp/runtime.log" 2>&1 &
runtime_pid=$!

VITE_API_BASE="http://127.0.0.1:${api_port}/api" \
  pnpm exec vite --config apps/desktop/vite.config.ts \
    --host 127.0.0.1 --port "$web_port" --strictPort \
    >"$root_tmp/vite.log" 2>&1 &
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

"$PWCLI" --session "$session" open \
  "http://127.0.0.1:${web_port}/?task=stale-task-from-previous-runtime" >/dev/null

result="$("$PWCLI" --session "$session" run-code \
  "async page => {
    const missingResponses = [];
    page.on('response', response => {
      if (response.url().includes('/api/tasks/stale-task-from-previous-runtime')) {
        missingResponses.push(response.status());
      }
    });
    await page.waitForTimeout(1600);
    const body = await page.locator('body').innerText();
    await page.setViewportSize({width: 390, height: 844});
    const dimensions = await page.evaluate(() => ({body: document.body.scrollWidth, viewport: window.innerWidth}));
    return {path: new URL(page.url()).pathname, hasRawError: body.includes('not_found'), missingResponses, dimensions};
  }" 2>&1)"

echo "$result"
grep -Fq '"path":"/overview"' <<<"$result"
grep -Fq '"hasRawError":false' <<<"$result"
grep -Fq '"missingResponses":[]' <<<"$result"
grep -Fq '"body":390' <<<"$result"

echo "TRUST UI SMOKE PASS"
