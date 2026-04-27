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

    let covers_dir = library_path.join(".covers");

    tauri::Builder::default()
        .manage(DbState(std::sync::Mutex::new(db)))
        .manage(CoverState(cover_manager))
        .manage(LibraryPath(library_path))
        .register_uri_scheme_protocol("covers", move |_ctx, request| {
            let path = request.uri().path().trim_start_matches('/');
            let file_path = covers_dir.join(path);

            if file_path.exists() {
                let bytes = std::fs::read(&file_path).unwrap_or_default();
                let mime = if path.ends_with(".png") {
                    "image/png"
                } else {
                    "image/jpeg"
                };
                tauri::http::Response::builder()
                    .header("Content-Type", mime)
                    .header("Cache-Control", "public, max-age=31536000, immutable")
                    .body(bytes)
                    .unwrap()
            } else {
                tauri::http::Response::builder()
                    .status(404)
                    .body(Vec::new())
                    .unwrap()
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::list_documents,
            commands::search_documents,
            commands::get_document,
            commands::get_library_stats,
            commands::get_topics_vocabulary,
            commands::get_subjects,
            commands::get_cover,
            commands::open_pdf,
            commands::reveal_in_finder,
            commands::run_wst_command,
            commands::backup_document_to_icloud,
            commands::backup_to_icloud,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Wan Shi Tong");
}
