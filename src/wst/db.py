import json
import sqlite3
from pathlib import Path

from wst.models import DocType, DocumentMetadata, LibraryEntry

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    author            TEXT NOT NULL,
    doc_type          TEXT NOT NULL,
    year              INTEGER,
    publisher         TEXT,
    isbn              TEXT,
    language          TEXT,
    tags              TEXT,
    topics            TEXT,
    page_count        INTEGER,
    summary           TEXT,
    toc               TEXT,
    subject           TEXT,
    filename          TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_path         TEXT NOT NULL UNIQUE,
    file_hash         TEXT NOT NULL UNIQUE,
    ingested_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_author ON documents(author);
CREATE INDEX IF NOT EXISTS idx_doc_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_year ON documents(year);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, author, tags, topics, subject, summary,
    content='documents',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, author, tags, topics, subject, summary)
    VALUES (new.id, new.title, new.author, new.tags, new.topics, new.subject, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, author, tags, topics, subject, summary)
    VALUES (
        'delete', old.id, old.title, old.author, old.tags, old.topics, old.subject, old.summary
    );
END;
"""

TOPICS_VOCABULARY_SCHEMA = """
CREATE TABLE IF NOT EXISTS topics_vocabulary (
    id      INTEGER PRIMARY KEY CHECK (id = 1),
    topics  TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

EMBEDDINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    doc_id     INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    embedding  BLOB NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _has_fts_column(conn: sqlite3.Connection, column: str) -> bool:
    """Check if a column exists in the FTS table by inspecting its schema."""
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents_fts'"
        ).fetchone()
        if row is None:
            return False
        return column in (row["sql"] or "")
    except Exception:
        return False


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        # Add topics column to documents if it doesn't exist (migration for old DBs)
        if not _has_column(self.conn, "documents", "topics"):
            self.conn.execute("ALTER TABLE documents ADD COLUMN topics TEXT")
            self.conn.commit()

        # Ensure FTS table has topics column; rebuild if missing
        if not _has_fts_column(self.conn, "topics"):
            self._rebuild_fts()
        else:
            self.conn.executescript(FTS_SCHEMA)

        self.conn.executescript(TOPICS_VOCABULARY_SCHEMA)
        self.conn.executescript(EMBEDDINGS_SCHEMA)

    def _rebuild_fts(self) -> None:
        """Drop and recreate FTS table with the current schema, then repopulate."""
        self.conn.executescript("""
            DROP TRIGGER IF EXISTS documents_ai;
            DROP TRIGGER IF EXISTS documents_ad;
            DROP TABLE IF EXISTS documents_fts;
        """)
        self.conn.executescript(FTS_SCHEMA)
        # Repopulate FTS from documents table
        rows = self.conn.execute(
            "SELECT id, title, author, tags, topics, subject, summary FROM documents"
        ).fetchall()
        for row in rows:
            self.conn.execute(
                "INSERT INTO documents_fts(rowid, title, author, tags, topics, subject, summary)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    row["title"],
                    row["author"],
                    row["tags"],
                    row["topics"],
                    row["subject"],
                    row["summary"],
                ),
            )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def exists_hash(self, file_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM documents WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return row is not None

    def delete_by_hash(self, file_hash: str) -> str | None:
        """Delete entry by hash. Returns the file_path if found, None otherwise."""
        row = self.conn.execute(
            "SELECT id, file_path FROM documents WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        if row is None:
            return None
        self.conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
        self.conn.commit()
        return row["file_path"]

    def delete(self, doc_id: int) -> str | None:
        """Delete entry by ID. Returns the file_path if found, None otherwise."""
        row = self.conn.execute(
            "SELECT file_path FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        if row is None:
            return None
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.commit()
        return row["file_path"]

    def insert(self, entry: LibraryEntry) -> int:
        m = entry.metadata
        cur = self.conn.execute(
            """INSERT INTO documents
               (title, author, doc_type, year, publisher, isbn, language,
                tags, topics, page_count, summary, toc, subject,
                filename, original_filename, file_path, file_hash, ingested_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                m.title,
                m.author,
                m.doc_type.value,
                m.year,
                m.publisher,
                m.isbn,
                m.language,
                json.dumps(m.tags),
                json.dumps(m.topics),
                m.page_count,
                m.summary,
                m.table_of_contents,
                m.subject,
                entry.filename,
                entry.original_filename,
                entry.file_path,
                entry.file_hash,
                entry.ingested_at,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def search(
        self,
        query: str,
        doc_type: str | None = None,
        author: str | None = None,
        subject: str | None = None,
        topic: str | None = None,
    ) -> list[LibraryEntry]:
        if query:
            sql = """SELECT d.* FROM documents d
                     JOIN documents_fts f ON d.id = f.rowid
                     WHERE documents_fts MATCH ?"""
            params: list = [query]
        else:
            sql = "SELECT * FROM documents d WHERE 1=1"
            params = []

        if doc_type:
            sql += " AND d.doc_type = ?"
            params.append(doc_type)
        if author:
            sql += " AND d.author LIKE ?"
            params.append(f"%{author}%")
        if subject:
            sql += " AND d.subject LIKE ?"
            params.append(f"%{subject}%")
        if topic:
            sql += " AND LOWER(d.topics) LIKE LOWER(?)"
            params.append(f"%{topic}%")

        sql += " ORDER BY d.title"
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def list_all(self, doc_type: str | None = None, sort_by: str = "title") -> list[LibraryEntry]:
        sql = "SELECT * FROM documents"
        params: list = []
        if doc_type:
            sql += " WHERE doc_type = ?"
            params.append(doc_type)

        valid_sorts = {"title", "author", "year", "ingested_at"}
        col = sort_by if sort_by in valid_sorts else "title"
        sql += f" ORDER BY {col}"

        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def update(self, entry: LibraryEntry) -> None:
        m = entry.metadata
        # Fetch the CURRENT row values so we can remove the exact FTS entry that was inserted
        old_row = self.conn.execute(
            "SELECT title, author, tags, topics, subject, summary FROM documents WHERE id = ?",
            (entry.id,),
        ).fetchone()
        if old_row is not None:
            fts_del = (
                "INSERT INTO documents_fts"
                "(documents_fts, rowid, title, author, tags, topics, subject, summary) "
                "VALUES ('delete', ?, ?, ?, ?, ?, ?, ?)"
            )
            self.conn.execute(
                fts_del,
                (
                    entry.id,
                    old_row["title"],
                    old_row["author"],
                    old_row["tags"],
                    old_row["topics"],
                    old_row["subject"],
                    old_row["summary"],
                ),
            )
        self.conn.execute(
            """UPDATE documents SET
               title=?, author=?, doc_type=?, year=?, publisher=?, isbn=?,
               language=?, tags=?, topics=?, page_count=?, summary=?, toc=?, subject=?,
               filename=?, file_path=?
               WHERE id=?""",
            (
                m.title,
                m.author,
                m.doc_type.value,
                m.year,
                m.publisher,
                m.isbn,
                m.language,
                json.dumps(m.tags),
                json.dumps(m.topics),
                m.page_count,
                m.summary,
                m.table_of_contents,
                m.subject,
                entry.filename,
                entry.file_path,
                entry.id,
            ),
        )
        # Re-insert FTS entry with new values
        self.conn.execute(
            "INSERT INTO documents_fts(rowid, title, author, tags, topics, subject, summary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                entry.id,
                m.title,
                m.author,
                json.dumps(m.tags),
                json.dumps(m.topics),
                m.subject,
                m.summary,
            ),
        )
        self.conn.commit()

    def get(self, doc_id: int) -> LibraryEntry | None:
        row = self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return self._row_to_entry(row) if row else None

    def get_by_title(self, title: str) -> LibraryEntry | None:
        row = self.conn.execute(
            "SELECT * FROM documents WHERE title LIKE ? LIMIT 1", (f"%{title}%",)
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def save_topics_vocabulary(self, vocabulary: list[str]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO topics_vocabulary(id, topics, updated_at)"
            " VALUES (1, ?, datetime('now'))",
            (json.dumps(vocabulary),),
        )
        self.conn.commit()

    def load_topics_vocabulary(self) -> list[str] | None:
        row = self.conn.execute("SELECT topics FROM topics_vocabulary WHERE id = 1").fetchone()
        if row is None:
            return None
        return json.loads(row["topics"])

    # ------------------------------------------------------------------
    # Embeddings (semantic search index)
    # ------------------------------------------------------------------

    def upsert_embedding(self, doc_id: int, embedding_bytes: bytes) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO embeddings(doc_id, embedding, updated_at)"
            " VALUES (?, ?, datetime('now'))",
            (doc_id, embedding_bytes),
        )
        self.conn.commit()

    def load_all_embeddings(self) -> dict[int, bytes]:
        rows = self.conn.execute("SELECT doc_id, embedding FROM embeddings").fetchall()
        return {row["doc_id"]: bytes(row["embedding"]) for row in rows}

    def count_embeddings(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM embeddings").fetchone()
        return row["n"] if row else 0

    def get_by_ids(self, doc_ids: list[int]) -> list[LibraryEntry]:
        if not doc_ids:
            return []
        placeholders = ",".join("?" * len(doc_ids))
        rows = self.conn.execute(
            f"SELECT * FROM documents WHERE id IN ({placeholders})", doc_ids
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def _row_to_entry(self, row: sqlite3.Row) -> LibraryEntry:
        tags = json.loads(row["tags"]) if row["tags"] else []
        # topics column may not exist in very old DB rows (defensive)
        try:
            topics = json.loads(row["topics"]) if row["topics"] else []
        except (IndexError, KeyError):
            topics = []
        meta = DocumentMetadata(
            title=row["title"],
            author=row["author"],
            doc_type=DocType(row["doc_type"]),
            year=row["year"],
            publisher=row["publisher"],
            isbn=row["isbn"],
            language=row["language"],
            tags=tags,
            topics=topics,
            page_count=row["page_count"],
            summary=row["summary"],
            table_of_contents=row["toc"],
            subject=row["subject"],
        )
        return LibraryEntry(
            id=row["id"],
            metadata=meta,
            filename=row["filename"],
            original_filename=row["original_filename"],
            file_path=row["file_path"],
            file_hash=row["file_hash"],
            ingested_at=row["ingested_at"],
        )
