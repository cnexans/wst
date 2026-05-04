# RFC 0004: Consistent Cover Display for Documents Without ISBN

**Issue**: #11  
**Status**: Draft — awaiting approval  
**Branch**: `rfc/issue-11-cover-consistency`

---

## Problem

Some documents without an ISBN show **no cover** in the app while others show the **first PDF page** as a cover. The behavior is inconsistent.

### Root cause analysis

The cover system has two layers:

1. **Python CLI** (`src/wst/covers.py`) — `ensure_cover()` generates and caches covers in `.covers/<id>.jpg`
2. **Tauri app** (`app/src-tauri/src/covers.rs`) — `CoverManager::get_cover_filename()` checks if the cached file exists

`ensure_cover` is only called by `wst covers` (not during ingest). The fallback path for no-ISBN documents:

```python
pdf_path = library_path / file_path
if pdf_path.exists():
    data = render_pdf_first_page(pdf_path)
```

Likely failure modes (causing inconsistency):

**A) `pdf_path.exists()` returns false** when `file_path` in the DB is an absolute path (e.g., iCloud-backed files whose path starts with `/`). `library_path / absolute_path` silently produces an incorrect path on Python < 3.12 when `file_path` doesn't start with `/` (it joins correctly), but if the path is the full absolute path, the join could fail.

**B) `render_pdf_first_page` fails silently** for some PDFs (encrypted, unusual encoding, zero-dimension page) and returns `None` — the cover is never written and the failure is only visible in the CLI output (`failed`), not the app.

**C) `wst covers` was run before some documents were ingested** — those documents simply have no entry in `.covers/` because the command was never run for them. The app has no way to trigger cover generation on demand.

---

## Proposed Solution

Three complementary fixes:

### Fix 1 — Resolve `file_path` correctly

In `ensure_cover`, normalize the path before checking existence:

```python
pdf_path = Path(file_path) if Path(file_path).is_absolute() else library_path / file_path
```

This handles the case where some entries have absolute paths (e.g., iCloud storage).

### Fix 2 — Auto-generate covers during ingest

Call `ensure_cover` at the end of `ingest_file` so every document gets a cover immediately on ingest, not only when the user runs `wst covers`:

```python
# In ingest_file(), after entry.id = db.insert(entry):
ensure_cover(config.library_path, entry.id, metadata.isbn, entry.file_path)
```

This eliminates the "covers exist for old docs but not new ones" gap.

### Fix 3 — Placeholder cover in the app for unresolvable covers

When `get_cover_filename` returns `None`, the Tauri app currently shows nothing (or crashes). Add a fallback so the app renders a generic placeholder:

In `CoverImage.tsx` (or equivalent component), when `cover_path` is null, display an SVG placeholder with the document title initials instead of an empty box.

---

## Alternative Considered

**On-demand cover generation from the app**: trigger `wst covers --id <doc_id>` via `run_wst_command` when the app requests a cover and none is cached. This avoids the ingest-time overhead but adds latency to the app's first load. Rejected because Fix 2 is simpler and ingest already calls the AI, so the additional PDF rendering cost is negligible.

---

## Open Questions

> **Q1**: Should we also add a `wst covers --missing` flag that only processes documents currently without a cached cover (for users who have existing libraries where some covers are missing)?

> **Q2**: For the path resolution (Fix 1), are there documents in your library where `file_path` is stored as an absolute path? If so, are those iCloud paths or S3 paths? This affects whether Fix 1 is the right approach or whether we need to special-case remote backends.

> **Q3**: For the app placeholder (Fix 3), do you want a styled placeholder (title initials in a colored box) or just an icon? I can prototype both.

---

## Files Changed (implementation phase)

- `src/wst/covers.py` — Fix 1: normalize `file_path` in `ensure_cover`
- `src/wst/ingest.py` — Fix 2: call `ensure_cover` after ingest insert
- `app/src/components/CoverImage.tsx` — Fix 3: render placeholder when cover is null
- `app/src-tauri/src/commands.rs` — (optionally) add `get_cover` command that triggers generation if missing
