# wst — Wan Shi Tong

<div align="center">

<img src="docs/images/wan-shi-tong.png" alt="Wan Shi Tong" width="300">

*"I am Wan Shi Tong, he who knows ten thousand things."*

<sub>Character from Avatar: The Last Airbender. Avatar: The Last Airbender is a trademark of Viacom International Inc. Image used for illustrative purposes only.</sub>

</div>

---

CLI tool for organizing books and PDFs with AI-powered metadata generation.

Named after **Wan Shi Tong**, the ancient spirit who collected every piece of knowledge in the world and guarded the great library in the desert. This tool aspires to do the same for your PDFs — just with less hostility toward humans.

## Features

- **AI-powered metadata**: Automatically extracts and completes metadata (title, author, type, year, summary, tags, etc.) using Claude CLI with web search for missing fields (year, ISBN, publisher)
- **OCR support**: Optionally OCR scanned PDFs before ingestion to extract text from image-based documents
- **Metadata enrichment**: Fill in missing fields (ISBN, table of contents, publisher, year) on existing documents using AI + web search, individually or in batch
- **Organized library**: Files sorted by type (`books/`, `papers/`, `notes/`, `exercises/`, `guides/`) with consistent naming (`Author - Title (Year).pdf`)
- **SQLite search index**: Full-text search across title, author, tags, subject, and summary via FTS5
- **Coverage stats**: See metadata completeness across your library, broken down by document type and field
- **Interactive browser**: Fuzzy-search your library, view and edit metadata interactively
- **Cloud backup**: Backup files to iCloud Drive, Google Drive, or S3, with extensible provider system
- **Extensible backends**: Abstract layers for AI (Claude CLI, future API/SDK) and storage (local filesystem, S3)

## Installation

### pipx (recommended, all platforms)

```bash
pipx install wst-library
```

### pip

```bash
pip install wst-library
```

### Desktop App (macOS)

Download `Wan.Shi.Tong_*.dmg` from the [latest release](https://github.com/cnexans/wst/releases/latest), open it, and drag the app to `/Applications`.

Since the app is not yet notarized by Apple, macOS may show a "damaged" warning on first launch. Run this once in Terminal to clear the quarantine flag:

```bash
xattr -cr /Applications/Wan\ Shi\ Tong.app
```

Then open the app normally.

#### Ingestar desde la GUI

The toolbar has an **Ingestar** button that opens a native picker for files or a folder. The app spawns the bundled CLI behind the scenes (`wst ingest --format ndjson`) and shows per-file progress as documents are processed. Scanned PDFs are OCR'd automatically when `ocrmypdf` is installed; if it's not, the row gets a "OCR tools not installed" note and the document is ingested with whatever text and metadata are available.

### Homebrew (macOS/Linux)

```bash
brew tap cnexans/tap
brew install wst
```

### Chocolatey (Windows)

```powershell
choco install wst
```

### From source

```bash
git clone https://github.com/cnexans/wst.git
cd wst
make install
```

## Quick Start

```bash
# Ingest PDFs from a folder
wst ingest ~/Documents/papers/

# Ingest from default inbox (~/wst/inbox/)
wst ingest

# Ingest with OCR for scanned PDFs
wst ingest --ocr

# Ingest with manual confirmation for each file
wst ingest --confirm

# Re-ingest files with fresh AI metadata
wst ingest --reprocess

# Search
wst search "machine learning"
wst search --author "Knuth"
wst search --type textbook

# List and show
wst list
wst list --type paper --sort year
wst show 1

# Edit metadata
wst edit 1
wst edit "Player's Handbook"
wst edit 42 --enrich              # fill missing fields with AI + web search

# Enrich missing metadata in batch
wst fix --dry-run                 # preview what needs fixing
wst fix --type textbook           # fix all textbooks
wst fix --field isbn --field toc  # only fill ISBN and TOC
wst fix -y                        # auto-accept all changes

# Metadata coverage stats
wst stats
wst stats --type textbook

# Interactive browser
wst browse

# Backup
wst backup icloud
wst backup gdrive          # syncs into your local Google Drive folder
wst backup gdrive --all    # back up the entire library (used by the GUI)
wst backup s3
wst backup providers --format json  # list providers and configured state
```

## Commands

| Command | Description |
|---------|-------------|
| `wst ingest [PATH]` | Ingest PDFs, generate metadata with AI. Options: `--ocr`, `--confirm`, `--reprocess`, `--verbose` |
| `wst search <query>` | Full-text search. Options: `--author`, `--type`, `--subject` |
| `wst list` | List all documents. Options: `--type`, `--sort` |
| `wst show <id-or-title>` | Show complete metadata for a document |
| `wst edit <id-or-title>` | Edit metadata interactively, or `--enrich` to fill missing fields with AI |
| `wst fix` | Batch enrich documents with missing metadata. Options: `--type`, `--field`, `--dry-run`, `-y` |
| `wst stats` | Show metadata coverage statistics. Options: `--type` |
| `wst browse` | Interactive TUI for browsing and editing documents |
| `wst ocr <id-or-path>` | Run OCR on scanned PDFs |
| `wst backup [provider]` | Backup files to iCloud, Google Drive, or S3. Providers: `icloud`, `gdrive`, `s3`. Use `--all` for full-library backup. The GUI exposes the same providers via the **Backup pane** in the sidebar. |

## How Ingestion Works

```
PDF file → [OCR (optional)] → Extract text + PDF metadata → AI generates metadata → Store + Index
```

1. **OCR** (optional, `--ocr`): Scanned PDFs are processed with `ocrmypdf` to extract text from images before metadata generation.
2. **Text extraction**: Reads existing PDF metadata and text from the first pages using PyMuPDF.
3. **AI metadata generation**: Sends the text sample to Claude CLI, which analyzes the content and uses web search to find ISBN, publisher, year, and other fields.
4. **Storage**: Files are moved to the library, organized by document type with consistent naming (`Author - Title (Year).pdf`).
5. **Indexing**: Metadata is stored in SQLite with full-text search (FTS5).

After ingestion, use `wst fix` to batch-enrich documents that are missing fields (ISBN, table of contents, etc.) — this is especially useful for scanned books where the initial AI pass may not have found all metadata.

## Library Structure

```
~/wst/
├── inbox/           # PDFs pending ingestion
└── library/
    ├── books/       # book, novel, textbook
    ├── papers/      # paper
    ├── notes/       # class-notes
    ├── exercises/   # exercises
    ├── guides/      # guide-theory, guide-practice
    └── wst.db       # SQLite index
```

## Documentation

See [docs/README.md](docs/README.md) for architecture details and diagrams.

## Requirements

- Python 3.11+
- AI backend (at least one):
  - `claude` CLI (authenticated) — default backend
  - `codex` CLI (authenticated) — use with `wst -b codex`
- macOS, Windows, or Linux

## Releasing

Releases are automatic. Use [Conventional Commits](https://www.conventionalcommits.org/) and the version will bump itself when you merge to `main`:

| Commit prefix on `main` | Effect |
|---|---|
| `feat:` / `feat!:` / `BREAKING CHANGE:` | minor bump (e.g. `0.10.3` → `0.11.0`) |
| `fix:` / `perf:` | patch bump (e.g. `0.10.3` → `0.10.4`) |
| `refactor:` / `chore:` / `docs:` / `rfc:` / `test:` / `style:` / `ci:` | no release |

On a qualifying merge, `auto-release.yml` bumps `pyproject.toml`, commits the bump as `github-actions[bot]`, and pushes a `vX.Y.Z` tag. Recursion is prevented by an actor + subject guard on the bump job, not by the GitHub CI-skip directive. After pushing the tag, `auto-release.yml` invokes `release-on-tag.yml` via `repository_dispatch` — pushes made with the default `GITHUB_TOKEN` do not trigger workflow runs, so we call the dispatch API explicitly. `release-on-tag.yml` then runs tests, builds the macOS `.dmg` / Windows `.exe` / Linux `.AppImage` / `.deb`, publishes to PyPI, optionally pushes to Chocolatey, and attaches all artifacts to a GitHub Release. Manually pushing a tag from a workstation also works as an emergency-hotfix path because that push is *not* made with `GITHUB_TOKEN`.

> **Heads-up:** never include the literal CI-skip token (open bracket, `skip` `ci`, close bracket — described, not spelled, here so this README itself doesn't trip it) in commit messages or PR descriptions for changes that should run CI. GitHub honors that token on **any line** of a commit message and silently skips every workflow. If you need to refer to it in prose, hyphenate it (`[skip-ci]`) or wrap it in inline code that the squash-merge will preserve as backticks.
>
> The `Skip-CI Guard` workflow (RFC 0012) enforces this on every PR targeting `main` — a PR whose title or body contains a literal CI-skip directive will fail the check and cannot be merged until the token is escaped.

Pre-1.0: `BREAKING CHANGE:` bumps minor (no major bumps until `1.0.0`).

**Emergency hotfix:** push a `vX.Y.Z` tag directly. `release-on-tag.yml` will pick it up and build/release without needing the auto-bump step.

## License

MIT with Commons Clause — free to use, modify, and distribute. Commercial sale rights reserved to the author. See [LICENSE](LICENSE).
