import { invoke } from "@tauri-apps/api/core";
import type { Document, LibraryStats } from "./types";

export async function listDocuments(
  docType?: string,
  sortBy?: string
): Promise<Document[]> {
  return invoke("list_documents", {
    docType: docType ?? null,
    sortBy: sortBy ?? null,
  });
}

export async function searchDocuments(
  query: string,
  docType?: string
): Promise<Document[]> {
  return invoke("search_documents", {
    query,
    docType: docType ?? null,
    author: null,
    subject: null,
  });
}

export async function getDocument(id: number): Promise<Document | null> {
  return invoke("get_document", { id });
}

export async function getLibraryStats(): Promise<LibraryStats> {
  return invoke("get_library_stats");
}

export async function getCover(id: number): Promise<string | null> {
  return invoke("get_cover", { id });
}

export async function ensureCover(
  id: number,
  isbn: string | null,
  filePath: string
): Promise<string | null> {
  return invoke("ensure_cover", { id, isbn, filePath });
}

export async function openPdf(filePath: string): Promise<void> {
  return invoke("open_pdf", { filePath });
}

export async function revealInFinder(filePath: string): Promise<void> {
  return invoke("reveal_in_finder", { filePath });
}
