# RFC 0014: Backup all to iCloud and Google Drive (CLI + GUI)

**Issue**: #35
**Status**: Draft — awaiting approval
**Branch**: `rfc/35-backup-all-cloud-providers`

---

## Problem

`wst` already has a `backup` system with two providers — `icloud` (filesystem-based, writes into the macOS/Windows iCloud Drive sync folder) and `s3` (API-based). The CLI can already back up the **entire library** to either provider via `wst backup` (interactive) or a single file via `wst backup icloud <ID>` / `wst backup s3 <ID>` ([`backup.py:303-313`](../../src/wst/backup.py), [`cli.py:393-488`](../../src/wst/cli.py)).

Two gaps:

1. **No Google Drive support.** Many users sync libraries with Google Drive's desktop client (`~/Library/CloudStorage/GoogleDrive-<email>/My Drive` on macOS, `Google Drive` folder on Windows) the same way they use iCloud. Today they have to copy files manually out of `~/wst` or set up S3, which they may not have.
2. **The GUI only backs up one document at a time, and only to iCloud.** The Tauri surface exposes `backup_to_icloud(id)` only ([`commands.rs:283`](../../app/src-tauri/src/commands.rs)) — there's no GUI equivalent of the CLI's "backup all" or "choose provider" flows. Desktop-app users have to drop to the CLI for bulk or non-iCloud backup.

The user's request — *"Add option to backup all in iOS and Google Drive. It should rely on auto sync Google Drive folder and iOS. Should be available in CLI and in GUI"* — closes both gaps in one feature.

---

## Proposed Solution

Add a third backup provider that writes into the user's local Google Drive sync folder (mirroring `ICloudProvider`), and expand the GUI to expose **backup-all + provider choice** for both filesystem-sync providers.

### Provider: `GoogleDriveProvider`

A new entry in `wst/backup.py` modeled directly on `ICloudProvider` (filesystem write into a user-synced folder):

| Concern | Behavior |
|---|---|
| **Detection** | macOS: glob `~/Library/CloudStorage/GoogleDrive-*/My Drive` (Google appends the account email, so detection has to handle multiple matches). Windows: `~/Google Drive/My Drive` then fall back to `G:/My Drive`. Linux: `~/GoogleDrive` (rclone/insync convention), prompt if missing. |
| **Configuration** | Subfolder name (default `wst`), like iCloud. Optional manual root path stored in `~/wst/config.json` if auto-detection fails. |
| **`backup_file` / `backup_all`** | `shutil.copy2` into the synced folder, preserving relative path. Identical structure to `ICloudProvider`. |
| **`is_configured`** | True iff the detected (or user-supplied) Google Drive root exists. |

Registered in `PROVIDERS` so `wst backup gdrive` and `wst backup gdrive <ID>` mirror the existing iCloud commands.

> This is **sync-folder backup**, not the Google Drive API. We are deliberately *not* adding OAuth/API-based upload here — that would be a separate provider with its own auth and error model. "Auto sync" in the issue body confirms the user's intent is the local sync folder approach.

### CLI changes (small)

- Register `GoogleDriveProvider` in the `PROVIDERS` dict in `backup.py`.
- Add a `backup gdrive [IDENTIFIER]` Click subcommand alongside the existing `backup icloud` and `backup s3` commands. Same shape as `backup_icloud` ([`cli.py:440-486`](../../src/wst/cli.py)) — interactive when no identifier, single-file when identifier passed.

The interactive `wst backup` flow picks up the new provider automatically through the `PROVIDERS` registry — no special-casing needed.

### GUI changes

The GUI today exposes one Tauri command (`backup_to_icloud(id)`) and one button (☁ iCloud) inside [`BookDetail.tsx:155-160`](../../app/src/components/BookDetail.tsx). Two changes:

1. **Add Tauri commands** in `app/src-tauri/src/commands.rs`:
   - `backup_document(id, provider)` — single-file backup. Replaces `backup_to_icloud`.
   - `backup_all(provider)` — library-wide backup, returns `{ provider, backed_up_files }` mirroring `run_backup_all`'s return shape ([`backup.py:418-427`](../../src/wst/backup.py)).
   - `list_backup_providers()` — returns `[{ name, configured }]` so the UI can grey out unconfigured providers.

2. **UI surface**:
   - In `BookDetail`: change the "☁ iCloud" button to a small dropdown (iCloud / Google Drive). iCloud stays default for back-compat. Status messages keep their current shape.
   - Add a **Backup all** entry point — see Q2 — that opens a modal listing configured providers and runs `backup_all(provider)`, with progress (event stream) and a final count.

The CLI's `backup_all(library_path, emit=True)` writes to stdout — for the GUI we'll add an optional progress callback so progress can stream over a Tauri event channel.

---

## Alternatives Considered

| Alternative | Why rejected |
|---|---|
| Use the Google Drive API (OAuth) instead of the local sync folder | Heavier auth, requires a Google Cloud project, and behaves differently from `ICloudProvider`. User explicitly said *"auto sync Google Drive folder"* — they want the filesystem-sync approach. Could be added later as `gdrive-api` if needed. |
| Skip the GUI changes; add Google Drive only in CLI | Issue explicitly requires GUI parity. Half the request. |
| Single "backup everywhere" command that pushes to all configured providers in one go | Surprising default (cost, time, partial failures). Better as a future enhancement once we have provider selection UI working — explicit choice first. |
| Reuse `s3` provider for Google Cloud Storage instead of adding a new provider | Different feature (cloud-API uploads vs. local sync folder). Would also confuse users who expect Google Drive ≠ GCS. |

---

## Open Questions

> **Q1**: For Google Drive on macOS, the canonical path under modern Google Drive for Desktop is `~/Library/CloudStorage/GoogleDrive-<email>/My Drive`. Account emails are dynamic, so detection has to glob. **Should we (a) auto-pick the first match, (b) prompt to choose if there are multiple, or (c) always require manual configuration?** Lean (b) with (a) as the silent default when only one account is signed in.

> **Q2**: Where should "Backup all" live in the GUI? (a) new top-level button in `Toolbar.tsx`, (b) a new "Settings / Backup" pane in `Sidebar.tsx`, (c) inside the existing `ExtrasPanel.tsx`. Backup is a configuration-style action, not per-book — leans toward (b) or (c).

> **Q3**: For the CLI, should `wst backup gdrive` follow the same "subfolder" convention as iCloud (default `wst/`)? Or copy directly into the Google Drive root? Subfolder is safer (no clutter) — proposing default `wst`.

> **Q4**: When neither provider is configured and the user hits "Backup all" in the GUI, what should happen? Show a config wizard inline, or tell them to run `wst backup` once in the CLI? Inline wizard is nicer but more code to write.

> **Q5**: For Tauri command naming — keep `backup_to_icloud` as a deprecated shim and add new `backup_document(id, provider)`, or rename in one shot and update `BookDetail.tsx`? The shim adds churn for little compatibility benefit (the GUI is the only caller). Lean toward in-place rename.

---

## Implementation Plan

- [ ] Add `GoogleDriveProvider` to `src/wst/backup.py` with macOS / Windows / Linux detection, `configure()`, `is_configured()`, `backup_file()`, `backup_all()`.
- [ ] Register `gdrive` in `PROVIDERS`.
- [ ] Add `wst backup gdrive [ID]` Click command in `src/wst/cli.py` mirroring `backup_icloud`.
- [ ] Tests: detection logic (mocked OS), backup-all into a temp dir acting as the "sync folder", config save/load.
- [ ] Add Tauri commands `backup_document`, `backup_all`, `list_backup_providers` in `app/src-tauri/src/commands.rs`; register them in `lib.rs`.
- [ ] Update `app/src/lib/tauri.ts` with the new Promise wrappers.
- [ ] Update `BookDetail.tsx`: replace single iCloud button with a provider picker; keep the existing UX/status message shape.
- [ ] Add a "Backup all" UI entry point (location decided in Q2) and a progress modal.
- [ ] Update `README.md` backup section to document the new provider and the new GUI flow.
- [ ] Smoke-test on macOS with both iCloud and Google Drive configured.
