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

- **AI-powered metadata**: Automatically extracts and completes metadata (title, author, type, year, summary, tags, etc.) using Claude CLI
- **Organized library**: Files sorted by type (`libros/`, `papers/`, `notas/`, `ejercicios/`, `guias/`) with consistent naming (`Author - Title (Year).pdf`)
- **SQLite search index**: Full-text search across title, author, tags, subject, and summary via FTS5
- **Extensible backends**: Abstract layers for AI (Claude CLI, future API/SDK) and storage (local filesystem, future S3)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or via Make:

```bash
make install
```

## Quick Start

```bash
# Create inbox and add PDFs
mkdir inbox
cp ~/Downloads/*.pdf inbox/

# Ingest — scans, generates metadata with AI, organizes
wst ingest

# Ingest with manual confirmation for each file
wst ingest --confirm

# Ingest from a custom folder
wst ingest --inbox ~/Documents/papers/

# Search
wst search "machine learning"
wst search --author "Knuth"
wst search --type textbook

# List all documents
wst list
wst list --type paper --sort year

# Show full details
wst show 1
wst show "Design Patterns"
```

## Commands

| Command | Description |
|---------|-------------|
| `wst ingest [--inbox PATH] [--confirm]` | Scan inbox for PDFs, generate metadata with AI, organize into library |
| `wst search <query> [--author] [--type]` | Full-text search across the index |
| `wst list [--type] [--sort]` | List all documents in the library |
| `wst show <id-or-title>` | Show complete metadata for a document |

## Library Structure

```
library/
├── libros/          # book, novel, textbook
├── papers/          # paper
├── notas/           # class-notes
├── ejercicios/      # exercises
├── guias/           # guide-theory, guide-practice
└── wst.db           # SQLite index
```

## Documentation

See [docs/README.md](docs/README.md) for architecture details and diagrams.

## Requirements

- Python 3.11+
- `claude` CLI (authenticated) for AI metadata generation

## License

MIT with Commons Clause — free to use, modify, and distribute. Commercial sale rights reserved to the author. See [LICENSE](LICENSE).
