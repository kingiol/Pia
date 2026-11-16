import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "../../desktop/src/App";
import "../../desktop/src/styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js");
  });
}
