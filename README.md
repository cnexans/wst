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
- **Organized library**: Files sorted by type (`books/`, `papers/`, `notes/`, `exercises/`, `guides/`) with consistent naming (`Author - Title (Year).pdf`)
- **SQLite search index**: Full-text search across title, author, tags, subject, and summary via FTS5
- **Interactive browser**: Fuzzy-search your library, view and edit metadata interactively
- **Cloud backup**: Backup files to iCloud Drive (macOS/Windows), with extensible provider system for future S3 support
- **Extensible backends**: Abstract layers for AI (Claude CLI, future API/SDK) and storage (local filesystem, future S3)

## Installation

### pipx (recommended, all platforms)

```bash
pipx install wst-library
```

### pip

```bash
pip install wst-library
```

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

# Ingest from current directory
wst ingest .

# Ingest from default inbox (~/wst/inbox/)
wst ingest

# Ingest with manual confirmation for each file
wst ingest --confirm

# Re-ingest files with fresh AI metadata (e.g. after enabling web search)
wst ingest --reprocess

# Search
wst search "machine learning"
wst search --author "Knuth"
wst search --type textbook
wst search --subject "Mathematics"

# List all documents
wst list
wst list --type paper --sort year

# Show full details
wst show 1
wst show "Design Patterns"

# Interactive browser — fuzzy search, view and edit metadata
wst browse

# Edit a specific document
wst edit 1
wst edit "Player's Handbook"

# Backup to iCloud
wst backup icloud                    # interactive: all or select file
wst backup icloud 1                  # backup specific file by ID
wst backup icloud "Player's Handbook" # backup by title
wst backup                           # interactive: choose provider
```

## Commands

| Command | Description |
|---------|-------------|
| `wst ingest [PATH] [--confirm] [--reprocess]` | Ingest PDFs from a path or the inbox, generate metadata with AI |
| `wst search <query> [--author] [--type] [--subject]` | Full-text search across the index |
| `wst list [--type] [--sort]` | List all documents in the library |
| `wst show <id-or-title>` | Show complete metadata for a document |
| `wst edit <id-or-title>` | Interactively edit metadata for a document |
| `wst browse` | Interactive TUI for browsing and editing documents |
| `wst backup [provider] [id-or-title]` | Backup files to a cloud provider (iCloud, future S3) |

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
- `claude` CLI (authenticated) for AI metadata generation
- macOS, Windows, or Linux

## License

MIT with Commons Clause — free to use, modify, and distribute. Commercial sale rights reserved to the author. See [LICENSE](LICENSE).
