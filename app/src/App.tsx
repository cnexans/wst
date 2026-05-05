import { createEffect, onMount, Show, on, createSignal } from "solid-js";
import {
  setDocuments,
  searchQuery,
  activeDocType,
  activeTopic,
  activeSubject,
  sortBy,
  viewMode,
  setLibraryStats,
  setAllTopicsVocab,
  setAllSubjects,
} from "./lib/store";
import {
  listDocuments,
  searchDocuments,
  getLibraryStats,
  getTopicsVocabulary,
  getSubjects,
} from "./lib/tauri";
import SearchBar from "./components/SearchBar";
import Sidebar from "./components/Sidebar";
import Toolbar, { showExtras, setShowExtras } from "./components/Toolbar";
import BookGrid from "./components/BookGrid";
import BookList from "./components/BookList";
import BookDetail from "./components/BookDetail";
import ExtrasPanel from "./components/ExtrasPanel";

export default function App() {
  let debounceTimer: number | undefined;
  let fetchId = 0;
  const [fading, setFading] = createSignal(false);

  onMount(async () => {
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
  });

  createEffect(
    on(
      [searchQuery, activeDocType, activeTopic, activeSubject, sortBy],
      ([query, docType, topic, subject, sort]) => {
        clearTimeout(debounceTimer);
        const currentFetch = ++fetchId;

        const doFetch = async () => {
          try {
            let results;
            if (query.trim()) {
              results = await searchDocuments(
                query,
                docType ?? undefined,
                topic ?? undefined,
                subject ?? undefined
              );
            } else {
              results = await listDocuments(
                docType ?? undefined,
                sort,
                topic ?? undefined,
                subject ?? undefined
              );
            }
            if (currentFetch === fetchId) {
              setFading(true);
              requestAnimationFrame(() => {
                setDocuments(results);
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
      }
    )
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
      <Show when={showExtras()}>
        <ExtrasPanel onClose={() => setShowExtras(false)} />
      </Show>
    </div>
  );
}
