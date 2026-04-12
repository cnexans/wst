import { createEffect, onMount, Show } from "solid-js";
import {
  documents,
  setDocuments,
  searchQuery,
  activeDocType,
  sortBy,
  viewMode,
  setLibraryStats,
} from "./lib/store";
import { listDocuments, searchDocuments, getLibraryStats } from "./lib/tauri";
import SearchBar from "./components/SearchBar";
import Sidebar from "./components/Sidebar";
import Toolbar from "./components/Toolbar";
import BookGrid from "./components/BookGrid";
import BookList from "./components/BookList";
import BookDetail from "./components/BookDetail";

export default function App() {
  onMount(async () => {
    const stats = await getLibraryStats();
    setLibraryStats(stats);
    const docs = await listDocuments();
    setDocuments(docs);
  });

  // Reactive: re-fetch when filters change
  createEffect(() => {
    const query = searchQuery();
    const docType = activeDocType();
    const sort = sortBy();

    let debounce: number | undefined;

    const fetch = async () => {
      if (query.trim()) {
        const results = await searchDocuments(query, docType ?? undefined);
        setDocuments(results);
      } else {
        const results = await listDocuments(docType ?? undefined, sort);
        setDocuments(results);
      }
    };

    if (query) {
      debounce = window.setTimeout(fetch, 150);
    } else {
      fetch();
    }

    return () => clearTimeout(debounce);
  });

  return (
    <div class="app">
      <header class="app-header">
        <SearchBar />
      </header>
      <div class="app-body">
        <Sidebar />
        <main class="app-main">
          <Toolbar />
          <Show when={viewMode() === "grid"} fallback={<BookList />}>
            <BookGrid />
          </Show>
        </main>
      </div>
      <BookDetail />
    </div>
  );
}
