import { For, createMemo, Show, createSignal, onCleanup } from "solid-js";
import {
  activeDocType,
  setActiveDocType,
  activeTopic,
  setActiveTopic,
  libraryStats,
  documents,
} from "../lib/store";
import { DOC_TYPE_LABELS } from "../lib/types";

const STORAGE_KEY = "wst.sidebarWidth";
const MIN_WIDTH = 140;
const MAX_WIDTH = 320;
const DEFAULT_WIDTH = 180;

export default function Sidebar() {
  const stats = () => libraryStats();

  const savedWidth = parseInt(localStorage.getItem(STORAGE_KEY) ?? "", 10);
  const initialWidth = Number.isFinite(savedWidth)
    ? Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, savedWidth))
    : DEFAULT_WIDTH;

  const [width, setWidth] = createSignal(initialWidth);

  // Derive unique topics sorted alphabetically from all loaded documents
  const allTopics = createMemo(() => {
    const topicSet = new Set<string>();
    for (const doc of documents()) {
      for (const topic of doc.topics ?? []) {
        if (topic) topicSet.add(topic);
      }
    }
    return Array.from(topicSet).sort((a, b) => a.localeCompare(b));
  });

  let startX = 0;
  let startWidth = 0;

  function onMouseMove(e: MouseEvent) {
    const delta = e.clientX - startX;
    const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + delta));
    setWidth(next);
  }

  function onMouseUp() {
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
    document.body.classList.remove("resizing");
    localStorage.setItem(STORAGE_KEY, String(width()));
  }

  function onHandleMouseDown(e: MouseEvent) {
    e.preventDefault();
    startX = e.clientX;
    startWidth = width();
    document.body.classList.add("resizing");
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }

  onCleanup(() => {
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
    document.body.classList.remove("resizing");
  });

  return (
    <nav class="sidebar" style={{ width: `${width()}px` }}>
      <div class="sidebar-section-label">Library</div>
      <ul class="sidebar-list">
        <li
          class={`sidebar-item ${activeDocType() === null ? "active" : ""}`}
          onClick={() => setActiveDocType(null)}
        >
          <span>All</span>
          <span class="sidebar-count">{stats().total}</span>
        </li>
        <For each={stats().by_type}>
          {(item) => (
            <li
              class={`sidebar-item ${activeDocType() === item.doc_type ? "active" : ""}`}
              onClick={() => setActiveDocType(item.doc_type)}
            >
              <span>{DOC_TYPE_LABELS[item.doc_type] ?? item.doc_type}</span>
              <span class="sidebar-count">{item.count}</span>
            </li>
          )}
        </For>
      </ul>

      <Show when={allTopics().length > 0}>
        <div class="sidebar-section-label sidebar-section-label--topics">Topics</div>
        <ul class="sidebar-list">
          <For each={allTopics()}>
            {(topic) => (
              <li
                class={`sidebar-item ${activeTopic() === topic ? "active" : ""}`}
                onClick={() =>
                  setActiveTopic(activeTopic() === topic ? null : topic)
                }
              >
                <span class="sidebar-topic-name">{topic}</span>
              </li>
            )}
          </For>
        </ul>
      </Show>

      <div class="sidebar-resize-handle" onMouseDown={onHandleMouseDown} />
    </nav>
  );
}
