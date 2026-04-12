use rusqlite::{Connection, OpenFlags, Result, params};
use std::path::PathBuf;

use crate::models::{DocTypeCount, Document, LibraryStats};

pub struct Db {
    conn: Connection,
}

impl Db {
    pub fn open(db_path: &PathBuf) -> Result<Self> {
        let conn = Connection::open_with_flags(
            db_path,
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )?;
        conn.pragma_update(None, "journal_mode", "wal")?;
        Ok(Db { conn })
    }

    pub fn list_all(&self, doc_type: Option<&str>, sort_by: &str) -> Result<Vec<Document>> {
        let sort_col = match sort_by {
            "author" => "author",
            "year" => "year",
            "ingested_at" => "ingested_at",
            _ => "title",
        };

        let (sql, params_vec): (String, Vec<Box<dyn rusqlite::types::ToSql>>) = match doc_type {
            Some(dt) => (
                format!("SELECT * FROM documents WHERE doc_type = ? ORDER BY {sort_col}"),
                vec![Box::new(dt.to_string())],
            ),
            None => (
                format!("SELECT * FROM documents ORDER BY {sort_col}"),
                vec![],
            ),
        };

        let mut stmt = self.conn.prepare(&sql)?;
        let params_refs: Vec<&dyn rusqlite::types::ToSql> = params_vec.iter().map(|p| p.as_ref()).collect();
        let rows = stmt.query_map(params_refs.as_slice(), |row| self.row_to_document(row))?;

        rows.collect()
    }

    pub fn search(
        &self,
        query: &str,
        doc_type: Option<&str>,
        author: Option<&str>,
        subject: Option<&str>,
    ) -> Result<Vec<Document>> {
        let mut sql = String::from(
            "SELECT d.* FROM documents d \
             JOIN documents_fts f ON d.id = f.rowid \
             WHERE documents_fts MATCH ?1",
        );
        let mut params_vec: Vec<Box<dyn rusqlite::types::ToSql>> =
            vec![Box::new(query.to_string())];
        let mut idx = 2;

        if let Some(dt) = doc_type {
            sql.push_str(&format!(" AND d.doc_type = ?{idx}"));
            params_vec.push(Box::new(dt.to_string()));
            idx += 1;
        }
        if let Some(a) = author {
            sql.push_str(&format!(" AND d.author LIKE ?{idx}"));
            params_vec.push(Box::new(format!("%{a}%")));
            idx += 1;
        }
        if let Some(s) = subject {
            sql.push_str(&format!(" AND d.subject LIKE ?{idx}"));
            params_vec.push(Box::new(format!("%{s}%")));
            let _ = idx;
        }

        sql.push_str(" ORDER BY rank");

        let mut stmt = self.conn.prepare(&sql)?;
        let params_refs: Vec<&dyn rusqlite::types::ToSql> =
            params_vec.iter().map(|p| p.as_ref()).collect();
        let rows = stmt.query_map(params_refs.as_slice(), |row| self.row_to_document(row))?;

        rows.collect()
    }

    pub fn get(&self, id: i64) -> Result<Option<Document>> {
        let mut stmt = self.conn.prepare("SELECT * FROM documents WHERE id = ?1")?;
        let mut rows = stmt.query_map(params![id], |row| self.row_to_document(row))?;
        Ok(rows.next().transpose()?)
    }

    pub fn get_library_stats(&self) -> Result<LibraryStats> {
        let total: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM documents", [], |row| row.get(0))?;

        let mut stmt = self
            .conn
            .prepare("SELECT doc_type, COUNT(*) as cnt FROM documents GROUP BY doc_type ORDER BY cnt DESC")?;
        let by_type = stmt
            .query_map([], |row| {
                Ok(DocTypeCount {
                    doc_type: row.get(0)?,
                    count: row.get(1)?,
                })
            })?
            .collect::<Result<Vec<_>>>()?;

        Ok(LibraryStats { total, by_type })
    }

    fn row_to_document(&self, row: &rusqlite::Row) -> Result<Document> {
        let tags_json: String = row.get::<_, Option<String>>("tags")?.unwrap_or_default();
        let tags: Vec<String> = serde_json::from_str(&tags_json).unwrap_or_default();

        Ok(Document {
            id: row.get("id")?,
            title: row.get("title")?,
            author: row.get("author")?,
            doc_type: row.get("doc_type")?,
            year: row.get("year")?,
            publisher: row.get("publisher")?,
            isbn: row.get("isbn")?,
            language: row.get("language")?,
            tags,
            page_count: row.get("page_count")?,
            summary: row.get("summary")?,
            toc: row.get("toc")?,
            subject: row.get("subject")?,
            filename: row.get("filename")?,
            original_filename: row.get("original_filename")?,
            file_path: row.get("file_path")?,
            file_hash: row.get("file_hash")?,
            ingested_at: row.get("ingested_at")?,
        })
    }
}
