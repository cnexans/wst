from enum import StrEnum

from pydantic import BaseModel, Field


class DocType(StrEnum):
    BOOK = "book"
    NOVEL = "novel"
    TEXTBOOK = "textbook"
    PAPER = "paper"
    CLASS_NOTES = "class-notes"
    EXERCISES = "exercises"
    GUIDE_THEORY = "guide-theory"
    GUIDE_PRACTICE = "guide-practice"


DOCTYPE_FOLDER: dict[DocType, str] = {
    DocType.BOOK: "libros",
    DocType.NOVEL: "libros",
    DocType.TEXTBOOK: "libros",
    DocType.PAPER: "papers",
    DocType.CLASS_NOTES: "notas",
    DocType.EXERCISES: "ejercicios",
    DocType.GUIDE_THEORY: "guias",
    DocType.GUIDE_PRACTICE: "guias",
}


class DocumentMetadata(BaseModel):
    title: str
    author: str
    doc_type: DocType
    year: int | None = None
    publisher: str | None = None
    isbn: str | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
    page_count: int | None = None
    summary: str | None = None
    table_of_contents: str | None = None
    subject: str | None = None


class LibraryEntry(BaseModel):
    id: int | None = None
    metadata: DocumentMetadata
    filename: str
    original_filename: str
    file_path: str
    file_hash: str
    ingested_at: str
