use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Document {
    pub id: i64,
    pub title: String,
    pub author: String,
    pub doc_type: String,
    pub year: Option<i32>,
    pub publisher: Option<String>,
    pub isbn: Option<String>,
    pub language: Option<String>,
    pub tags: Vec<String>,
    pub topics: Vec<String>,
    pub page_count: Option<i32>,
    pub summary: Option<String>,
    pub toc: Option<String>,
    pub subject: Option<String>,
    pub filename: String,
    pub original_filename: String,
    pub file_path: String,
    pub file_hash: String,
    pub ingested_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocTypeCount {
    pub doc_type: String,
    pub count: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LibraryStats {
    pub total: i64,
    pub by_type: Vec<DocTypeCount>,
}
