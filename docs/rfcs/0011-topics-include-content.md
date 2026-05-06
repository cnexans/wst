# RFC 0011: Topic modeling should include document content

**Issue**: #29
**Status**: Draft — awaiting approval
**Branch**: `rfc/29-topic-modeling-content`

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
| 3 | Introductory chapter text | Detect via TOC entry whose title matches `^(introduc(tion|ción)\|prefac(e\|io)\|prólogo\|preface)`; extract that page range. |
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
- Skip silently if the file is missing.

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

## Open Questions

> **Q1**: What's the right target length for `content_preview`? Proposed **1500 chars** as the upper bound and **600 chars** as the threshold to stop walking the ladder. Too short and TOC entries get cut mid-list; too long and book TOCs dominate the embedding over title/tags. Should we tune empirically by re-running clustering on the user's current library and comparing topic coherence, or just ship the proposed defaults?

> **Q2**: Should the selection ladder log *which* source it used per document (e.g. `[toc]`, `[first-pages]`)? Useful for debugging "why did this book end up in cluster X" but adds noise on a 1000-doc library. Proposal: store the source in a sibling column `content_preview_source` (TEXT) so it's queryable but not printed during build.

> **Q3**: Backfill strategy for files that no longer exist on disk (the `path` column points to a missing file). Skip silently and leave `content_preview = NULL`, falling back to `summary` for those rows? Or surface a count at the end of build (`5 documents skipped — files missing`)? Proposal: count + summary line, no per-file noise.

> **Q4**: Should the introduction-detection regex (step 3 of the ladder) also match `'capítulo 1'` / `'chapter 1'` as a fallback when no `introducción` heading exists? Some books skip the introduction. Risk: matches noise like "Chapter 1: Acknowledgments." Proposal: keep the regex narrow for now (introduction/prólogo/preface), revisit if Q1 tuning shows weak signal.

---

## Implementation Plan

- [ ] Add migration: `ALTER TABLE documents ADD COLUMN content_preview TEXT` (and `content_preview_source TEXT` if Q2 = yes).
- [ ] Add `wst.document.build_content_preview(path, summary) -> tuple[str | None, str]` implementing the ladder. Returns `(preview, source)` where `source ∈ {summary, toc, intro, first-pages, title-only, none}`.
- [ ] Hook `build_content_preview()` into the ingest pipeline so new documents get the field populated immediately.
- [ ] Add lazy backfill at the start of `topics_build()` ([`cli.py:1795`](../../src/wst/cli.py)): for rows where `content_preview IS NULL` and `path` exists, compute and persist.
- [ ] Update [`topics.py:191`](../../src/wst/topics.py) `build_vocabulary()` to read `content_preview` (with `summary[:300]` fallback for NULL).
- [ ] Update the cluster-naming prompt at [`topics.py:22-46`](../../src/wst/topics.py) to include `content_preview` in the per-document context (subject to its own char budget).
- [ ] Smoke-test on the user's existing library: re-run `wst topics build` and verify topic coherence improves on books that previously landed in noise clusters.
- [ ] Document the new column and the ladder behavior in the topics section of `README.md`.
