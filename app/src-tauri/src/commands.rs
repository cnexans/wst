use std::process::Command;
use tauri::State;

use crate::covers::CoverManager;
use crate::db::Db;
use crate::models::{Document, LibraryStats};

pub struct DbState(pub std::sync::Mutex<Db>);
pub struct CoverState(pub CoverManager);
pub struct LibraryPath(pub std::path::PathBuf);

#[tauri::command]
pub fn list_documents(
    doc_type: Option<String>,
    sort_by: Option<String>,
    topic: Option<String>,
    state: State<DbState>,
) -> Result<Vec<Document>, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.list_all(
        doc_type.as_deref(),
        sort_by.as_deref().unwrap_or("title"),
        topic.as_deref(),
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn search_documents(
    query: String,
    doc_type: Option<String>,
    topic: Option<String>,
    state: State<DbState>,
) -> Result<Vec<Document>, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.search(&query, doc_type.as_deref(), topic.as_deref(), None, None)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_document(id: i64, state: State<DbState>) -> Result<Option<Document>, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.get(id).map_err(|e| e.to_string())
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

fn which_wst() -> String {
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
