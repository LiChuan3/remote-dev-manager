use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::process::{Child, Command};
use std::sync::atomic::{AtomicU16, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::menu::{Menu, MenuEvent, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::webview::PageLoadEvent;
use tauri::{AppHandle, Manager, RunEvent, WindowEvent};
use tauri_plugin_autostart::MacosLauncher;
use tauri_plugin_opener::OpenerExt;

/// Preferred port for the Python FastAPI sidecar. Falls back dynamically if busy.
const DEFAULT_SIDECAR_PORT: u16 = 8765;
static SIDECAR_PORT: AtomicU16 = AtomicU16::new(DEFAULT_SIDECAR_PORT);

/// Holds the spawned Python/sidecar child process so we can kill it on exit.
#[derive(Default)]
struct SidecarState(Mutex<Option<Child>>);

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Returns the port the sidecar is reachable on. Callable from JS via `invoke`.
#[tauri::command]
fn get_sidecar_port() -> u16 {
    SIDECAR_PORT.load(Ordering::Relaxed)
}

/// Kills the sidecar and exits the application. Callable from JS via `invoke`.
#[tauri::command]
fn quit_app(app: AppHandle) {
    kill_sidecar(&app);
    app.exit(0);
}

/// Kills the stored sidecar child, if any. Safe to call multiple times.
fn kill_sidecar(app: &AppHandle) {
    if let Some(state) = app.try_state::<SidecarState>() {
        if let Ok(mut guard) = state.0.lock() {
            if let Some(mut child) = guard.take() {
                request_sidecar_shutdown(SIDECAR_PORT.load(Ordering::Relaxed));

                let deadline = Instant::now() + Duration::from_secs(3);
                loop {
                    match child.try_wait() {
                        Ok(Some(_status)) => return,
                        Ok(None) if Instant::now() < deadline => {
                            std::thread::sleep(Duration::from_millis(100));
                        }
                        _ => break,
                    }
                }

                if let Err(e) = child.kill() {
                    eprintln!("[rdm-desktop] failed to kill sidecar after shutdown request: {e}");
                }
                // Reap the process so it doesn't linger as a zombie.
                let _ = child.wait();
            }
        }
    }
}

/// Pick a local API port. Prefer 8765, but avoid hard failure when it is busy.
fn choose_sidecar_port() -> u16 {
    if TcpListener::bind(("127.0.0.1", DEFAULT_SIDECAR_PORT)).is_ok() {
        return DEFAULT_SIDECAR_PORT;
    }

    match TcpListener::bind(("127.0.0.1", 0)) {
        Ok(listener) => listener
            .local_addr()
            .map(|addr| addr.port())
            .unwrap_or(DEFAULT_SIDECAR_PORT),
        Err(_) => DEFAULT_SIDECAR_PORT,
    }
}

/// Ask the sidecar to stop managed services before exiting.
fn request_sidecar_shutdown(port: u16) {
    if let Ok(mut stream) = TcpStream::connect(("127.0.0.1", port)) {
        let _ = stream.set_read_timeout(Some(Duration::from_millis(1000)));
        let _ = stream.set_write_timeout(Some(Duration::from_millis(1000)));
        let request = concat!(
            "POST /api/shutdown HTTP/1.1\r\n",
            "Host: 127.0.0.1\r\n",
            "Content-Length: 0\r\n",
            "Connection: close\r\n",
            "\r\n"
        );
        let _ = stream.write_all(request.as_bytes());
        let mut buf = [0_u8; 512];
        let _ = stream.read(&mut buf);
    }
}

/// Applies platform-specific spawn tweaks (hide console window on Windows).
fn configure_command(cmd: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    // Silence the binding to avoid an unused warning on non-Windows.
    let _ = cmd;
}

/// Spawns the Python sidecar.
///
/// Debug build: `python -m rdm.api --port 8765` with cwd at the repo root
/// (two levels up from `src-tauri`), falling back to `python3`.
///
/// Release build: the bundled `rdm-sidecar` binary resolved next to the app
/// executable or via the Tauri resource dir, with `--port 8765`.
#[cfg_attr(debug_assertions, allow(unused_variables))]
fn spawn_sidecar(app: &AppHandle, port: u16) -> Option<Child> {
    let port = port.to_string();

    #[cfg(debug_assertions)]
    {
        // Repo root is two levels up from `desktop/src-tauri`.
        let repo_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..");

        for interpreter in ["python", "python3"] {
            let mut cmd = Command::new(interpreter);
            cmd.args(["-m", "rdm.api", "--port", &port]);
            cmd.current_dir(&repo_root);
            configure_command(&mut cmd);

            match cmd.spawn() {
                Ok(child) => {
                    eprintln!(
                        "[rdm-desktop] spawned sidecar via `{interpreter} -m rdm.api --port {port}` (cwd: {})",
                        repo_root.display()
                    );
                    return Some(child);
                }
                Err(e) => {
                    eprintln!("[rdm-desktop] `{interpreter}` failed to spawn: {e}");
                }
            }
        }

        eprintln!(
            "[rdm-desktop] could not start the Python sidecar (tried python/python3). \
             Frontend will stay in a connecting state."
        );
        None
    }

    #[cfg(not(debug_assertions))]
    {
        // Build a list of candidate paths for the bundled binary.
        let exe_name = if cfg!(windows) {
            "rdm-sidecar.exe"
        } else {
            "rdm-sidecar"
        };

        let mut candidates: Vec<std::path::PathBuf> = Vec::new();
        let mut search_dirs: Vec<std::path::PathBuf> = Vec::new();

        // 1) Next to the current executable.
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                candidates.push(dir.join(exe_name));
                search_dirs.push(dir.to_path_buf());
            }
        }

        // 2) Tauri resource dir.
        if let Ok(res_dir) = app.path().resource_dir() {
            candidates.push(res_dir.join(exe_name));
            candidates.push(res_dir.join("binaries").join(exe_name));
            search_dirs.push(res_dir.clone());
            search_dirs.push(res_dir.join("binaries"));
        }

        // Tauri externalBin files are commonly suffixed with the target triple.
        for dir in search_dirs {
            if let Ok(entries) = std::fs::read_dir(dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    let Some(name) = path.file_name().and_then(|n| n.to_str()) else {
                        continue;
                    };
                    if name.starts_with("rdm-sidecar") {
                        candidates.push(path);
                    }
                }
            }
        }

        for candidate in &candidates {
            if !candidate.exists() {
                continue;
            }
            let mut cmd = Command::new(candidate);
            cmd.args(["--port", &port]);
            configure_command(&mut cmd);

            match cmd.spawn() {
                Ok(child) => {
                    eprintln!(
                        "[rdm-desktop] spawned bundled sidecar `{}` --port {port}",
                        candidate.display()
                    );
                    return Some(child);
                }
                Err(e) => {
                    eprintln!(
                        "[rdm-desktop] failed to spawn `{}`: {e}",
                        candidate.display()
                    );
                }
            }
        }

        eprintln!(
            "[rdm-desktop] bundled `rdm-sidecar` not found in any candidate path: {candidates:?}. \
             Frontend will stay in a connecting state."
        );
        let _ = app;
        None
    }
}

/// Shows and focuses the main window, creating no new window.
fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// Toggles the main window's visibility (used on tray left-click).
fn toggle_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        match window.is_visible() {
            Ok(true) => {
                let _ = window.hide();
            }
            _ => {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }
    }
}

/// A navigation guard plugin that opens truly external links in the system
/// browser instead of inside the webview. The app's own pages (tauri scheme,
/// localhost / 127.0.0.1 / tauri.localhost dev + bundled assets) load normally.
fn external_navigation_plugin<R: tauri::Runtime>() -> tauri::plugin::TauriPlugin<R> {
    tauri::plugin::Builder::<R>::new("external-navigation")
        .on_navigation(|webview, url| {
            let is_internal_host = matches!(
                url.host_str(),
                Some("localhost") | Some("127.0.0.1") | Some("tauri.localhost") | Some("::1")
            );
            if url.scheme() == "tauri" || is_internal_host {
                return true;
            }
            if matches!(url.scheme(), "http" | "https" | "mailto" | "tel") {
                let _ = webview.opener().open_url(url.as_str(), None::<&str>);
                return false;
            }
            true
        })
        .build()
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // A second instance was launched: focus the existing window.
            show_main_window(app);
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(external_navigation_plugin())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None,
        ))
        .manage(SidecarState::default())
        .setup(|app| {
            let handle = app.handle();
            let port = choose_sidecar_port();
            SIDECAR_PORT.store(port, Ordering::Relaxed);

            // Spawn the Python/sidecar process and store the handle in state.
            if let Some(child) = spawn_sidecar(handle, port) {
                if let Some(state) = app.try_state::<SidecarState>() {
                    if let Ok(mut guard) = state.0.lock() {
                        *guard = Some(child);
                    }
                }
            }

            // Build the tray menu.
            let show_item = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &quit_item])?;

            // Build the tray icon.
            let _tray = TrayIconBuilder::with_id("main-tray")
                .icon(app.default_window_icon().cloned().ok_or_else(|| {
                    tauri::Error::AssetNotFound("default window icon".into())
                })?)
                .tooltip("远程开发管理器")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event: MenuEvent| match event.id().as_ref() {
                    "show" => show_main_window(app),
                    "quit" => {
                        kill_sidecar(app);
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_main_window(tray.app_handle());
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            // Hide to tray instead of quitting when the user closes the window.
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .on_page_load(|webview, payload| {
            // Flash-prevention: the main window starts hidden (visible: false in
            // tauri.conf.json) and is shown only after the first paint finishes.
            if webview.label() == "main" && matches!(payload.event(), PageLoadEvent::Finished) {
                let _ = webview.window().show();
            }
        })
        .invoke_handler(tauri::generate_handler![get_sidecar_port, quit_app])
        .build(tauri::generate_context!())
        .expect("error while building the Remote Dev Manager application")
        .run(|app_handle, event| match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                kill_sidecar(app_handle);
            }
            _ => {}
        });
}
