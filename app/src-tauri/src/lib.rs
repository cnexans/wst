mod commands;
mod covers;
mod db;
mod models;

use commands::{CoverState, DbState, LibraryPath};
use covers::CoverManager;
use db::Db;
use std::path::PathBuf;

fn get_library_path() -> PathBuf {
    let home = dirs::home_dir().expect("could not find home directory");
    // Try reading config.json first
    let config_path = home.join(".wst").join("config.json");
    if config_path.exists() {
        if let Ok(content) = std::fs::read_to_string(&config_path) {
            if let Ok(config) = serde_json::from_str::<serde_json::Value>(&content) {
                if let Some(path) = config.get("library_path").and_then(|v| v.as_str()) {
                    return PathBuf::from(path);
                }
            }
        }
    }
    home.join("wst").join("library")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let library_path = get_library_path();
    let db_path = library_path.join("wst.db");

    let db = Db::open(&db_path).expect("failed to open database");
    let cover_manager = CoverManager::new(library_path.clone());

    tauri::Builder::default()
        .manage(DbState(std::sync::Mutex::new(db)))
        .manage(CoverState(cover_manager))
        .manage(LibraryPath(library_path))
        .invoke_handler(tauri::generate_handler![
            commands::list_documents,
            commands::search_documents,
            commands::get_document,
            commands::get_library_stats,
            commands::get_cover,
            commands::ensure_cover,
            commands::open_pdf,
            commands::reveal_in_finder,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Wan Shi Tong");
}
