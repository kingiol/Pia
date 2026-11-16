# Pia Android

This module is the native Android extension client for the cloud execution
plane. It uses Kotlin and Jetpack Compose and talks to the same `/api` contract
as Desktop, Web and iOS.

The client owns authentication, task and notification presentation, device
registration, optional FCM token upload, incremental sync with a persisted
SharedPreferences cursor, and read-state acknowledgement. Bearer tokens are
stored through Android Keystore-backed encryption, and `PiaRefreshWorker`
schedules network-constrained background refresh. Agent orchestration, Rules,
Evidence provenance and Audit remain cloud responsibilities; FCM token
acquisition and delivery still require
deployment credentials and a configured device gateway.

## Build

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
./apps/android/gradlew --no-daemon --project-dir apps/android :app:assembleDebug
```

The emulator defaults to `http://10.0.2.2:8765/api`. For a physical device or
another Cloud deployment, inject the endpoint at build time:

```bash
./apps/android/gradlew --no-daemon --project-dir apps/android \
  -PpiaCloudUrl=http://192.168.1.20:8765/api :app:assembleDebug
```

The legacy `piaServerUrl` property remains a fallback when `piaCloudUrl` is unset.
