from enum import StrEnum

from pydantic import BaseModel, Field


class DocType(StrEnum):
    BOOK = "book"
    PAPER = "paper"
    GUIDE_THEORY = "guide-theory"
    GUIDE_PRACTICE = "guide-practice"


DOCTYPE_FOLDER: dict[DocType, str] = {
    DocType.BOOK: "books",
    DocType.PAPER: "papers",
    DocType.GUIDE_THEORY: "guides",
    DocType.GUIDE_PRACTICE: "guides",
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
    topics: list[str] = Field(default_factory=list)
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
