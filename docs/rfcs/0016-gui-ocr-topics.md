# RFC 0016: OCR and topic modeling from the GUI

**Issue**: #39
**Status**: Implementing
**Branch**: `rfc/39-gui-ocr-topics`

**Resolutions** (from #39 comments):
- **Q1**: A — Topics pane lives in the sidebar, below the Backup pane.
- **Q2**: OCR is one-shot per document (no streaming). Streaming is reserved for topics.
- **Q3**: Yes, confirmation dialog before topics build. Advanced toggle exposes `--n-topics`.
- **Q4**: Re-fetch the document list and topic vocabulary after topics build, after ingest, after OCR (and after `wst fix` as a follow-up — fix is out of scope here).
- **Q5**: A "needs OCR" indicator is welcome **if easy**. We'll evaluate during implementation; if it requires schema migration or a heuristic at ingest, defer to a follow-up.

---

## Problem

Today the desktop app exposes a small slice of the CLI: list/search/edit/ingest/per-doc iCloud backup, plus the new Backup pane. Two long-running operations are still CLI-only:

- **OCR** (`wst ocr <path>` — [`cli.py:974`](../../src/wst/cli.py)): adds a searchable text layer to scanned PDFs via `ocrmypdf`. Per-document.
- **Topic modeling** (`wst topics build` — [`cli.py:2110`](../../src/wst/cli.py)): clusters the corpus into a topic vocabulary and assigns topics to every document. Library-wide, multi-minute on a real library.

Users on the GUI today have to drop to a terminal for both, which is the friction this issue calls out.

The pattern for "long-running CLI command, called from the GUI with progress" already exists in **RFC 0013 (ingest from GUI)** — `run_wst_command` spawns the CLI with `--format ndjson`, the Tauri side relays each NDJSON line as a typed event, and the frontend renders progress. We can reuse that pattern almost verbatim.

---

## Proposed Solution

Two new GUI surfaces, each shelling out to its existing CLI command via the established Tauri ingest pattern.

### 1. OCR — per-document button in `BookDetail`

Add a **"OCR"** button next to the existing Edit / Backup buttons in `BookDetail.tsx`. On click:

- The frontend calls a new `tauri.ts` wrapper `ocrDocument(id, opts)` which invokes `run_wst_command` with args `["ocr", "<file_path>", "--format", "ndjson"]`. The current `wst ocr` is human-output-only, so the implementation also adds an `--format ndjson` mode (one event per file with `{event: "file", path, status: "ocrd"|"skipped"|"failed", reason}`) — small extension, parallels `wst ingest --format ndjson`.
- Status is shown inline like the existing backup status row. Force-OCR is exposed as a small toggle (off by default — auto-detect handles most cases).
- After success, the row reloads from the DB so the "OCR" indicator (if we add one) reflects new state.

### 2. Topic modeling — entry point in `Sidebar` (next to the Backup pane)

Add a **"Topics"** pane in the sidebar — same visual weight as the Backup pane — with one button: **"Rebuild topic vocabulary"**. On click:

- Confirmation dialog: "This will recompute topics for all N documents and may take a few minutes." (Topics build *replaces* the existing vocabulary — needs an explicit confirm, mirroring the CLI's `-y` prompt.)
- The frontend calls `tauri.ts` wrapper `buildTopics()` which invokes `run_wst_command` with `["topics", "build", "--yes", "--format", "ndjson"]`.
- A modal shows progress events streamed over a Tauri channel (mirroring `IngestModal`):
  - `{event: "phase", name: "embedding"|"clustering"|"naming"|"assigning", message: ...}`
  - `{event: "doc", id, topics: [...]}` for each per-doc assignment (so the modal can show "Assigning 47/213…")
  - Final `{event: "done", topics: [...], assigned: N}`
- On `done`, the frontend re-fetches the topic vocabulary (via the existing `getTopicsVocabulary()`) and the document list, so the sidebar's Topics filter and per-doc chips update.

`wst topics build` is human-output-only today; like OCR, we add an `--format ndjson` mode that emits the events above.

### Tauri / commands surface

No new Rust commands needed. Both new flows go through the existing `run_wst_command`. Two new JS wrappers in `tauri.ts`:

- `ocrDocument(id: number, opts: { force?: boolean }): Promise<OcrResult>`
- `buildTopics(opts: { nTopics?: number }): Promise<TopicsBuildResult>` — returns the final summary; per-event progress is delivered via a Tauri event listener (`onTopicsEvent` etc.), mirroring `onIngestFile`.

If the streaming progress turns out to be more wiring than it's worth for OCR (which is per-file and usually fast), the OCR path can simplify to a one-shot `run_wst_command` call returning the final `OcrResult` — see Q2 below.

---

## Alternatives Considered

| Alternative | Why rejected |
|---|---|
| Implement OCR/topics natively in Rust (skip CLI) | Duplicates Python logic (ocrmypdf wrapping, sentence-transformers, KMeans, AI naming). The CLI is the source of truth — wrap it, don't fork it. |
| Single "Tools" pane with both OCR and topics | Topics is library-wide; OCR is per-document. Different ergonomic homes. |
| Run topics build automatically after every ingest | Surprising and expensive. Keep it explicit (button-driven). |
| Batch OCR ("OCR all scanned PDFs") | Useful but bigger scope. The CLI supports `wst ocr <directory>`; we can add this as a follow-up after the per-doc flow lands. |
| Expose `wst fix` (metadata enrichment) too | Issue title is "OCR + topic modeling". `wst fix` is a separate operation (batch metadata via AI + web search) — out of scope. Could be RFC 0017 if asked. |

---

## Open Questions

> **Q1**: Where exactly should the "Rebuild topics" entry point live? (a) sidebar pane below Backup, (b) inside `ExtrasPanel.tsx` (behaves like a tool/admin action), (c) toolbar button. Lean (a) — sidebar matches the per-feature pane convention we just established with Backup, and topics genuinely is a library-level setting.

> **Q2**: Should OCR stream NDJSON progress, or is it fine as a one-shot call (call returns when done, no per-file events)? Per-doc OCR is usually fast (seconds–tens of seconds per file). One-shot keeps the wiring small. If the user later asks for batch OCR ("OCR all scanned PDFs at once"), we can add streaming then. Lean **one-shot for OCR; streaming for topics**.

> **Q3**: Topics build is destructive (replaces vocabulary, reassigns every doc). Confirmation dialog before kicking it off — yes/no? Lean yes. Should it also offer `--n-topics` as an advanced option, or always auto-detect? Auto-detect is the CLI default; keep advanced hidden behind a "Show advanced" toggle inside the modal.

> **Q4**: When topics build finishes, the GUI needs to refresh: (a) the sidebar's `Temas` list (`getTopicsVocabulary`), (b) every visible document's `topics` chips. Simple approach: re-fetch the document list after `done`. Acceptable, or do we want a finer-grained update? Lean simple re-fetch.

> **Q5**: For OCR, should the GUI show a "needs OCR" indicator on documents detected as scanned? That's a nice-to-have but not in scope here — it would need a new DB column or heuristic at ingest time. Out of scope; flag as a follow-up.

---

## Implementation Plan

- [ ] Add `--format ndjson` to `wst ocr` ([`cli.py:974`](../../src/wst/cli.py)) emitting per-file `{event, path, status, reason}` events. (Out: keep `--format human` and `--format json` working unchanged.)
- [ ] Add `--format ndjson` to `wst topics build` ([`cli.py:2110`](../../src/wst/cli.py)) emitting `phase` / `doc` / `done` events.
- [ ] Add `ocrDocument(id, opts)` in `app/src/lib/tauri.ts` — one-shot wrapper around `run_wst_command` (per Q2).
- [ ] Add `buildTopics(opts)` + `onTopicsEvent(cb)` in `app/src/lib/tauri.ts`, mirroring the ingest pattern.
- [ ] Add an "OCR" button to `BookDetail.tsx` (next to Edit / Backup), with inline status row.
- [ ] Add a `TopicsPane.tsx` next to `BackupPane.tsx` in the sidebar, with confirmation dialog and progress modal.
- [ ] On `topics-build done`, refresh `getTopicsVocabulary()` and re-fetch the document list so chips and filters update.
- [ ] Smoke-test on the user's library (≥100 docs) end-to-end: OCR a scanned PDF from BookDetail, rebuild topics from the sidebar.
- [ ] Update `README.md` and the Features section.
