import { For, createMemo, Show } from "solid-js";
import {
  activeDocType,
  setActiveDocType,
  activeTopic,
  setActiveTopic,
  libraryStats,
  documents,
} from "../lib/store";
import { DOC_TYPE_LABELS } from "../lib/types";

export default function Sidebar() {
  const stats = () => libraryStats();

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

  return (
    <nav class="sidebar">
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
    </nav>
  );
}
