# RFC 0013: Allow ingesting from GUI

**Issue**: #32
**Status**: Implementing
**Branch**: `rfc/32-ingest-from-gui`

**Resolutions** (from #32 comments):
- **Q1**: Native picker only, supporting either files OR a folder. No drag-and-drop in v1.
- **Q2**: Add `--format ndjson` to the CLI; the GUI consumes that stream.
- **Q3**: Auto-confirm is the **only** option for the GUI — no per-file review/edit flow.
- **Q4**: **Auto-detect**, do not show a checkbox. If `ocrmypdf` is installed, OCR scanned PDFs automatically; if not, surface a per-file warning and proceed with whatever extractable text exists. (Different from the original explicit-checkbox proposal.)
- **Q5**: Inbox copy stays — the GUI calls the same CLI path so the user can clean up the source folder afterward freely.

---

## Problem

The desktop app (`app/`) is read-only over the library: it lists, searches, opens, and reveals documents but cannot add new ones. To ingest a new file the user has to leave the app, open a terminal, and run `wst ingest <path>`. This is the only common workflow where the GUI sends the user back to the CLI.

Concretely:

- `wst ingest [PATH]` ([`src/wst/cli.py:197`](../../src/wst/cli.py)) is the single entry point. Without arguments it processes `~/wst/inbox/`; with a path it copies the input into inbox and ingests only those files. Per-file flow is interactive by default (prompts "Accept and ingest?") unless run as `wst ingest --format json` (auto-accepts and emits a single JSON summary at the end). Supports `--ocr`, `-v`, `--keep-inbox`.
- The Tauri commands ([`app/src-tauri/src/commands.rs`](../../app/src-tauri/src/commands.rs)) are all read-only over the library: `list_documents`, `search_documents`, `get_document`, `get_topics_vocabulary`, `get_library_stats`, `open_pdf`, `reveal_in_finder`, `get_cover`. The only "write" command is `backup_to_icloud`, plus a generic CLI shim `run_wst_command(args: Vec<String>)` (lines 92–105).
- The plumbing to invoke the CLI from the GUI **already exists** via that `run_wst_command` shim; `which_wst()` resolves the bundled sidecar (RFC 0002), then `~/.local/bin/wst`, then `/usr/local/bin/wst`. What's missing is the UI surface and a progress affordance suited to a slow-per-file operation.

The "slow-per-file" part is non-trivial. Per-file ingest does an LLM metadata call, PDF text extraction, content_preview ladder (RFC 0011), cover generation (RFC 0004), and a DB insert. Even on a small folder, a `--format json` invocation emits nothing until *every* file is done — the app would appear frozen for minutes. The GUI needs incremental progress, not a single end-of-run blob.

---

## Proposed Solution

Three pieces:

1. **CLI**: add `--format ndjson` to `wst ingest`, emitting one JSON event per file plus a final summary event.
2. **Tauri**: add an `ingest_files` command that spawns the CLI in NDJSON mode, tails its stdout, and re-emits each event to the frontend as a Tauri event.
3. **Frontend**: add an "Ingestar" button to the toolbar that opens an ingest modal — file/folder picker (and optionally drag-and-drop), per-file progress list, cancel button, and a final refresh of the document grid.

### 1. CLI — `--format ndjson`

`wst ingest` already uses an output abstraction (`wst.output`) with `human`, `json`, `yaml`, `md` formats. Add `ndjson` as a fifth value with these semantics:

- One line per **per-file event** as it finishes:
  ```json
  {"event":"file","filename":"book.pdf","status":"ingested","dest_path":"books/Author - Title.pdf"}
  {"event":"file","filename":"scan.pdf","status":"failed","reason":"Error generating metadata: timeout"}
  {"event":"file","filename":"dup.pdf","status":"skipped","reason":"duplicate"}
  ```
- One final **summary event** matching today's `--format json` payload, wrapped in `{"event":"summary", ...}`.
- Stdout is line-buffered (`sys.stdout.reconfigure(line_buffering=True)` on entry) so consumers see each line immediately.
- NDJSON implies `--yes` (auto-confirm) — no interactive prompt is meaningful when stdout is being parsed line-by-line by another process.

This is purely additive. Existing JSON consumers are untouched.

### 2. Tauri command — `ingest_files`

```rust
#[derive(Deserialize)]
pub struct IngestOpts {
    pub ocr: bool,
}

#[tauri::command]
pub async fn ingest_files(
    paths: Vec<String>,
    opts: IngestOpts,
    window: tauri::Window,
) -> Result<IngestSummary, String> { /* ... */ }
```

Behavior:

- Spawns `wst ingest --format ndjson` with one positional path per entry in `paths`, plus `--ocr` if `opts.ocr` is set.
- Reads stdout line-by-line via `tokio::io::BufReader::lines()`. For every `event:"file"` line, emits a Tauri event `ingest:file` to the requesting window with the parsed payload. The frontend listens for these and updates its progress list incrementally.
- The final `event:"summary"` line is **not** re-emitted as an event — it becomes the function's return value (`IngestSummary`), which the frontend awaits via `invoke()`.
- Stderr is captured and forwarded as `ingest:log` events, surfaced in a collapsible "Detalles" panel of the modal so users see real CLI errors instead of a generic toast.
- The command returns `Err(...)` only on hard failures (CLI binary not found, NDJSON parse error). A `--format ndjson` run where some files failed but the process exited cleanly is `Ok(summary)` with non-zero `failed` count, exactly like today's `--format json` semantics.

**Cancellation** is done by killing the child process. The Tauri command holds the `Child` handle in app state keyed by an ingest-session id; a sibling command `cancel_ingest(session_id)` kills it. CLI side: a half-processed file remains in inbox; the next ingest run reprocesses it (file-hash dedupe in `db.exists_hash` ensures already-indexed files are skipped). No special cleanup needed.

### 3. Frontend — toolbar button + ingest modal

- **Toolbar**: add an "Ingestar" button (next to "Extras") in `Toolbar.tsx`. Clicking opens `IngestModal`.
- **IngestModal** (new component, sibling to `ExtrasPanel.tsx`):
  - Empty state: a centered drop zone (or button if drag-drop is not in scope per Q1) labeled "Soltá archivos o una carpeta acá" plus an explicit "Elegir archivos…" button that opens Tauri's native dialog (`@tauri-apps/plugin-dialog`).
  - OCR opt-in checkbox (Q4) — disabled with a tooltip when the `ocr` extra is missing (status fetched once on mount via the existing `getExtrasStatus` helper).
  - Once paths are queued, the modal shows a list: filename → state (pending/spinner/✓/×). Updated by the `ingest:file` event listener.
  - Final summary: "Listo — N ingestados, M omitidos, K fallaron" plus a button to close the modal. On close, emit a `library:changed` window event so `App.tsx` (or whichever component owns the document list) refreshes via `list_documents`.
  - Cancel button (only while a session is active) calls `cancel_ingest(session_id)`.

A small Solid signal store holds the per-session state. No global state mutation beyond the close-time refresh.

### Sequence

```
User → Toolbar "Ingestar" button → IngestModal opens
User picks files via picker (or drops them onto the modal — Q1)
IngestModal → invoke("ingest_files", {paths, opts}) → Tauri spawns `wst ingest --format ndjson <paths…>`
                                                         │
                                                         ▼
                              CLI emits NDJSON line per file as each finishes
                                                         │
                                                         ▼
       Tauri parses each line → emit "ingest:file" event ─→ IngestModal updates row
       CLI emits final summary line → tauri command resolves with IngestSummary
       IngestModal shows totals, fires "library:changed" → grid refreshes via list_documents
```

---

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| Reimplement ingest in Rust (no CLI subprocess) | Doubles the maintenance surface — every ingest change would need to land in two places, including the LLM prompt, content_preview ladder (RFC 0011), and cover generation. The CLI is the source of truth and is already bundled as a sidecar. |
| Reuse the existing `run_wst_command` shim with `--format json` | No incremental progress — the app would appear frozen for the entire ingest. Per-folder ingests can take many minutes; users will think the app crashed. |
| Watch the inbox folder and auto-ingest dropped files | Less explicit than a button + modal. Surprises users when ingest runs without an obvious trigger. Can revisit as a separate "watch mode" feature. |
| Parse the human-format `[N%] file.pdf | ETA: 3s` carriage-return progress line in the Tauri command | Format-fragile — any tweak to the human progress display breaks the GUI. NDJSON is a stable contract by design and reuses the existing `--format` machinery. |
| Per-file metadata review/edit before commit (matches CLI's default interactive mode) | Substantially more UI work — the AI metadata is rich (title, author, year, ISBN, summary, tags, topics, content_preview). The CLI already supports `wst edit <id> --enrich` post-hoc, which covers correction without blocking the ingest flow. Revisit in a follow-up if user feedback says auto-accept produces too many bad rows. |
| In-place ingestion (skip the inbox copy step the CLI does today) | Diverges GUI and CLI semantics, making `wst ingest` and "Ingestar from GUI" subtly different. Inbox copy is cheap relative to LLM time; not worth the divergence. |

---

## Open Questions

> **Q1** — Input modality: picker dialog only (simpler), or also drag-and-drop onto the modal? Drag-onto-the-whole-window is friendlier but requires opting into Tauri's drag-drop event globally, which on macOS interferes with text drag-select and is awkward to scope to "only the modal." Proposal: **picker only for v1**, drop zone on the modal in a follow-up if it turns out to matter.

> **Q2** — Progress model: NDJSON event stream from the CLI, or have the Tauri command parse the existing human-format `\r`-progress line? Proposal: **NDJSON.** It's a small CLI lift (one branch in the existing `--format` switch), the contract is stable, and it sets us up for any future GUI feature that needs streaming events from the CLI. The human format keeps doing its job for terminal users.

> **Q3** — Auto-confirm vs review-before-persisting: GUI always auto-accepts AI metadata (`wst ingest -y` semantics), or shows a per-file metadata preview the user can edit before commit (CLI default)? Auto-accept is much less UI work and the user can correct rows after the fact via the existing `wst edit --enrich` / book-detail edit paths. Proposal: **auto-accept for v1**, surface a "Revisar antes de guardar" toggle in a follow-up if false positives become a complaint.

> **Q4** — OCR opt-in: an "OCR para PDFs escaneados" checkbox in the ingest modal, off by default, disabled when the `ocr` extra (RFC 0008) is not installed and tooltip-pointed at the Extras panel? Or always-on auto-detect (run OCR only if the file's first-pages text extraction comes back empty)? Proposal: **explicit checkbox**, since OCR can be expensive for large scans and the user knows when they're feeding in a scanned doc.

> **Q5** — Inbox semantics: ingest-from-GUI still goes through the inbox copy step (matches CLI behavior; users can delete the source after), or reads source files in place (slightly faster, no disk duplication)? Proposal: **inbox copy** to keep the two entry points behaviorally identical and let the user clean up the source folder freely.

---

## Implementation Plan

- [ ] Add `--format ndjson` to `wst ingest` in `src/wst/cli.py` — emit one `{"event":"file",...}` line per `IngestResult` plus a final `{"event":"summary",...}` line; line-buffer stdout; imply `--yes`. Per Q2.
- [ ] Auto-detect OCR (Q4): in the per-file ingest flow, when the extracted `text_sample` is too thin to be useful, run OCR if `ocrmypdf` is on `PATH`, otherwise emit a per-file `{"event":"warning",...}` (NDJSON mode) or stderr line (other modes) and continue with whatever text exists. The existing `--ocr` flag stays as the explicit force-on override. Apply uniformly to both CLI and GUI ingest paths since the GUI just calls the CLI.
- [ ] Tests: `tests/test_ingest.py` covering the NDJSON event sequence (happy path, mixed success/skip/fail, OCR auto-detect when text is sparse and `ocrmypdf` is missing/present).
- [ ] Add `ingest_files(paths, opts)` and `cancel_ingest(session_id)` Tauri commands in `app/src-tauri/src/commands.rs`. Spawn the CLI sidecar, parse NDJSON, emit `ingest:file` / `ingest:warning` / `ingest:log` events, return `IngestSummary` on completion.
- [ ] Add `tauri-plugin-dialog` to `app/src-tauri/Cargo.toml` and `@tauri-apps/plugin-dialog` to `app/package.json` for native file/folder picker (Q1).
- [ ] Frontend: new `IngestModal.tsx` component (mirrors `ExtrasPanel.tsx` overlay style); wire the toolbar "Ingestar" button in `Toolbar.tsx`; emit a `library:changed` window event on close so the grid refreshes. No OCR checkbox per Q4 — surface OCR auto-detect warnings inline as per-file rows tagged "OCR no disponible".
- [ ] Smoke-test: ingest a 3-file folder via the GUI and confirm rows appear in the grid without restart; cancel mid-ingest and confirm the inbox is recoverable.
- [ ] README: add a "Desktop app — Ingestar" subsection under the existing Desktop App install block; one-line description of the auto-detect OCR behavior and the warning when tools are missing.
