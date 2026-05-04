# RFC 0003: Subject Assignment by Clustering

**Issue**: #12  
**Status**: Approved — implementation in progress  
**Branch**: `rfc/issue-12-subject-by-clustering`

---

## Problem

Currently, the `subject` field (e.g., "Mathematics", "Computer Science") is assigned by the LLM during `wst ingest`, using only the individual document's content as context. This produces two problems:

1. **Inconsistency across the corpus** — two books on Calculus may get "Mathematics" and "Matemáticas" depending on the document's language.

2. **Redundancy with topics** — once `wst topics build` runs, the library already has a curated topic vocabulary. The `subject` field should be the broader parent area ("Mathematics"), but it is set independently and often overlaps with or contradicts topic assignments.

---

## Approved Solution

Replace per-document LLM subject inference with **two-level clustering**: after `wst topics build` produces fine-grained topic clusters, run a **second KMeans pass** on those cluster centroids with a smaller K to produce broader subject groups. The AI names the subject groups (which are inherently broader because they already aggregate multiple related topics).

### Two-phase approach

#### Phase 1 — Subject clustering (happens inside `wst topics build`)

After the main KMeans produces `k` topic centroids, run a second KMeans on those centroids:

```python
n_subjects = min(max(2, k // 3), k - 1, 8)
km2 = KMeans(n_clusters=n_subjects, random_state=42, n_init="auto")
super_labels = km2.fit_predict(centroids)   # maps each topic → subject cluster
```

For each subject cluster, gather the topic names it contains and ask the AI to name the group:

```
Topics in this group: ["Cálculo", "Álgebra Lineal", "Geometría"]
→ AI response: "Matemáticas"
```

This produces a `topic_to_subject` mapping: `{"Cálculo": "Matemáticas", "Álgebra Lineal": "Matemáticas", ...}`.

#### Phase 2 — Subject backfill (runs automatically in `wst topics assign`)

After topics are assigned to each document, set `subject` from the primary (first) topic:

```python
for entry in db.list_all():
    if entry.metadata.topics:
        subject = topic_to_subject.get(entry.metadata.topics[0])
        if subject:
            entry.metadata.subject = subject
            db.update(entry)
```

### Approved answers to open questions

- **Q1** — Automatic: `wst topics assign` always backfills subjects; no flag needed.
- **Q2** — LLM fallback: during `wst ingest`, keep setting subject via LLM. Topics build overwrites it.
- **Q3** — Yes: `wst topics subjects` command lists the topic→subject mapping so users can inspect it.
- **Q4** — No hardcoded allow-list: the AI freely names the subject groups in Spanish.

### Data model change

Extend `topics_vocabulary` table with a `subjects` column:

```sql
ALTER TABLE topics_vocabulary ADD COLUMN subjects TEXT;
-- subjects column: '{"Cálculo": "Matemáticas", "Programación": "Ciencias de la Computación", ...}'
```

---

## Files Changed

- `src/wst/topics.py` — add `_build_subject_naming_prompt`, `_build_subject_mapping`, `backfill_subjects`; update `build_vocabulary` return to include `topic_to_subject`; update `save_vocabulary` to persist subjects
- `src/wst/db.py` — extend `TOPICS_VOCABULARY_SCHEMA` with `subjects` column; add `save_topics_vocabulary(vocab, subjects)`, `load_topics_subjects()`, `update_subject(doc_id, subject)` migration
- `src/wst/cli.py` — update `topics build` and `topics assign` to backfill subjects; add `wst topics subjects` subcommand
