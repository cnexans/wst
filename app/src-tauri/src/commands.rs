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
