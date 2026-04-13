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
    state: State<DbState>,
) -> Result<Vec<Document>, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.list_all(doc_type.as_deref(), sort_by.as_deref().unwrap_or("title"))
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn search_documents(
    query: String,
    doc_type: Option<String>,
    state: State<DbState>,
) -> Result<Vec<Document>, String> {
    let db = state.0.lock().map_err(|e| e.to_string())?;
    db.search(&query, doc_type.as_deref(), None, None)
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
