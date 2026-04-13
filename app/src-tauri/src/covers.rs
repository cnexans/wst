use std::path::PathBuf;

pub struct CoverManager {
    covers_dir: PathBuf,
}

impl CoverManager {
    pub fn new(library_path: PathBuf) -> Self {
        let covers_dir = library_path.join(".covers");
        Self { covers_dir }
    }

    pub fn get_cover_filename(&self, doc_id: i64) -> Option<String> {
        for ext in &["jpg", "png"] {
            let path = self.covers_dir.join(format!("{doc_id}.{ext}"));
            if path.exists() {
                return Some(format!("{doc_id}.{ext}"));
            }
        }
        None
    }
}
