#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::env;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::image::Image;
use tauri::menu::{MenuBuilder, MenuItemBuilder};
use tauri::tray::TrayIconBuilder;
use tauri::{Emitter, Manager, RunEvent, WindowEvent};

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

fn spawn_runtime() -> std::io::Result<Child> {
    let data_provider = env::var("PIA_DATA_PROVIDER").unwrap_or_else(|_| "akshare".to_string());
    if let Some(sidecar) = packaged_sidecar() {
        let mut command = Command::new(sidecar);
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
        }
        return command
            .args(["serve", "--scheduler"])
            .env("PIA_DATA_PROVIDER", data_provider)
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn();
    }
    let root = runtime_root();
    let python = env::var("PIA_PYTHON").unwrap_or_else(|_| {
        if cfg!(target_os = "windows") { "python".to_string() } else { "python3".to_string() }
    });
    let mut command = Command::new(python);
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    command
        .args(["-m", "pia_runtime.cli", "serve", "--scheduler"])
        .current_dir(&root)
        .env("PYTHONPATH", root.join("packages-py/pia_runtime"))
        .env("PIA_DATA_PROVIDER", data_provider)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
}

fn stop_runtime(runtime: &Arc<Mutex<Option<Child>>>) {
    if let Some(mut child) = runtime.lock().expect("runtime mutex poisoned").take() {
        let pid = child.id();
        #[cfg(unix)]
        unsafe {
            let _ = libc::killpg(pid as i32, libc::SIGTERM);
        }
        #[cfg(windows)]
        {
            let _ = Command::new("taskkill")
                .args(["/PID", &pid.to_string(), "/T", "/F"])
                .status();
        }
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[tauri::command]
fn ensure_local_runtime(runtime: tauri::State<'_, Arc<Mutex<Option<Child>>>>) -> Result<(), String> {
    if env::var("PIA_MANAGED_RUNTIME").as_deref() == Ok("0") {
        return Ok(());
    }
    let mut child = runtime.lock().map_err(|error| error.to_string())?;
    if let Some(process) = child.as_mut() {
        if process.try_wait().map_err(|error| error.to_string())?.is_none() {
            return Ok(());
        }
    }
    *child = Some(spawn_runtime().map_err(|error| error.to_string())?);
    Ok(())
}

fn main() {
    let runtime: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let runtime_for_exit = Arc::clone(&runtime);
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Arc::clone(&runtime))
        .invoke_handler(tauri::generate_handler![ensure_local_runtime])
        .setup(move |_app| {
            let show = MenuItemBuilder::with_id("show", "Show Pia").build(_app)?;
            let status = MenuItemBuilder::with_id("status", "View runtime status").build(_app)?;
            let pause = MenuItemBuilder::with_id("pause-scheduler", "Pause scheduled tasks").build(_app)?;
            let resume = MenuItemBuilder::with_id("resume-scheduler", "Resume scheduled tasks").build(_app)?;
            let quit = MenuItemBuilder::with_id("quit", "Quit Pia").build(_app)?;
            let menu = MenuBuilder::new(_app)
                .items(&[&show, &status, &pause, &resume, &quit])
                .build()?;
            TrayIconBuilder::new()
                .icon(Image::from_bytes(include_bytes!("../icons/icon.png"))?)
                .menu(&menu)
                .tooltip("Pia Research Workspace")
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
    app.run(move |app_handle, event| {
        match event {
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
        }
    });
}
