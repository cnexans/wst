import { For, Show, createMemo, onCleanup } from "solid-js";
import {
  activeDocType, setActiveDocType,
  activeTopic, setActiveTopic,
  activeSubject, setActiveSubject,
  libraryStats,
  allTopicsVocab,
  allSubjects,
  clearAllFilters,
} from "../lib/store";
import { DOC_TYPE_LABELS } from "../lib/types";

const STORAGE_KEY = "wst.sidebarWidth";
const MIN_WIDTH = 160;
const MAX_WIDTH = 360;
const DEFAULT_WIDTH = 200;

export default function Sidebar() {
  const stats = () => libraryStats();

  const savedWidth = parseInt(localStorage.getItem(STORAGE_KEY) ?? "", 10);
  const initialWidth = Number.isFinite(savedWidth)
    ? Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, savedWidth))
    : DEFAULT_WIDTH;

  let sidebarEl!: HTMLElement;
  let startX = 0;
  let startWidth = 0;
  let currentWidth = initialWidth;

  function applyWidth(w: number) {
    currentWidth = w;
    sidebarEl.style.width = `${w}px`;
  }

  function onMouseMove(e: MouseEvent) {
    const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + (e.clientX - startX)));
    applyWidth(next);
  }

  function onMouseUp() {
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
    document.body.classList.remove("resizing");
    localStorage.setItem(STORAGE_KEY, String(currentWidth));
  }

  function onHandleMouseDown(e: MouseEvent) {
    e.preventDefault();
    startX = e.clientX;
    startWidth = currentWidth;
    document.body.classList.add("resizing");
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }

  onCleanup(() => {
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
    document.body.classList.remove("resizing");
  });

  const hasActiveFilter = createMemo(
    () => activeDocType() !== null || activeTopic() !== null || activeSubject() !== null
  );

  return (
    <nav
      class="sidebar"
      ref={sidebarEl}
      style={{ width: `${initialWidth}px` }}
    >
      {/* Active filters summary + clear */}
      <Show when={hasActiveFilter()}>
        <div class="sidebar-active-filters">
          <span class="sidebar-active-label">Filtros activos</span>
          <button class="sidebar-clear-btn" onClick={clearAllFilters}>Limpiar</button>
        </div>
        <div class="sidebar-chips">
          <Show when={activeDocType()}>
            <span class="sidebar-chip" onClick={() => setActiveDocType(null)}>
              {DOC_TYPE_LABELS[activeDocType()!] ?? activeDocType()} ×
            </span>
          </Show>
          <Show when={activeTopic()}>
            <span class="sidebar-chip" onClick={() => setActiveTopic(null)}>
              {activeTopic()} ×
            </span>
          </Show>
          <Show when={activeSubject()}>
            <span class="sidebar-chip" onClick={() => setActiveSubject(null)}>
              {activeSubject()} ×
            </span>
          </Show>
        </div>
      </Show>

      {/* Type */}
      <div class="sidebar-section-label">Tipo</div>
      <ul class="sidebar-list">
        <li
          class={`sidebar-item ${activeDocType() === null ? "active" : ""}`}
          onClick={() => setActiveDocType(null)}
        >
          <span>Todos</span>
          <span class="sidebar-count">{stats().total}</span>
        </li>
        <For each={stats().by_type}>
          {(item) => (
            <li
              class={`sidebar-item ${activeDocType() === item.doc_type ? "active" : ""}`}
              onClick={() =>
                setActiveDocType(activeDocType() === item.doc_type ? null : item.doc_type)
              }
            >
              <span>{DOC_TYPE_LABELS[item.doc_type] ?? item.doc_type}</span>
              <span class="sidebar-count">{item.count}</span>
            </li>
          )}
        </For>
      </ul>

      {/* Topics */}
      <Show when={allTopicsVocab().length > 0}>
        <div class="sidebar-section-label sidebar-section-sep">Temas</div>
        <ul class="sidebar-list">
          <For each={allTopicsVocab()}>
            {(topic) => (
              <li
                class={`sidebar-item ${activeTopic() === topic ? "active" : ""}`}
                onClick={() => setActiveTopic(activeTopic() === topic ? null : topic)}
              >
                <span class="sidebar-topic-name">{topic}</span>
              </li>
            )}
          </For>
        </ul>
      </Show>

      {/* Subjects */}
      <Show when={allSubjects().length > 0}>
        <div class="sidebar-section-label sidebar-section-sep">Materia</div>
        <ul class="sidebar-list">
          <For each={allSubjects()}>
            {(subj) => (
              <li
                class={`sidebar-item ${activeSubject() === subj ? "active" : ""}`}
                onClick={() => setActiveSubject(activeSubject() === subj ? null : subj)}
              >
                <span class="sidebar-topic-name">{subj}</span>
              </li>
            )}
          </For>
        </ul>
      </Show>

      <div class="sidebar-resize-handle" onMouseDown={onHandleMouseDown} />
    </nav>
  );
}
