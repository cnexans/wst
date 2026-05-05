# RFC 0009: Reliable releases on merge to main

**Issue**: #25
**Status**: Draft — awaiting approval
**Branch**: `rfc/25-release-on-merge`

---

## Problem

Issue #25 reports that merging PR #24 to `main` (run [25399495953](https://github.com/cnexans/wst/actions/runs/25399495953)) did not publish a release with artifacts. Investigation shows this is **working as designed** — but the design is fragile and surprising.

`auto-release.yml` runs on every push to `main`, but its `check` job gates the rest of the workflow on a single condition:

```yaml
if gh release view "v$VERSION" > /dev/null 2>&1; then
  echo "should_release=false"
else
  echo "should_release=true"
fi
```

So a release fires **only** when `pyproject.toml`'s `version` field is set to a value that has no matching GitHub release yet. In practice this means:

- Merging a `chore: bump version to X.Y.Z` PR → release fires.
- Merging anything else (feature, fix, RFC, refactor) without a bump → silent skip.

The current workflow run that prompted the issue is exactly this case: PR #24 (an RFC merge) didn't bump the version, so the `check` job set `should_release=false` and the `test`/`pypi`/`dmg`/`release` jobs were all skipped. From the user's point of view this looks broken — the workflow says "success" but no artifacts appear on the Releases page.

There are two real problems here:

1. **Trigger model is implicit.** Contributors must remember to bump `pyproject.toml` in the same PR (or a follow-up PR) as any user-visible change. Forgetting silently swallows the release.
2. **Workflow sprawl.** Four release-related workflows exist with overlapping responsibilities — easy to lose track of which one actually fires:

   | Workflow | Trigger | Purpose |
   |---|---|---|
   | `auto-release.yml` | push to `main` | Build + publish if `pyproject.toml` version is unreleased |
   | `release-on-tag.yml` | push tag `v*` | Calls `release.yml`, then creates GitHub release |
   | `release.yml` | `workflow_call` | Reusable test/pypi/dmg/chocolatey jobs |
   | `tag-release.yml` | `workflow_dispatch` | Manual: bump version, tag, call `release.yml` |

   `auto-release.yml` and `release-on-tag.yml` both build artifacts, both create a release, both run on different events. A version bump merged to main races against an explicit `vX.Y.Z` tag push — whichever finishes second errors out trying to create a duplicate release/tag.

## Proposed Solution

Pick **one canonical trigger** and remove the others. Two viable directions:

### Option A — Auto-bump on merge (recommended for low ceremony)

Every merge to `main` with a `feat:` / `fix:` / `perf:` conventional-commit prefix auto-bumps the patch (or minor) version, commits the bump, tags it, and releases. RFC-only / chore / docs / refactor merges do nothing.

Pros: contributors stop thinking about versioning. Releases happen automatically when user-visible code changes.
Cons: requires conventional-commit discipline; auto-bump commits add noise to git log; harder to "batch" several commits into one release.

Implementation sketch:
- Replace `auto-release.yml` with a workflow that:
  1. Inspects commits in the push (`git log <before>..<after>`).
  2. Determines bump kind: `feat:`/`feat!:` → minor, `fix:`/`perf:` → patch, anything else → no release.
  3. Edits `pyproject.toml`, commits with `[skip ci]` to avoid recursion, pushes a tag.
- Delete `tag-release.yml` (manual bump becomes obsolete) and let `release-on-tag.yml` handle the build/publish path.

### Option B — Tag-driven only (recommended for explicit control)

Drop the push-to-main trigger entirely. Releases happen **only** when a maintainer pushes a `vX.Y.Z` tag (manually or via `tag-release.yml`'s `workflow_dispatch`). Update CONTRIBUTING / README to make this explicit.

Pros: zero magic, no auto-commits, single trigger to reason about.
Cons: maintainer must remember to cut releases; merges that should ship do not ship until someone tags.

Implementation sketch:
- Delete `auto-release.yml`.
- Keep `release-on-tag.yml` and `tag-release.yml` as the only paths.
- Add a CI check that warns (not blocks) on PRs containing `feat:` / `fix:` commits without a matching version-bump PR queued.

### Either way: collapse the workflow sprawl

Regardless of which trigger model we pick, the build/publish steps should live in a single reusable workflow (`release.yml`'s current shape) called by exactly one trigger workflow. Today `auto-release.yml` duplicates the build steps inline instead of reusing `release.yml` — that drift is why the macOS build steps in the two files differ (e.g. `auto-release.yml` collects `numpy`/`sklearn`/`scipy`; `release.yml` does not).

## Alternatives Considered

| Alternative | Why rejected (or kept as fallback) |
|---|---|
| Keep current behavior, document it loudly in CONTRIBUTING | Doesn't solve the silent-skip surprise. The workflow run reports `success` even when nothing was released — that's the actual UX bug. |
| Trigger release on every push to main, regardless of version | Creates duplicate-tag/release errors and republishes identical artifacts under new versions. PyPI also rejects republishing the same version. |
| Use `release-please` or `semantic-release` GitHub Apps | Heavier dependency; project is small enough that 30–50 lines of bash beats pulling in a release bot. Worth revisiting if Option A's bump logic grows complex. |
| Keep `auto-release.yml` and have it **fail loudly** when commits since last release contain `feat:`/`fix:` but version wasn't bumped | Decent middle ground but still requires manual bump PRs. Could be a stepping stone toward Option A. |

## Open Questions

> **Q1**: Option A (auto-bump on merge) or Option B (tag-driven only)? Or the middle-ground "fail loudly when bump is missing"?

> **Q2**: If Option A: what is the bump rule for commits like `refactor:` that touch user-visible code? Patch bump, or no release? My default would be no release — `refactor:` is an internal contract.

> **Q3**: If Option A: should the auto-bump commit be made by `github-actions[bot]` directly on `main`, or via an auto-merging PR? Direct commit is simpler; PR is auditable but adds churn.

> **Q4**: Should the build matrix in `release.yml` be unified with the one in `auto-release.yml`? Today they diverge (numpy/sklearn/scipy collection, Chocolatey job). This RFC proposes deleting one and keeping the union of both.

> **Q5**: PR #23 (RFC 0007 — multi-platform releases) proposes adding Windows + Linux build jobs to the release workflow. Should this RFC's restructuring be done **before**, **after**, or **as part of** that work? Doing it before makes #23's diff smaller; doing it after avoids two consecutive workflow rewrites.

## Implementation Plan

Plan deferred until Q1 (trigger model) is answered. Once decided, the plan will look approximately like:

- [ ] Delete the workflows we're abandoning (depends on Q1).
- [ ] Rewrite the canonical trigger workflow (auto-bump logic for Option A, or simplified tag-driven for Option B).
- [ ] Consolidate build steps into the reusable `release.yml`; remove duplication.
- [ ] Update CONTRIBUTING / README with the new release flow.
- [ ] Smoke-test by cutting a `v0.10.4` patch release.
- [ ] Coordinate with PR #23 (Q5) so multi-platform builds land in the consolidated `release.yml`, not the soon-to-be-deleted `auto-release.yml`.
