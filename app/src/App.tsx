import { createEffect, onMount, Show, on, createSignal } from "solid-js";
import {
  setDocuments,
  searchQuery,
  activeDocType,
  activeTopic,
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
  let debounceTimer: number | undefined;
  let fetchId = 0;
  const [fading, setFading] = createSignal(false);

  onMount(async () => {
    const [stats, docs] = await Promise.all([
      getLibraryStats(),
      listDocuments(),
    ]);
    setLibraryStats(stats);
    setDocuments(docs);
  });

  createEffect(
    on(
      [searchQuery, activeDocType, activeTopic, sortBy],
      ([query, docType, topic, sort]) => {
      clearTimeout(debounceTimer);
      const currentFetch = ++fetchId;

      const doFetch = async () => {
        try {
          let results;
          if (query.trim()) {
            results = await searchDocuments(
              query,
              docType ?? undefined,
              topic ?? undefined
            );
          } else {
            results = await listDocuments(
              docType ?? undefined,
              sort,
              topic ?? undefined
            );
          }
          // Only apply if this is still the latest fetch
          if (currentFetch === fetchId) {
            setFading(true);
            requestAnimationFrame(() => {
              setDocuments(results);
              // Let the browser paint the new content, then fade in
              requestAnimationFrame(() => setFading(false));
            });
          }
        } catch (e) {
          console.error("Search error:", e);
        }
      };

      if (query.trim()) {
        debounceTimer = window.setTimeout(doFetch, 250);
      } else {
        doFetch();
      }
    })
  );

  return (
    <div class="app">
      <header class="app-header">
        <SearchBar />
      </header>
      <div class="app-body">
        <Sidebar />
        <main class="app-main">
          <Toolbar />
          <div class={`content-area ${fading() ? "fading" : ""}`}>
            <Show when={viewMode() === "grid"} fallback={<BookList />}>
              <BookGrid />
            </Show>
          </div>
        </main>
      </div>
      <BookDetail />
    </div>
  );
}
