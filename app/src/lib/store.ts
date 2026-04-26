import { createSignal } from "solid-js";
import type { Document, LibraryStats } from "./types";

export const [documents, setDocuments] = createSignal<Document[]>([]);
export const [searchQuery, setSearchQuery] = createSignal("");
export const [activeDocType, setActiveDocType] = createSignal<string | null>(
  null
);
export const [activeTopic, setActiveTopic] = createSignal<string | null>(null);
export const [viewMode, setViewMode] = createSignal<"grid" | "list">("grid");
export const [sortBy, setSortBy] = createSignal("title");
export const [selectedDoc, setSelectedDoc] = createSignal<Document | null>(
  null
);
export const [libraryStats, setLibraryStats] = createSignal<LibraryStats>({
  total: 0,
  by_type: [],
});
export const [covers, setCovers] = createSignal<Record<number, string>>({});

export function setCover(id: number, path: string) {
  setCovers((prev) => ({ ...prev, [id]: path }));
}
