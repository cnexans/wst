# RFC 0011: Topic modeling should include document content

**Issue**: #29
**Status**: Approved — awaiting approval label
**Branch**: `rfc/29-topic-modeling-content`

**Resolutions** (from #29 comments):
- **Q1**: Ship with proposed defaults (1500-char cap, 600-char threshold). Validate empirically by re-running clustering on the current library after implementation.
- **Q2**: Add `content_preview_source` column so the chosen ladder step is queryable per document.
- **Q3**: Out of scope — skip missing files silently, no count line.
- **Q4**: Use the TOC entries' page-index numbers to locate the introduction chapter (the first non-front-matter entry's page range). Fall back to the regex match only when the TOC has no usable page indices.

---

## Problem

`wst topics build` clusters documents using only **metadata fields** — `title | tags | summary[:300]` ([`topics.py:177-199`](../../src/wst/topics.py)). For a multilingual library that mixes textbooks, papers, and one-sentence-titled e-books, this is not enough signal:

- **Short, generic titles** (e.g. *"Introducción"*, *"Notes"*) give the embedder almost nothing to work with — every short generic title clusters together regardless of subject.
- **Books** carry their topical signal in their **table of contents and first chapter**, not in the title. A book titled *"Vol. 2"* with a TOC of "Eigenvalues, Spectral theorem, Quadratic forms" should land in the linear-algebra cluster, but currently lands in a generic "Volume 2"-style noise cluster.
- **The `documents.toc` column already exists** ([`db.py:22`](../../src/wst/db.py)) but is **never populated and never read** by topics. The schema is half-done.

The user's request maps directly to a content-aware feature ladder:

> *"if it is short, it can use a summary; if it is too long, like a book, it should try to use its table of contents and introductory chapter; if [neither] exists, it should use first few pages."*

---

## Proposed Solution

Introduce a single field — `content_preview` — that is computed once at ingest time, stored on the document row, and concatenated into the topic-clustering text. The selection of *what* to put in `content_preview` follows a deterministic ladder so the same document always produces the same preview.

### Selection ladder (per document, at ingest)

For each document, pick **the first option that yields ≥ N characters** of usable text (proposed `N = 600`):

| Order | Source | Notes |
|---|---|---|
| 1 | `summary` (already AI-generated) | Cheap, already in the DB. Used as-is when long enough. |
| 2 | TOC extracted via `fitz.Document.get_toc()` | Free for most PDFs that ship a structured TOC. Flatten to one line per heading. |
| 3 | Introductory chapter text | Use the TOC entries' page indices to locate the first body chapter. Concretely: skip front-matter entries (cover, copyright, acknowledgments, table of contents itself) and pull the page range of the first remaining entry. Only fall back to the regex `^(introduc(tion|ción)\|prefac(e\|io)\|prólogo\|preface)` if `get_toc()` returns no usable page indices. |
| 4 | First ~5 pages of body text (current `extract_doc_info` behavior) | Last-resort fallback. We already read these pages at ingest, so this is free. |
| 5 | Title + tags only | Only if the doc has no extractable text (e.g. scanned PDF without OCR). |

Truncate the chosen source to a max length (proposed `1500 chars`) so that very long TOCs don't dominate the embedding.

### Schema change

Add one column, populated at ingest time:

```sql
ALTER TABLE documents ADD COLUMN content_preview TEXT;
```

(Migration: nullable column, no default; existing rows get backfilled lazily — see Backfill below.)

### Topics build change

In [`topics.py:191`](../../src/wst/topics.py), replace:

```python
text = f"{title} | {tags_str} | {summary[:300]}"
```

with:

```python
text = " | ".join(filter(None, [title, tags_str, content_preview[:1500]]))
```

If `content_preview` is `NULL` (legacy rows that haven't been backfilled), fall back to `summary[:300]` so old libraries still work.

### Backfill

`wst topics build` already iterates every document. Add a one-shot helper invoked **before** the embedding step:

- For any row with `content_preview IS NULL` and a known `path`, run the selection ladder against the file and `UPDATE documents SET content_preview = ?`.
- Print `Backfilling N/M …` so the user sees progress.
- Skip silently if the file is missing (out of scope per Q3).

This avoids a separate `wst topics backfill` command — the work happens lazily on first build after upgrade.

---

## Alternatives Considered

| Alternative | Why rejected |
|---|---|
| Use the `toc` column instead of a new `content_preview` | `toc` is currently unused and unpopulated. We could populate it, but the *ladder* picks from multiple sources and `content_preview` better describes the field's purpose. We'd still want a separate slot for raw TOC if other features need it later. |
| Compute the preview on the fly during `topics build` (no new column) | Re-parsing every PDF on every `topics build` run is slow and wasteful. The selection is deterministic, so cache it. |
| Embed the full document text (e.g. `paraphrase-multilingual-MiniLM-L12-v2` with chunking) | Order-of-magnitude more compute, marginal clustering gain over a 1500-char preview, and would change the topic-naming prompt budget. Out of scope for this RFC. |
| Use AI to write a topic-oriented summary at ingest (separate from current summary) | Doubles ingest LLM cost. The selection ladder is mechanical and free for ~80% of documents (TOC + first pages already read at ingest). Revisit if signal is still weak. |
| Add `content_preview` only to PDFs, skip for `.epub`/`.txt`/etc. | The ladder works for any file type that has extractable text — defining it as a universal field keeps the topics code simple. |

---

## Implementation Plan

- [ ] Migration: `ALTER TABLE documents ADD COLUMN content_preview TEXT` and `ALTER TABLE documents ADD COLUMN content_preview_source TEXT`.
- [ ] Add `wst.document.build_content_preview(path, summary) -> tuple[str | None, str]` implementing the ladder. Returns `(preview, source)` where `source ∈ {summary, toc, intro, first-pages, title-only, none}`.
- [ ] Hook `build_content_preview()` into the ingest pipeline so new documents get the field populated immediately.
- [ ] Add lazy backfill at the start of `topics_build()` ([`cli.py:1795`](../../src/wst/cli.py)): for rows where `content_preview IS NULL` and `path` exists, compute and persist.
- [ ] Update [`topics.py:191`](../../src/wst/topics.py) `build_vocabulary()` to read `content_preview` (with `summary[:300]` fallback for NULL).
- [ ] Update the cluster-naming prompt at [`topics.py:22-46`](../../src/wst/topics.py) to include `content_preview` in the per-document context (subject to its own char budget).
- [ ] Smoke-test on the user's existing library: re-run `wst topics build` and verify topic coherence improves on books that previously landed in noise clusters (Q1 validation).
- [ ] Document the new columns and the ladder behavior in the topics section of `README.md`.
