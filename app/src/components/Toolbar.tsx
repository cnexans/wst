import { createSignal } from "solid-js";
import { viewMode, setViewMode, sortBy, setSortBy, documents } from "../lib/store";
import { backupToIcloud } from "../lib/tauri";

export default function Toolbar() {
  const [backupStatus, setBackupStatus] = createSignal<string | null>(null);
  const [backupError, setBackupError] = createSignal(false);

  async function handleBackup() {
    try {
      await backupToIcloud();
      setBackupError(false);
      setBackupStatus("Backed up to iCloud ✓");
    } catch (err) {
      setBackupError(true);
      setBackupStatus(String(err));
    } finally {
      setTimeout(() => setBackupStatus(null), 3000);
    }
  }

  return (
    <div class="toolbar">
      <span class="toolbar-count">{documents().length} documents</span>

      <div class="toolbar-controls">
        {backupStatus() !== null && (
          <span class={`toolbar-backup-status${backupError() ? " toolbar-backup-status--error" : ""}`}>
            {backupStatus()}
          </span>
        )}

        <button class="btn btn-secondary" onClick={handleBackup}>
          Backup to iCloud
        </button>

        <select
          class="toolbar-sort"
          value={sortBy()}
          onChange={(e) => setSortBy(e.currentTarget.value)}
        >
          <option value="title">Sort by Title</option>
          <option value="author">Sort by Author</option>
          <option value="year">Sort by Year</option>
          <option value="ingested_at">Recently Added</option>
        </select>

        <div class="view-toggle">
          <button
            class={`view-btn ${viewMode() === "grid" ? "active" : ""}`}
            onClick={() => setViewMode("grid")}
            title="Grid view"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
              <path d="M1 2.5A1.5 1.5 0 012.5 1h3A1.5 1.5 0 017 2.5v3A1.5 1.5 0 015.5 7h-3A1.5 1.5 0 011 5.5v-3zm8 0A1.5 1.5 0 0110.5 1h3A1.5 1.5 0 0115 2.5v3A1.5 1.5 0 0113.5 7h-3A1.5 1.5 0 019 5.5v-3zm-8 8A1.5 1.5 0 012.5 9h3A1.5 1.5 0 017 10.5v3A1.5 1.5 0 015.5 15h-3A1.5 1.5 0 011 13.5v-3zm8 0A1.5 1.5 0 0110.5 9h3a1.5 1.5 0 011.5 1.5v3a1.5 1.5 0 01-1.5 1.5h-3A1.5 1.5 0 019 13.5v-3z" />
            </svg>
          </button>
          <button
            class={`view-btn ${viewMode() === "list" ? "active" : ""}`}
            onClick={() => setViewMode("list")}
            title="List view"
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
