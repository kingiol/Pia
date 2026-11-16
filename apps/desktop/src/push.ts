import type { DeviceRegistration } from "../../../packages/contracts/generated/typescript/models";

type RegisterDevice = (device: DeviceRegistration) => Promise<unknown>;

export type WebPushResult =
  | { status: "registered"; deviceId: string }
  | { status: "unsupported"; detail: string }
  | { status: "disabled"; detail: string };

function decodeBase64Url(value: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const normalized = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const decoded = window.atob(normalized);
  return Uint8Array.from(decoded, (character) => character.charCodeAt(0));
}

function deviceId(): string {
  const key = "pia.web_device_id";
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const created = `web-${crypto.randomUUID()}`;
  window.localStorage.setItem(key, created);
  return created;
}

export async function registerWebPushDevice(
  registerDevice: RegisterDevice,
): Promise<WebPushResult> {
  const publicKey = import.meta.env.VITE_WEB_PUSH_PUBLIC_KEY as string | undefined;
  if (!publicKey) {
    return {
      status: "disabled",
      detail: "VITE_WEB_PUSH_PUBLIC_KEY is not configured",
    };
  }
  if (
    typeof window === "undefined" ||
    !("serviceWorker" in navigator) ||
    !("PushManager" in window) ||
    !("Notification" in window)
  ) {
    return { status: "unsupported", detail: "This browser does not support Web Push" };
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    return { status: "disabled", detail: `Notification permission: ${permission}` };
  }

  const registration = await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: decodeBase64Url(publicKey),
    });
  }

  await registerDevice({
    device_id: deviceId(),
    platform: "web",
    device_name: "Pia Web",
    push_token: JSON.stringify(subscription.toJSON()),
  });
  return { status: "registered", deviceId: deviceId() };
}
