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
    title, author, tags, subject, summary,
    content='documents',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, author, tags, subject, summary)
    VALUES (new.id, new.title, new.author, new.tags, new.subject, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, title, author, tags, subject, summary)
    VALUES ('delete', old.id, old.title, old.author, old.tags, old.subject, old.summary);
END;
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.executescript(FTS_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def exists_hash(self, file_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM documents WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return row is not None

    def insert(self, entry: LibraryEntry) -> int:
        m = entry.metadata
        cur = self.conn.execute(
            """INSERT INTO documents
               (title, author, doc_type, year, publisher, isbn, language,
                tags, page_count, summary, toc, subject,
                filename, original_filename, file_path, file_hash, ingested_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                m.title,
                m.author,
                m.doc_type.value,
                m.year,
                m.publisher,
                m.isbn,
                m.language,
                json.dumps(m.tags),
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
        self, query: str, doc_type: str | None = None, author: str | None = None
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

    def get(self, doc_id: int) -> LibraryEntry | None:
        row = self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return self._row_to_entry(row) if row else None

    def get_by_title(self, title: str) -> LibraryEntry | None:
        row = self.conn.execute(
            "SELECT * FROM documents WHERE title LIKE ? LIMIT 1", (f"%{title}%",)
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def _row_to_entry(self, row: sqlite3.Row) -> LibraryEntry:
        tags = json.loads(row["tags"]) if row["tags"] else []
        meta = DocumentMetadata(
            title=row["title"],
            author=row["author"],
            doc_type=DocType(row["doc_type"]),
            year=row["year"],
            publisher=row["publisher"],
            isbn=row["isbn"],
            language=row["language"],
            tags=tags,
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
