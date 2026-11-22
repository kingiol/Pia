# Desktop Runtime Selection

## Scope

Desktop can connect to either the local Python sidecar or an existing authenticated
Cloud API. This selects the workspace and execution location for all requests,
including task controls, scheduler actions, exports and task event streams.
Web keeps its existing deployment configuration and login flow.

No data is copied or merged between Local and Cloud. Cloud deployment, worker
configuration, account provisioning and automatic failover are outside this change.

## Interaction

First launch opens the Local workspace immediately, without a mode-selection
screen. A segmented Local / Cloud control sits at the bottom of the left sidebar,
below navigation. The sidebar does not display a persistent runtime-status or
model-name row. Web does not render this control.
Selecting Cloud opens a modal connection form over the current workspace.
Cancel and Escape close the form without changing the active environment.
Selecting Local connects directly. Later launches restore the saved mode.

```text
Navigation
...
Notifications
----------------
Runtime
[ Local | Cloud ]

Cloud Connection
API URL       [ https://pia.example.com/api ]
Access token  [ *************************** ]
                       [ Cancel ] [ Connect ]
```

Cloud accepts HTTPS endpoints, or HTTP on loopback for development. The form
accepts a deployment root or an API base ending in `/api`, including a proxy
prefix. Credentials, query parameters and fragments in the address are rejected.
The endpoint must report `runtime: cloud`, and the token must pass an authenticated
task-list request before the connection is saved.

The selected mode and Cloud URL are saved in local storage. The token is saved
only in session storage and bound to the exact API base. Debug and Release use
separate keys for both. A Cloud session without a
token keeps the workspace and sidebar available, displays the authentication
error, and allows reconnecting through the Cloud control or switching to Local.
A Cloud token is never restored into
the Local client, including from the Web client's legacy token keys.

Applying a connection reloads the workspace to dispose of requests, subscriptions
and UI state from the previous environment. A failed connection leaves the saved
environment intact. Local startup waits for the sidecar before fetching workspace
data; the sidebar and homepage remain visible during startup or connection failure.

## Local Credentials

In Local mode, Settings includes a DeepSeek API Key field with Save and Clear
actions and the effective source: saved credential, environment, or unconfigured.
The field never loads an existing secret. Saving writes to the host credential
manager (macOS Keychain, Windows Credential Vault, or Linux Secret Service), not
browser storage or the workspace database.

Saved `DEEPSEEK_API_KEY` credentials take precedence over the environment.
Clearing the saved Key immediately falls back to the runtime process's
`DEEPSEEK_API_KEY`, if present. Saving and clearing update existing model clients, including policy
routes using that credential reference, for subsequent requests without restart.
Authentication failures do not trigger credential fallback.

The credential API returns only configured status and source. It rejects Cloud
mode, non-loopback peers/hosts, and untrusted browser origins. Supported Desktop
origins are the packaged Tauri origins and localhost port 5173 for development.
Cloud model credentials remain managed on the Cloud host. Debug uses the
`pia.debug` credential service and reads Debug-specific environment credentials
such as `PIA_DEBUG_DEEPSEEK_API_KEY`. Release retains `pia` and the existing
Release environment variable names.

In **Settings → Tushare**, save or clear a Token using the same native credential
manager. A saved Token takes precedence over `TUSHARE_TOKEN` in Local mode.
Clearing it restores the environment value when available. New requests use the
updated credential immediately. The form reports the effective source and never
reads back the Token.

During live synchronization, supported A-share stock symbols use Tushare's free
unadjusted `daily` endpoint over HTTPS first. AKShare supplies ETF bars, the trading calendar,
the market snapshot, and other research inputs. The free route calls `daily`
only. A successful stock-bar request can be reported separately from a degraded
market snapshot. Fixture mode continues to use fixture data. Cloud providers
remain managed by the Cloud operator.

## Sidecar Lifecycle

For source debugging, `pnpm run debug:desktop:local` forces Local and hides the
Cloud controls without changing the saved connection. It explicitly uses AKShare
for live market data; `pnpm run debug:desktop:local:fixture` uses fixture data
instead. `pnpm run debug:desktop` keeps both modes available and retains the
environment's data provider (fixture when unset).
All three commands open the Debug build of Tauri, which starts the Python source
runtime when the Local workspace opens. Port 5173 is for Vite. The Python runtime
binds its own loopback port. Restart the application after Python changes.

The shell starts a managed runtime when the frontend requests Local. Release
uses its packaged sidecar. The child reports an instance-specific loopback API
base after binding its port. The frontend checks the build channel and instance
ID before sending workspace requests. The runtime accepts API requests under
that instance's prefix. `VITE_API_BASE` and `VITE_API_TOKEN` still configure
browser previews. Cold startup has a 60-second budget for extraction and Python
startup, followed by an HTTP readiness check.

Debug and Release each use their bundle identifier to locate local storage.
Debug further separates fixture and live databases. The sidecar locks the data
directory before opening SQLite or DuckDB. See [data paths and legacy
migration](OPERATIONS.md#桌面端数据隔离).

Starting directly in Cloud requires no working local Python installation.
Switching from Local to Cloud keeps an already running sidecar alive until app
exit so local tasks are not interrupted. Restarting in Cloud does not start it.
Closing the window still hides to tray; quitting still terminates the managed
sidecar process group.

The packaged CSP permits HTTPS API connections and loopback HTTP while retaining
`default-src 'self'` and Tauri IPC connections.

## Acceptance And Verification

- First launch opens the homepage in Local without a selection screen.
- The sidebar footer contains keyboard-accessible Local / Cloud controls.
- Cloud configuration is a modal with cancel, Escape and focus restoration.
- Local starts or reuses the sidecar and displays the local workspace.
- Debug and Release can run together and reconnect only to their own runtime.
- Release data remains available after quitting and relaunching the packaged app.
- Cloud validates its URL, runtime mode and token before saving.
- Invalid credentials and unreachable endpoints remain recoverable.
- Switching and reloading restore the chosen workspace without mixing data or tokens.
- REST requests and task SSE use the same selected API base and token.
- Local Settings can save and clear the DeepSeek Key without a runtime restart.
- Credential source changes from saved to environment (or unconfigured) on clear.
- Cloud mode and untrusted origins cannot manage host credentials.
- Desktop and Web builds pass; Rust shell compiles.
- Connection parsing, persistence and token isolation pass
  `node --test scripts/runtime-connection.test.mjs`.

Browser verification should use isolated fixture Local and Cloud databases and
check task creation and event requests in both environments. A browser preview
uses an externally started local API because it has no Tauri shell.
`desktop-lifecycle-smoke.sh` accepts Local or Cloud startup.
Set `PIA_EXPECT_LOCAL_RUNTIME=1` when using Local to also require
sidecar startup. Packaged macOS/Windows lifecycle and remote HTTPS deployment
acceptance remain separate platform checks.

Verified on 2026-11-12 in the working tree: eight connection unit tests,
TypeScript checking, Desktop/Web production builds, Rust `cargo check`, documentation
links and shell syntax checks. The macOS `Pia.app` was rebuilt and opened to verify
default Local startup directly into the homepage, sidebar footer placement, the
Cloud modal, cancel/Escape returning to Local, and successful sidecar readiness.
Normal application quit was also confirmed to stop its managed processes.
The cold-start regression test first failed with the old startup budget and
passed after allowing 60 seconds; timeout and runtime-mode rejection also pass.

Connection routing acceptance used isolated fixture Local and
Cloud APIs: both task creation routes, authenticated Cloud SSE, Local EventSource,
mode switching, reload persistence, rejected credentials, runtime mode mismatch,
unreachable API recovery and a new tab without a session token. Observed Cloud
requests used only the Cloud API and bearer token; Local requests carried no Cloud
token. Real remote HTTPS Cloud and Windows packaging remain unverified.

Credential settings verification on 2026-11-12: the Python suite passed 264 tests
(one optional PostgreSQL test skipped), and TypeScript, Desktop/Web builds,
generated client and documentation checks passed. The rebuilt macOS app was
tested against an isolated fixture runtime with a simulated credential store:
the password field masked input, Save cleared the draft and showed the saved
source, and Clear restored the environment source without restarting. Backend
tests cover actual request Authorization headers after updates, custom policy
credential references, storage failures, input validation, authentication and
Local-only origin/host restrictions. No live DeepSeek API call was made.
All nine Desktop tests pass, including rendering Local credential settings when
workspace health data is unavailable. The panel uses the selected Desktop mode,
so an unrelated market-data refresh failure cannot hide credential settings.
The final packaged app was also opened with its managed Local sidecar and
confirmed to show the unconfigured Key field despite an existing
`CapabilityUnavailable` market-data error.
