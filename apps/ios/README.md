# Pia iOS Client

`PiaMobileClient` is the Swift Concurrency transport and contract layer used by
the SwiftUI app shell. It uses the same Cloud API paths and Bearer semantics as the
Desktop/Web client, including task creation, approval, task control,
notifications and SSE URL construction.

Run the client tests with:

```bash
swift test --package-path apps/ios/PiaMobileClient
```

Build the macOS-hosted SwiftUI shell with:

```bash
swift build --package-path apps/ios/PiaMobileClient --product PiaApp
```

The client persists the Bearer token in Keychain, registers the current device,
uploads an APNs device token when iOS provides one, consumes incremental
`/sync` changes with a UserDefaults cursor during foreground and background
refresh, and exposes device unregister and task-control transport methods. On
iOS, `PiaBackgroundRefreshCoordinator` wraps `BGTaskScheduler`; APNs
credentials and provider delivery remain deployment configuration and are never
reported as delivered without a gateway receipt.

The app reads its cloud endpoint from the `pia.cloud_base_url` UserDefaults
key, then `PIA_CLOUD_URL`. The legacy endpoint settings remain readable when
neither is configured. The local simulator defaults to
`http://127.0.0.1:8765/api`. For a device or remote Cloud deployment, set the
UserDefaults key before launching the app.
