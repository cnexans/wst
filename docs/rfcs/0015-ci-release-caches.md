# RFC 0015: Cache Rust/npm/pip in the release workflow

**Issue**: #37
**Status**: Implementing
**Branch**: `rfc/37-ci-release-caches`

---

## Problem

`release.yml` runs three platform jobs in parallel (`dmg`, `windows-installer`, `linux`), called via `workflow_call` from `release-on-tag.yml`. Each job recompiles **everything** from scratch:

- Tauri's Rust crate under `app/src-tauri/target/`
- The frontend's `app/node_modules/`
- Python deps for the bundled CLI (`pip install -e . numpy scikit-learn scipy pyinstaller`)

`grep "actions/cache\|rust-cache\|cache:" .github/workflows/release.yml` returns nothing — there is no caching anywhere in the workflow today. Every release pays the full cold-build cost on three runners.

This is the largest avoidable cost in the release pipeline. The three jobs already run in parallel, so wall-clock time is bounded by the slowest job (typically macOS DMG). Cache hits should reduce the slow path noticeably.

---

## Proposed Solution

Add three caches to each platform job in `release.yml`. None of the runners share caches with each other — GitHub keys cache by OS automatically — so the change is purely additive per job.

### What gets cached

| Cache | Action | Scope |
|---|---|---|
| Rust target dir + registry | `Swatinem/rust-cache@v2` (with `workspaces: app/src-tauri -> target`) | Per-OS, keyed on `Cargo.lock` |
| npm dependencies | `actions/setup-node@v4` with `cache: npm` and `cache-dependency-path: app/package-lock.json` | Per-OS, keyed on lockfile |
| pip dependencies | `actions/setup-python@v5` with `cache: pip` | Per-OS, keyed on `pyproject.toml` |

### Where the steps go in each job

The new caches replace the existing `setup-node` / `setup-python` steps (which currently don't enable `cache:`) and add a `Swatinem/rust-cache@v2` step *before* `tauri build`. PyInstaller numerical deps (numpy/scipy/scikit-learn) are heavy wheels; pip cache should hit on those even when our own code changes.

### Expected impact

- **Cold build** (no cache, e.g. first run after lockfile change): unchanged.
- **Warm build** (typical release on `main`): -5 to -10 min on macOS, less on Linux/Windows but still meaningful. Hard to be precise without measuring; we'll know after the first warm run.
- **Storage**: GitHub gives 10 GB per repo, evicted LRU. Three caches × three OSes ≈ a few GB. Within budget.

---

## Alternatives Considered

| Alternative | Why rejected |
|---|---|
| `sccache` (compile cache for Rust) | Stronger but more setup (bucket or local config). Try `Swatinem/rust-cache` first; revisit if it's not enough. |
| Skip PyInstaller rebuild when `pyproject.toml` is unchanged | Plausible but PyInstaller's outputs depend on the full Python env, not just the lockfile. pip cache is the safer lever. |
| Cache the macOS universal target | Out of scope — we don't ship universal binaries today. |
| Move to a single self-hosted runner with persistent state | Operational overhead, not worth it for this project's release cadence. |

---

## Open Questions

None — the issue body and the actions involved are well-known. Ready for approval.

---

## Implementation Plan

- [ ] In `release.yml`, replace the existing `setup-node` step in each platform job with one that enables `cache: npm` and `cache-dependency-path: app/package-lock.json`.
- [ ] In each platform job, add `actions/setup-python@v5` with `cache: pip` (or update the existing Python setup if there is one).
- [ ] In each platform job, add `Swatinem/rust-cache@v2` with `workspaces: app/src-tauri -> target` *before* the `npx tauri build` step.
- [ ] Trigger a no-op release (or rely on the next regular release) to populate caches, then a follow-up release to confirm warm-cache speedup.
- [ ] Note the timing in the PR description so we have a baseline for future tuning.
