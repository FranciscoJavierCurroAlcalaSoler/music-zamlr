use std::fs;
use std::process::id as process_id;
use std::time::{SystemTime, UNIX_EPOCH};

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};

const PORT_PREFIX: &str = "ZAMLR_PORT=";
const LOG_PREFIX: &str = "ZAMLR_LOG=";
// The origin the webview reports on Windows. The backend compares whole
// strings against the Origin header, so this has to match it exactly.
const WEBVIEW_ORIGIN: &str = "http://tauri.localhost";
// Where the page comes from under `tauri dev`: Vite serves it, so the
// window reports the dev server's origin instead of the webview's own.
const DEV_SERVER_ORIGIN: &str = "http://localhost:5173";

/// The origins the backend accepts, which differ between a development run
/// and a bundle.
///
/// The dev server's origin is granted only in a debug build. Shipping it
/// would let any page served from that port on the user's machine talk to
/// their backend, which is a door this app has no reason to leave open.
fn allowed_origins() -> String {
    if cfg!(debug_assertions) {
        format!("{WEBVIEW_ORIGIN},{DEV_SERVER_ORIGIN}")
    } else {
        WEBVIEW_ORIGIN.to_string()
    }
}
const BACKEND_EXE: &str = "music-zamlr-backend.exe";
const FPCALC_EXE: &str = "fpcalc.exe";
// Where the bundler puts the folder named in tauri.conf.json's resources.
const BACKEND_RESOURCE_DIR: &str = "backend";

/// Find a program this application ships, among its own resources.
///
/// They are bundle resources rather than `externalBin` sidecars, and for the
/// backend that is forced: `externalBin` copies a single file, while
/// PyInstaller's one-folder build is an executable beside an `_internal`
/// directory holding the Python runtime. Copied alone, the program starts
/// and dies on a missing python3xx.dll.
///
/// `tauri dev` copies resources into the build directory as well, so one
/// path serves both a development run and an installed app.
fn resource_path(app: &tauri::AppHandle, file_name: &str) -> Result<std::path::PathBuf, String> {
    let path = app
        .path()
        .resource_dir()
        .map_err(|error| format!("no resource directory: {error}"))?
        .join(BACKEND_RESOURCE_DIR)
        .join(file_name);
    if !path.exists() {
        // Named here rather than left to the spawn, which reports only that
        // a program could not be started, without saying which one or where
        // it was looked for.
        return Err(format!("{file_name} is missing at {}", path.display()));
    }
    Ok(path)
}

/// Read the port out of the line the backend announces it on.
///
/// Trimmed before parsing: the child writes its lines with a carriage
/// return on Windows, and `u16::from_str` rejects one. Untrimmed, the shell
/// would never find a port that was announced perfectly well.
pub fn parse_port_line(line: &str) -> Option<u16> {
    line.trim().strip_prefix(PORT_PREFIX)?.parse().ok()
}

/// Read the log file's path out of the line that carries it.
pub fn parse_log_line(line: &str) -> Option<&str> {
    line.trim().strip_prefix(LOG_PREFIX)
}

/// A token for this launch alone.
///
/// Not a secret against someone who can already read this process's command
/// line or environment. It closes the case that matters: any page open in
/// the browser can reach a port on this machine, and the import endpoint
/// deletes files.
fn launch_token() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or(0);
    format!("{:x}{:x}", nanos, process_id())
}

/// Hand the page what only this process knows.
///
/// The port is chosen at every launch and the token is made at every
/// launch, so neither can be built into the bundle. The page reads this
/// global at each request, and it polls the health endpoint behind its
/// splash until the backend answers — so arriving late is handled, and
/// arriving never is the failure the splash reports.
fn inject_connection(window: &tauri::WebviewWindow, port: u16, token: &str, log_path: &str) {
    let script = format!(
        r#"window.__ZAMLR__ = {{ apiBase: "http://127.0.0.1:{port}", token: "{token}", logPath: {log_path} }};"#,
        port = port,
        token = token,
        // Serialised rather than quoted by hand: a Windows path is full of
        // backslashes, and every one of them is an escape inside a JavaScript
        // string literal.
        log_path = serde_json::to_string(log_path).unwrap_or_else(|_| "null".into()),
    );
    if let Err(error) = window.eval(&script) {
        log::error!("could not give the page its connection: {error}");
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // What stops a second launch from becoming a second backend: every
        // plugin's own setup runs before the setup closure below, so the
        // second process ends before it reaches the spawn. Two backends
        // would bind two ports, open one database and append to one log,
        // and the one left behind would outlive the window that started it.
        //
        // First in the list by convention rather than by necessity. Moving
        // it below the shell plugin changes nothing here, because no other
        // plugin does work of its own in setup; it would matter to one that
        // did.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                // unminimize before set_focus: on Windows a minimized window
                // cannot take focus, so a user who minimized the app and
                // started it again would see nothing happen at all.
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // Both live in app-data, never beside the program: the install
            // folder is read-only for a normal user and an update replaces
            // it. Neither directory exists on a first run.
            let data_dir = app.path().app_data_dir()?;
            fs::create_dir_all(&data_dir)?;
            let log_dir = data_dir.join("logs");
            fs::create_dir_all(&log_dir)?;
            let database_path = data_dir.join("music.db");

            let token = launch_token();
            let backend = resource_path(app.handle(), BACKEND_EXE)?;
            log::info!("starting the backend at {}", backend.display());

            // Not with `?`. A missing backend is fatal; a missing fpcalc is
            // a mode the app already has: fpcalc_available answers false,
            // the comparison falls back to tags, and the window says so.
            // Leaving the variable unset lets the backend look on PATH,
            // which is how a run from source finds it.
            let mut command = app.shell().command(backend);
            match resource_path(app.handle(), FPCALC_EXE) {
                Ok(fpcalc) => {
                    command = command.env("ZAMLR_FPCALC", fpcalc.to_string_lossy().to_string());
                }
                Err(error) => log::warn!("fingerprinting will be unavailable: {error}"),
            }

            let (mut events, child) = command
                .env(
                    "ZAMLR_DATABASE_PATH",
                    database_path.to_string_lossy().to_string(),
                )
                .env("ZAMLR_LOG_DIR", log_dir.to_string_lossy().to_string())
                .env("ZAMLR_TOKEN", &token)
                .env("ZAMLR_ALLOWED_ORIGINS", allowed_origins())
                // The backend stops when this pipe closes, which is the only
                // signal that survives this process crashing. The kill below
                // covers the ordinary exit.
                .env("ZAMLR_WATCH_STDIN", "1")
                .spawn()?;

            app.manage(BackendChild(std::sync::Mutex::new(Some(child))));

            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let mut port: Option<u16> = None;
                let mut log_path: Option<String> = None;
                while let Some(event) = events.recv().await {
                    // Stderr and Terminated are reported, never dropped. A
                    // backend that dies on startup is otherwise perfectly
                    // silent here, and the only symptom is a splash that
                    // runs out its retries with nothing to explain it.
                    let line = match event {
                        CommandEvent::Stdout(bytes) => String::from_utf8_lossy(&bytes).to_string(),
                        CommandEvent::Stderr(bytes) => {
                            log::warn!("backend: {}", String::from_utf8_lossy(&bytes).trim_end());
                            continue;
                        }
                        CommandEvent::Terminated(payload) => {
                            log::error!("the backend stopped: {payload:?}");
                            break;
                        }
                        _ => continue,
                    };
                    if let Some(found) = parse_port_line(&line) {
                        port = Some(found);
                    } else if let Some(found) = parse_log_line(&line) {
                        log_path = Some(found.to_string());
                    }
                    // Only once both have arrived. The page needs the whole
                    // object, and a second injection would overwrite the
                    // first with a half-filled one.
                    if let (Some(port), Some(log_path)) = (port, log_path.as_deref()) {
                        if let Some(window) = handle.get_webview_window("main") {
                            inject_connection(&window, port, &token, log_path);
                        }
                        break;
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // Belt and braces. ZAMLR_WATCH_STDIN already stops the
                // backend when this process dies, including the crash this
                // handler never runs for.
                if let Some(state) = app.try_state::<BackendChild>() {
                    if let Ok(mut child) = state.0.lock() {
                        if let Some(child) = child.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}

struct BackendChild(std::sync::Mutex<Option<CommandChild>>);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_the_port() {
        assert_eq!(parse_port_line("ZAMLR_PORT=54321"), Some(54321));
    }

    #[test]
    fn parses_a_port_with_a_carriage_return() {
        // What the child actually writes on Windows. Without the trim this
        // is None, and the shell waits forever for a port it was told.
        assert_eq!(parse_port_line("ZAMLR_PORT=54321\r\n"), Some(54321));
    }

    #[test]
    fn ignores_another_line() {
        assert_eq!(parse_port_line("INFO: Started server process"), None);
    }

    #[test]
    fn ignores_a_port_that_is_not_a_number() {
        assert_eq!(parse_port_line("ZAMLR_PORT=garbage"), None);
    }

    #[test]
    fn parses_the_log_path() {
        // With the line ending the child really writes. Without it the trim
        // here has no test, and a path carrying \r\n reaches the page and
        // then the user, who is asked to find a file by that name.
        assert_eq!(
            parse_log_line("ZAMLR_LOG=C:\\Users\\x\\logs\\music-zamlr.log\r\n"),
            Some(r"C:\Users\x\logs\music-zamlr.log")
        );
    }

    #[test]
    fn ignores_a_log_line_that_is_something_else() {
        assert_eq!(parse_log_line("ZAMLR_PORT=54321"), None);
    }
}
