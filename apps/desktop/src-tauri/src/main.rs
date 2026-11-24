#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::Value;
use std::env;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex};
use std::time::Duration;
use tauri::image::Image;
use tauri::menu::{MenuBuilder, MenuItemBuilder};
use tauri::tray::TrayIconBuilder;
use tauri::{Emitter, Manager, RunEvent, WindowEvent};

#[cfg(windows)]
mod windows_job;

struct RuntimeChild {
    process: Child,
    endpoint: Value,
    #[cfg(windows)]
    job: std::os::windows::io::OwnedHandle,
}

const RELEASE_IDENTIFIER: &str = "com.pia.investment";
const DEBUG_IDENTIFIER: &str = "com.pia.investment.debug";

#[tauri::command]
fn desktop_channel(app: tauri::AppHandle) -> Result<&'static str, String> {
    match app.config().identifier.as_str() {
        DEBUG_IDENTIFIER => Ok("debug"),
        RELEASE_IDENTIFIER if !tauri::is_dev() && !cfg!(debug_assertions) => Ok("release"),
        _ => Err("桌面构建标识与启动方式不匹配，请使用 Pia 的调试启动命令。".into()),
    }
}

fn runtime_root() -> PathBuf {
    if let Ok(root) = env::var("PIA_RUNTIME_ROOT") {
        return PathBuf::from(root);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

fn sidecar_target() -> &'static str {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("macos", "aarch64") => "aarch64-apple-darwin",
        ("macos", "x86_64") => "x86_64-apple-darwin",
        ("windows", "aarch64") => "aarch64-pc-windows-msvc",
        ("windows", "x86_64") => "x86_64-pc-windows-msvc",
        ("linux", "aarch64") => "aarch64-unknown-linux-gnu",
        ("linux", "x86_64") => "x86_64-unknown-linux-gnu",
        _ => "unknown",
    }
}

fn packaged_sidecar() -> Option<PathBuf> {
    let executable = std::env::current_exe().ok()?;
    let parent = executable.parent()?;
    let mut path = parent.join(format!("pia-runtime-{}", sidecar_target()));
    if cfg!(target_os = "windows") {
        path.set_extension("exe");
    }
    if path.exists() {
        return Some(path);
    }
    let bundled = parent.join(if cfg!(target_os = "windows") {
        "pia-runtime.exe"
    } else {
        "pia-runtime"
    });
    bundled.exists().then_some(bundled)
}

fn spawn_runtime(app: &tauri::AppHandle, channel: &str) -> Result<RuntimeChild, String> {
    let data_provider = if channel == "debug" {
        env::var("PIA_DATA_PROVIDER").unwrap_or_else(|_| "fixture".to_string())
    } else {
        "akshare".to_string()
    };
    let mut data_dir = if let Some(base) = env::var_os("PIA_DESKTOP_DATA_BASE") {
        let base = PathBuf::from(base);
        if !base.is_absolute() {
            return Err("桌面数据根目录必须是绝对路径。".into());
        }
        base.join(&app.config().identifier)
    } else {
        app.path()
            .app_local_data_dir()
            .map_err(|error| error.to_string())?
    };
    if channel == "debug" {
        data_dir.push(if data_provider == "fixture" {
            "fixture"
        } else {
            "live"
        });
    }

    let mut command = if tauri::is_dev() {
        let root = runtime_root();
        let python = env::var("PIA_PYTHON").unwrap_or_else(|_| {
            if cfg!(target_os = "windows") {
                "python".to_string()
            } else {
                "python3".to_string()
            }
        });
        let mut command = Command::new(python);
        command
            .args(["-m", "pia_runtime.cli"])
            .current_dir(&root)
            .env("PYTHONPATH", root.join("packages-py/pia_runtime"));
        command
    } else {
        let sidecar = packaged_sidecar().ok_or("应用包缺少本地运行时，请重新安装 Pia。")?;
        let mut command = Command::new(sidecar);
        command
            .env_remove("PIA_RUNTIME_ROOT")
            .env_remove("PIA_FIXTURE_DIR")
            .env_remove("PIA_RULES_PATH");
        command
    };
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0).stdin(Stdio::piped());
    }
    #[cfg(windows)]
    let job = windows_job::create().map_err(|error| error.to_string())?;
    command
        .args([
            "desktop",
            "--channel",
            channel,
            "--provider",
            &data_provider,
            "--data-dir",
        ])
        .arg(data_dir)
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());
    #[cfg(unix)]
    command.arg("--exit-on-stdin-close");
    let mut process = command.spawn().map_err(|error| error.to_string())?;
    #[cfg(windows)]
    {
        process = windows_job::attach(&job, process).map_err(|error| error.to_string())?;
    }
    let stdout = process.stdout.take().expect("runtime stdout is piped");
    let mut child = RuntimeChild {
        process,
        endpoint: Value::Null,
        #[cfg(windows)]
        job,
    };
    let (send, ready) = mpsc::channel();
    std::thread::spawn(move || {
        let mut send = Some(send);
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if let Some(payload) = line.strip_prefix("PIA_DESKTOP_READY ") {
                if let Some(send) = send.take() {
                    let _ = send.send(
                        serde_json::from_str::<Value>(payload).map_err(|error| error.to_string()),
                    );
                }
            } else if let Some(message) = line.strip_prefix("PIA_DESKTOP_ERROR ") {
                if let Some(send) = send.take() {
                    let _ = send.send(Err(serde_json::from_str::<String>(message)
                        .unwrap_or_else(|_| "本地运行时未能完成启动，请检查运行时日志。".into())));
                }
            } else {
                println!("{line}");
            }
        }
    });
    match ready.recv_timeout(Duration::from_secs(60)) {
        Ok(Ok(endpoint)) if matches_desktop_endpoint(&endpoint, channel) => {
            child.endpoint = endpoint;
            Ok(child)
        }
        result => {
            terminate_runtime(child);
            Err(match result {
                Ok(Err(message)) => message,
                Ok(Ok(_)) => "本地运行时返回了不匹配的连接信息。".into(),
                Err(_) => "本地运行时未能完成启动，请检查运行时日志。".into(),
            })
        }
    }
}

fn matches_desktop_endpoint(endpoint: &Value, channel: &str) -> bool {
    let Some(id) = endpoint["instance_id"].as_str() else {
        return false;
    };
    let matching_id = id.len() == 32 && id.bytes().all(|byte| byte.is_ascii_hexdigit());
    let suffix = format!("/{id}/api");
    let valid_port = endpoint["base_url"]
        .as_str()
        .and_then(|url| url.strip_prefix("http://127.0.0.1:"))
        .and_then(|url| url.strip_suffix(&suffix))
        .and_then(|port| port.parse::<u16>().ok())
        .is_some_and(|port| port > 0);
    endpoint["channel"].as_str() == Some(channel) && matching_id && valid_port
}

fn terminate_runtime(child: RuntimeChild) {
    let mut process = child.process;
    #[cfg(unix)]
    {
        unsafe {
            libc::killpg(process.id() as i32, libc::SIGTERM);
        }
        for _ in 0..30 {
            if process.try_wait().ok().flatten().is_some() {
                return;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        unsafe {
            libc::killpg(process.id() as i32, libc::SIGKILL);
        }
    }
    #[cfg(windows)]
    drop(child.job);
    let _ = process.kill();
    let _ = process.wait();
}

fn stop_runtime(runtime: &Arc<Mutex<Option<RuntimeChild>>>) {
    if let Some(child) = runtime.lock().expect("runtime mutex poisoned").take() {
        terminate_runtime(child);
    }
}

#[tauri::command]
async fn ensure_local_runtime(app: tauri::AppHandle) -> Result<Value, String> {
    let channel = desktop_channel(app.clone())?;
    tauri::async_runtime::spawn_blocking(move || {
        let runtime = app.state::<Arc<Mutex<Option<RuntimeChild>>>>();
        let mut child = runtime.lock().map_err(|error| error.to_string())?;
        if let Some(runtime) = child.as_mut() {
            if runtime
                .process
                .try_wait()
                .map_err(|error| error.to_string())?
                .is_none()
            {
                return Ok(runtime.endpoint.clone());
            }
        }
        drop(child.take());
        let runtime = spawn_runtime(&app, channel)?;
        let endpoint = runtime.endpoint.clone();
        *child = Some(runtime);
        Ok(endpoint)
    })
    .await
    .map_err(|error| error.to_string())?
}

fn main() {
    let runtime: Arc<Mutex<Option<RuntimeChild>>> = Arc::new(Mutex::new(None));
    let runtime_for_exit = Arc::clone(&runtime);
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Arc::clone(&runtime))
        .invoke_handler(tauri::generate_handler![
            desktop_channel,
            ensure_local_runtime
        ])
        .setup(move |_app| {
            let show = MenuItemBuilder::with_id("show", "Show Pia").build(_app)?;
            let status = MenuItemBuilder::with_id("status", "View runtime status").build(_app)?;
            let pause =
                MenuItemBuilder::with_id("pause-scheduler", "Pause scheduled tasks").build(_app)?;
            let resume = MenuItemBuilder::with_id("resume-scheduler", "Resume scheduled tasks")
                .build(_app)?;
            let quit = MenuItemBuilder::with_id("quit", "Quit Pia").build(_app)?;
            let menu = MenuBuilder::new(_app)
                .items(&[&show, &status, &pause, &resume, &quit])
                .build()?;
            TrayIconBuilder::new()
                .icon(Image::from_bytes(include_bytes!("../icons/icon.png"))?)
                .menu(&menu)
                .tooltip("Pia 投资研究工作台")
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "status" => {
                        let _ = app.emit("pia://tray", "status");
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "pause-scheduler" => {
                        let _ = app.emit("pia://tray", "pause-scheduler");
                    }
                    "resume-scheduler" => {
                        let _ = app.emit("pia://tray", "resume-scheduler");
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(_app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Pia Desktop");
    app.run(move |app_handle, event| match event {
        RunEvent::WindowEvent {
            event: WindowEvent::CloseRequested { api, .. },
            label,
            ..
        } if label == "main" => {
            api.prevent_close();
            if let Some(window) = app_handle.get_webview_window("main") {
                let _ = window.hide();
            }
        }
        RunEvent::ExitRequested { .. } | RunEvent::Exit => {
            stop_runtime(&runtime_for_exit);
        }
        _ => {}
    });
}
