import { For } from "solid-js";
import {
  activeDocType,
  setActiveDocType,
  libraryStats,
} from "../lib/store";
import { DOC_TYPE_LABELS } from "../lib/types";

export default function Sidebar() {
  const stats = () => libraryStats();

  return (
    <nav class="sidebar">
      <div class="sidebar-header">Library</div>
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
    </nav>
  );
}
