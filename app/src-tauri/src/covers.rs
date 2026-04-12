use std::path::PathBuf;
use std::process::Command;
use tokio::sync::Semaphore;

const OPENLIBRARY_URL: &str = "https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg";
const MIN_COVER_SIZE: usize = 100;

pub struct CoverManager {
    covers_dir: PathBuf,
    library_path: PathBuf,
    client: reqwest::Client,
    semaphore: Semaphore,
}

impl CoverManager {
    pub fn new(library_path: PathBuf) -> Self {
        let covers_dir = library_path.join(".covers");
        std::fs::create_dir_all(&covers_dir).ok();

        Self {
            covers_dir,
            library_path,
            client: reqwest::Client::builder()
                .user_agent("wst-library/0.6.0")
                .build()
                .expect("failed to build HTTP client"),
            semaphore: Semaphore::new(10),
        }
    }

    pub fn get_cached(&self, doc_id: i64) -> Option<String> {
        let path = self.cover_path(doc_id);
        if path.exists() {
            Some(path.to_string_lossy().to_string())
        } else {
            None
        }
    }

    pub async fn ensure_cover(
        &self,
        doc_id: i64,
        isbn: Option<&str>,
        file_path: &str,
    ) -> Option<String> {
        if let Some(cached) = self.get_cached(doc_id) {
            return Some(cached);
        }

        let _permit = self.semaphore.acquire().await.ok()?;
        let cover_path = self.cover_path(doc_id);

        // Try Open Library by ISBN
        if let Some(isbn) = isbn {
            if let Some(data) = self.fetch_by_isbn(isbn).await {
                std::fs::write(&cover_path, data).ok()?;
                return Some(cover_path.to_string_lossy().to_string());
            }
        }

        // Fallback: render PDF first page
        let pdf_path = self.library_path.join(file_path);
        if pdf_path.exists() {
            if self.render_pdf_thumbnail(&pdf_path, &cover_path) {
                return Some(cover_path.to_string_lossy().to_string());
            }
        }

        None
    }

    async fn fetch_by_isbn(&self, isbn: &str) -> Option<Vec<u8>> {
        let clean_isbn = isbn.replace('-', "");
        let url = OPENLIBRARY_URL.replace("{isbn}", &clean_isbn);

        let resp = self.client.get(&url).send().await.ok()?;
        if !resp.status().is_success() {
            return None;
        }

        let bytes = resp.bytes().await.ok()?;
        if bytes.len() > MIN_COVER_SIZE {
            Some(bytes.to_vec())
        } else {
            None
        }
    }

    fn render_pdf_thumbnail(&self, pdf_path: &PathBuf, output_path: &PathBuf) -> bool {
        // Use macOS qlmanage for quick thumbnail generation
        let result = Command::new("qlmanage")
            .args([
                "-t",
                "-s",
                "300",
                "-o",
                output_path.parent().unwrap().to_str().unwrap(),
                pdf_path.to_str().unwrap(),
            ])
            .output();

        if let Ok(output) = result {
            if output.status.success() {
                // qlmanage creates file with .png extension appended
                let ql_output = PathBuf::from(format!(
                    "{}.png",
                    pdf_path.file_name().unwrap().to_string_lossy()
                ));
                let ql_path = output_path.parent().unwrap().join(ql_output);

                if ql_path.exists() {
                    // Rename to our expected path
                    std::fs::rename(&ql_path, output_path).ok();
                    return true;
                }
            }
        }

        // Fallback: use sips to convert first page
        let result = Command::new("sips")
            .args([
                "-s",
                "format",
                "jpeg",
                "-Z",
                "300",
                pdf_path.to_str().unwrap(),
                "--out",
                output_path.to_str().unwrap(),
            ])
            .output();

        matches!(result, Ok(output) if output.status.success())
    }

    fn cover_path(&self, doc_id: i64) -> PathBuf {
        self.covers_dir.join(format!("{doc_id}.jpg"))
    }
}
