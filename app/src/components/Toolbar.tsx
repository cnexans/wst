import { createSignal } from "solid-js";
import { viewMode, setViewMode, sortBy, setSortBy, documents } from "../lib/store";

export const [showExtras, setShowExtras] = createSignal(false);
export const [showIngest, setShowIngest] = createSignal(false);

export default function Toolbar() {
  return (
    <div class="toolbar">
      <span class="toolbar-count">{documents().length} documentos</span>

      <div class="toolbar-controls">
        <select
          class="toolbar-sort"
          value={sortBy()}
          onChange={(e) => setSortBy(e.currentTarget.value)}
        >
          <option value="title">Título</option>
          <option value="author">Autor</option>
          <option value="year">Año</option>
          <option value="ingested_at">Recién añadidos</option>
        </select>

        <button
          class="view-btn"
          onClick={() => setShowIngest(true)}
          title="Ingestar documentos"
        >
          <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
            <path d="M.5 9.9a.5.5 0 01.5.5v2.5a1 1 0 001 1h12a1 1 0 001-1v-2.5a.5.5 0 011 0v2.5a2 2 0 01-2 2H2a2 2 0 01-2-2v-2.5a.5.5 0 01.5-.5z"/>
            <path d="M7.646 1.146a.5.5 0 01.708 0l3 3a.5.5 0 01-.708.708L8.5 2.707V11.5a.5.5 0 01-1 0V2.707L5.354 4.854a.5.5 0 11-.708-.708l3-3z"/>
          </svg>
        </button>

        <button
          class="view-btn"
          onClick={() => setShowExtras(true)}
          title="Extras instalables"
        >
          <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
            <path d="M9.405 1.05c-.413-1.4-2.397-1.4-2.81 0l-.1.34a1.464 1.464 0 01-2.105.872l-.31-.17c-1.283-.698-2.686.705-1.987 1.987l.169.311c.446.82.023 1.841-.872 2.105l-.34.1c-1.4.413-1.4 2.397 0 2.81l.34.1a1.464 1.464 0 01.872 2.105l-.17.31c-.698 1.283.705 2.686 1.987 1.987l.311-.169a1.464 1.464 0 012.105.872l.1.34c.413 1.4 2.397 1.4 2.81 0l.1-.34a1.464 1.464 0 012.105-.872l.31.17c1.283.698 2.686-.705 1.987-1.987l-.169-.311a1.464 1.464 0 01.872-2.105l.34-.1c1.4-.413 1.4-2.397 0-2.81l-.34-.1a1.464 1.464 0 01-.872-2.105l.17-.31c.698-1.283-.705-2.686-1.987-1.987l-.311.169a1.464 1.464 0 01-2.105-.872l-.1-.34zM8 10.93a2.929 2.929 0 110-5.858 2.929 2.929 0 010 5.858z"/>
          </svg>
        </button>

        <div class="view-toggle">
          <button
            class={`view-btn ${viewMode() === "grid" ? "active" : ""}`}
            onClick={() => setViewMode("grid")}
            title="Cuadrícula"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
              <path d="M1 2.5A1.5 1.5 0 012.5 1h3A1.5 1.5 0 017 2.5v3A1.5 1.5 0 015.5 7h-3A1.5 1.5 0 011 5.5v-3zm8 0A1.5 1.5 0 0110.5 1h3A1.5 1.5 0 0115 2.5v3A1.5 1.5 0 0113.5 7h-3A1.5 1.5 0 019 5.5v-3zm-8 8A1.5 1.5 0 012.5 9h3A1.5 1.5 0 017 10.5v3A1.5 1.5 0 015.5 15h-3A1.5 1.5 0 011 13.5v-3zm8 0A1.5 1.5 0 0110.5 9h3a1.5 1.5 0 011.5 1.5v3a1.5 1.5 0 01-1.5 1.5h-3A1.5 1.5 0 019 13.5v-3z" />
            </svg>
          </button>
          <button
            class={`view-btn ${viewMode() === "list" ? "active" : ""}`}
            onClick={() => setViewMode("list")}
            title="Lista"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
              <path fill-rule="evenodd" d="M2.5 12a.5.5 0 01.5-.5h10a.5.5 0 010 1H3a.5.5 0 01-.5-.5zm0-4a.5.5 0 01.5-.5h10a.5.5 0 010 1H3a.5.5 0 01-.5-.5zm0-4a.5.5 0 01.5-.5h10a.5.5 0 010 1H3a.5.5 0 01-.5-.5z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
