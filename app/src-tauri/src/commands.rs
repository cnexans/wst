use std::collections::HashMap;
use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Emitter, State, Window};

use crate::covers::CoverManager;
use crate::db::Db;
use crate::models::{Document, LibraryStats};

pub struct DbState(pub std::sync::Mutex<Db>);
pub struct CoverState(pub CoverManager);
pub struct LibraryPath(pub std::path::PathBuf);

/// Active `wst ingest --format ndjson` subprocesses, keyed by session id so
/// the GUI can cancel a running ingest. RFC 0013.
pub struct IngestSessions(pub Mutex<HashMap<String, Child>>);

#[tauri::command]
pub fn list_documents(
    doc_type: Option<String>,
    sort_by: Option<String>,
    topic: Option<String>,
    subject: Option<String>,
    state: State<DbState>,
) -> Result<Vec<Document>, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.list_all(
        doc_type.as_deref(),
        sort_by.as_deref().unwrap_or("title"),
        topic.as_deref(),
        subject.as_deref(),
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn search_documents(
    query: String,
    doc_type: Option<String>,
    topic: Option<String>,
    subject: Option<String>,
    state: State<DbState>,
) -> Result<Vec<Document>, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.search(&query, doc_type.as_deref(), topic.as_deref(), subject.as_deref())
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_subjects(state: State<DbState>) -> Result<Vec<String>, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.get_subjects().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_document(id: i64, state: State<DbState>) -> Result<Option<Document>, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.get(id).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_topics_vocabulary(state: State<DbState>) -> Result<Vec<String>, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.get_topics_vocabulary().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_library_stats(state: State<DbState>) -> Result<LibraryStats, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.get_library_stats().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_cover(id: i64, state: State<CoverState>) -> Option<String> {
    state.0.get_cover_filename(id)
}

#[tauri::command]
pub fn open_pdf(file_path: String, library_path: State<LibraryPath>) -> Result<(), String> {
    let full_path = library_path.0.join(&file_path);
    Command::new("open")
        .arg(full_path.to_str().unwrap())
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn reveal_in_finder(file_path: String, library_path: State<LibraryPath>) -> Result<(), String> {
    let full_path = library_path.0.join(&file_path);
    Command::new("open")
        .args(["-R", full_path.to_str().unwrap()])
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn run_wst_command(args: Vec<String>) -> Result<String, String> {
    let wst_path = which_wst();
    let output = Command::new(&wst_path)
        .args(&args)
        .output()
        .map_err(|e| format!("Failed to run wst: {}", e))?;

    if output.status.success() {
        String::from_utf8(output.stdout).map_err(|e| e.to_string())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

pub fn which_wst() -> String {
    // 1. Bundled sidecar: sibling to the app binary (inside .app/Contents/MacOS/)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let sidecar = dir.join("wst");
            if sidecar.exists() {
                return sidecar.to_string_lossy().to_string();
            }
        }
    }
    // 2. User-installed CLI (pipx / manual)
    let candidates = [
        dirs::home_dir().map(|h| h.join(".local/bin/wst")),
        Some(std::path::PathBuf::from("/usr/local/bin/wst")),
    ];
    for c in candidates.into_iter().flatten() {
        if c.exists() {
            return c.to_string_lossy().to_string();
        }
    }
    "wst".to_string()
}


// ---------------------------------------------------------------------------
// RFC 0013 — ingest from GUI via `wst ingest --format ndjson`
// ---------------------------------------------------------------------------

#[derive(serde::Deserialize, Default)]
pub struct IngestOpts {
    /// When true, pass `--ocr` to force OCR on every PDF. When false (default),
    /// the CLI auto-detects scanned PDFs and OCRs them only when ocrmypdf is
    /// installed (per Q4).
    #[serde(default)]
    pub force_ocr: bool,
}

#[derive(serde::Serialize, Default)]
pub struct IngestSummary {
    pub processed: u64,
    pub ingested: u64,
    pub skipped: u64,
    pub failed: u64,
    pub cleaned_inbox_removed: u64,
}

#[tauri::command]
pub async fn ingest_files(
    paths: Vec<String>,
    opts: Option<IngestOpts>,
    session_id: String,
    window: Window,
    sessions: State<'_, IngestSessions>,
) -> Result<IngestSummary, String> {
    let opts = opts.unwrap_or_default();
    let wst_path = which_wst();

    let mut args: Vec<String> = vec!["ingest".into(), "--format".into(), "ndjson".into()];
    if opts.force_ocr {
        args.push("--ocr".into());
    }
    args.extend(paths);

    let mut child = Command::new(&wst_path)
        .args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("failed to spawn wst: {e}"))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "missing stdout from wst".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "missing stderr from wst".to_string())?;

    // Park the Child handle in the session map so cancel_ingest can kill it.
    {
        let mut map = sessions.0.lock().map_err(|e| e.to_string())?;
        map.insert(session_id.clone(), child);
    }

    // Forward stderr lines as ingest:log events; drop the join handle (best-effort).
    let win_err = window.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines().map_while(Result::ok) {
            let _ = win_err.emit("ingest:log", line);
        }
    });

    // Parse stdout NDJSON line-by-line, emit ingest:file events as they land,
    // capture the final summary event.
    let win = window.clone();
    let parse_handle = tauri::async_runtime::spawn_blocking(
        move || -> Result<IngestSummary, String> {
            let reader = BufReader::new(stdout);
            let mut summary: Option<IngestSummary> = None;
            for line in reader.lines().map_while(Result::ok) {
                let value: serde_json::Value = match serde_json::from_str(&line) {
                    Ok(v) => v,
                    Err(_) => continue, // skip non-JSON noise (shouldn't happen, but harmless)
                };
                match value.get("event").and_then(|v| v.as_str()) {
                    Some("file") => {
                        let _ = win.emit("ingest:file", value);
                    }
                    Some("summary") => {
                        summary = Some(IngestSummary {
                            processed: value
                                .get("processed")
                                .and_then(|v| v.as_u64())
                                .unwrap_or(0),
                            ingested: value
                                .get("ingested")
                                .and_then(|v| v.as_u64())
                                .unwrap_or(0),
                            skipped: value
                                .get("skipped")
                                .and_then(|v| v.as_u64())
                                .unwrap_or(0),
                            failed: value
                                .get("failed")
                                .and_then(|v| v.as_u64())
                                .unwrap_or(0),
                            cleaned_inbox_removed: value
                                .get("cleaned_inbox_removed")
                                .and_then(|v| v.as_u64())
                                .unwrap_or(0),
                        });
                    }
                    _ => {}
                }
            }
            // Cancellation closes the pipe before a summary arrives — return zeros.
            Ok(summary.unwrap_or_default())
        },
    );

    let summary = parse_handle.await.map_err(|e| format!("parse task failed: {e}"))??;

    // Reap the child if it's still in the session map (i.e., ingest finished
    // naturally rather than via cancel_ingest).
    if let Ok(mut map) = sessions.0.lock() {
        if let Some(mut child) = map.remove(&session_id) {
            let _ = child.wait();
        }
    }

    Ok(summary)
}

#[tauri::command]
pub fn cancel_ingest(
    session_id: String,
    sessions: State<'_, IngestSessions>,
) -> Result<(), String> {
    let mut map = sessions.0.lock().map_err(|e| e.to_string())?;
    if let Some(mut child) = map.remove(&session_id) {
        child.kill().map_err(|e| format!("could not kill ingest session: {e}"))?;
        let _ = child.wait();
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// RFC 0016 — topics build from GUI (streaming via NDJSON)
// ---------------------------------------------------------------------------

#[derive(serde::Deserialize, Default)]
pub struct TopicsBuildOpts {
    /// Optional --n-topics override; None means auto-detect.
    pub n_topics: Option<u32>,
}

#[derive(serde::Serialize, Default)]
pub struct TopicsBuildResult {
    pub vocabulary: Vec<String>,
    pub assigned_count: u64,
    pub subjects_updated: u64,
}

#[tauri::command]
pub async fn build_topics(
    opts: Option<TopicsBuildOpts>,
    window: Window,
) -> Result<TopicsBuildResult, String> {
    let opts = opts.unwrap_or_default();
    let wst_path = which_wst();

    let mut args: Vec<String> = vec![
        "topics".into(),
        "build".into(),
        "--yes".into(),
        "--format".into(),
        "ndjson".into(),
    ];
    if let Some(n) = opts.n_topics {
        args.push("--n-topics".into());
        args.push(n.to_string());
    }

    let mut child = Command::new(&wst_path)
        .args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("failed to spawn wst: {e}"))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "missing stdout from wst".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "missing stderr from wst".to_string())?;

    let win_err = window.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines().map_while(Result::ok) {
            let _ = win_err.emit("topics:log", line);
        }
    });

    let win = window.clone();
    let parse_handle = tauri::async_runtime::spawn_blocking(
        move || -> Result<TopicsBuildResult, String> {
            let reader = BufReader::new(stdout);
            let mut result = TopicsBuildResult::default();
            for line in reader.lines().map_while(Result::ok) {
                let value: serde_json::Value = match serde_json::from_str(&line) {
                    Ok(v) => v,
                    Err(_) => continue,
                };
                let _ = win.emit("topics:event", value.clone());
                if value.get("event").and_then(|v| v.as_str()) == Some("done") {
                    result.vocabulary = value
                        .get("vocabulary")
                        .and_then(|v| v.as_array())
                        .map(|arr| {
                            arr.iter()
                                .filter_map(|x| x.as_str().map(|s| s.to_string()))
                                .collect()
                        })
                        .unwrap_or_default();
                    result.assigned_count = value
                        .get("assigned_count")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                    result.subjects_updated = value
                        .get("subjects_updated")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                }
            }
            Ok(result)
        },
    );

    let result = parse_handle
        .await
        .map_err(|e| format!("parse task failed: {e}"))??;
    let _ = child.wait();
    Ok(result)
}

#[tauri::command]
pub fn backup_to_icloud(library_path: State<LibraryPath>) -> Result<String, String> {
    let home = dirs::home_dir().ok_or("Could not determine home directory")?;
    let icloud_root = home.join("Library/Mobile Documents/com~apple~CloudDocs");
    if !icloud_root.exists() {
        return Err("iCloud Drive is not available on this system".to_string());
    }

    let dest = icloud_root.join("WanShiTong");
    std::fs::create_dir_all(&dest).map_err(|e| format!("Failed to create destination folder: {}", e))?;

    // Copy wst.db
    let src_db = library_path.0.join("wst.db");
    let dest_db = dest.join("wst.db");
    std::fs::copy(&src_db, &dest_db)
        .map_err(|e| format!("Failed to copy wst.db: {}", e))?;

    // Copy .covers/ recursively (only if it exists)
    let src_covers = library_path.0.join(".covers");
    if src_covers.exists() {
        let dest_covers = dest.join(".covers");
        copy_dir_all(&src_covers, &dest_covers)
            .map_err(|e| format!("Failed to copy .covers: {}", e))?;
    }

    Ok(dest.to_string_lossy().to_string())
}

fn copy_dir_all(src: &std::path::Path, dst: &std::path::Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let dest_path = dst.join(entry.file_name());
        if file_type.is_dir() {
            copy_dir_all(&entry.path(), &dest_path)?;
        } else {
            std::fs::copy(entry.path(), dest_path)?;
        }
    }
    Ok(())
}
