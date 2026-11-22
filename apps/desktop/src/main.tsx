import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { DesktopApp } from "./DesktopApp";
import type { DesktopChannel } from "./runtimeConnection";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);

async function mountDesktop() {
  try {
    let channel: DesktopChannel | undefined;
    if ("__TAURI_INTERNALS__" in window) {
      const { invoke } = await import("@tauri-apps/api/core");
      channel = await invoke<DesktopChannel>("desktop_channel");
      if (channel !== "debug" && channel !== "release") throw new Error("无法识别当前桌面构建。");
    }
    root.render(<StrictMode><DesktopApp channel={channel} /></StrictMode>);
  } catch (error) {
    const message = typeof error === "string" ? error : "无法确认桌面运行环境，请重新启动 Pia。";
    root.render(<main className="auth-shell"><p className="auth-error" role="alert">{message}</p></main>);
  }
}

void mountDesktop();
