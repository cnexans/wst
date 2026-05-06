import { createSignal } from "solid-js";
import type { Document, LibraryStats } from "./types";
import {
  getLibraryStats,
  getSubjects,
  getTopicsVocabulary,
  listDocuments,
} from "./tauri";

export const [documents, setDocuments] = createSignal<Document[]>([]);
export const [searchQuery, setSearchQuery] = createSignal("");
export const [activeDocType, setActiveDocType] = createSignal<string | null>(null);
export const [activeTopic, setActiveTopic] = createSignal<string | null>(null);
export const [activeSubject, setActiveSubject] = createSignal<string | null>(null);
export const [viewMode, setViewMode] = createSignal<"grid" | "list">("grid");
export const [sortBy, setSortBy] = createSignal("title");
export const [selectedDoc, setSelectedDoc] = createSignal<Document | null>(null);
export const [libraryStats, setLibraryStats] = createSignal<LibraryStats>({
  total: 0,
  by_type: [],
});
export const [covers, setCovers] = createSignal<Record<number, string>>({});
export const [allTopicsVocab, setAllTopicsVocab] = createSignal<string[]>([]);
export const [allSubjects, setAllSubjects] = createSignal<string[]>([]);

export function setCover(id: number, path: string) {
  setCovers((prev) => ({ ...prev, [id]: path }));
}

export function clearAllFilters() {
  setActiveDocType(null);
  setActiveTopic(null);
  setActiveSubject(null);
}

/**
 * Re-fetch documents, stats, topic vocab, and subjects from the backend.
 * Call this after operations that mutate the library: ingest (RFC 0013),
 * OCR or topics build (RFC 0016).
 */
export async function refreshLibraryState(): Promise<void> {
  const [stats, docs, vocab, subjects] = await Promise.all([
    getLibraryStats(),
    listDocuments(),
    getTopicsVocabulary(),
    getSubjects(),
  ]);
  setLibraryStats(stats);
  setDocuments(docs);
  setAllTopicsVocab(vocab);
  setAllSubjects(subjects);
}
