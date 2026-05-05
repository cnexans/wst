# RFC 0008: Install Extras via CLI and GUI

**Issue**: #22  
**Status**: Draft — awaiting approval  
**Branch**: `rfc/22-instalacion-paquetes-extra`

---

## Problem

Optional features (OCR via `ocrmypdf`, topic modeling via `sentence-transformers` + `scikit-learn`) require users to manually run:

```
pip install "wst-library[ocr]"
pip install "wst-library[topics]"
```

This friction is especially high for non-technical users using the Tauri app. There is no in-app discovery of what's missing or how to install it. Features silently fail or show cryptic errors when the extras aren't installed.

---

## Proposed Solution

### 1 — `wst install <extra>` CLI command

Add a new top-level command that installs an optional extras group into the current Python environment:

```
wst install ocr       # installs wst-library[ocr]
wst install topics    # installs wst-library[topics]
wst install --list    # shows all extras and their install status
```

Implementation in `src/wst/cli.py`:

```python
EXTRAS = {
    "ocr": ("wst-library[ocr]", ["ocrmypdf"]),
    "topics": ("wst-library[topics]", ["sentence_transformers", "sklearn"]),
}

@cli.command()
@click.argument("extra", required=False)
@click.option("--list", "list_extras", is_flag=True)
def install(extra: str | None, list_extras: bool) -> None:
    """Install optional feature packages."""
```

The command resolves the Python executable via `sys.executable` and runs:

```python
subprocess.run([sys.executable, "-m", "pip", "install", package_spec], check=True)
```

This ensures the packages land in the same environment as `wst` itself.

**Status detection**: before installing, check importability of the key modules to show what's already installed:

```
$ wst install --list
ocr       ✗ not installed   → wst install ocr
topics    ✓ installed
```

### 2 — Tauri app: Settings / Extras page

Add a new **Settings** sidebar item (or a dedicated **Extras** section in an existing settings panel) that:

1. On mount, calls `wst install --list --json` (a machine-readable variant) to fetch install status.
2. Renders a card per extra with name, description, and an **Install** button for uninstalled ones.
3. On button click, invokes `wst install <extra>` via Tauri's `Command` API and streams stdout to a log panel.
4. Shows a spinner while running, then ✓/✗ based on exit code.

No new Tauri Rust code is needed — the Tauri app already shells out to the bundled `wst` binary for all operations.

### Bundled (PyInstaller) case

When `wst` is packaged as a PyInstaller one-file binary, `sys.executable` points to the frozen binary itself, not a Python interpreter — `pip` is not available.

Two options for this case:

| Option | Approach |
|--------|----------|
| **A — ship all extras in the bundle** | Add `ocr` and `topics` deps to the PyInstaller spec. Larger bundle (~400 MB → ~700 MB) but zero install friction |
| **B — side-car venv** | On first `wst install`, create a side-car venv at `~/.wst/extras/` using the system Python, install there, and add it to `sys.path` at startup |

Option A is simpler and eliminates the install flow entirely for Tauri app users. Option B keeps the bundle lean but requires a system Python.

> See **Q1** below for input on which to pursue.

---

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| Document-only (better README) | Doesn't help Tauri app users who never see the README |
| Auto-install on first use (transparent) | Installs without consent; surprising and potentially slow mid-command |
| Separate installers per platform | Duplicates distribution work; extras are pip packages, not system packages |

---

## Open Questions

> **Q1**: For the Tauri/bundled case, do you prefer Option A (bundle all extras — simpler UX, larger download) or Option B (side-car venv — lean bundle, needs system Python)?

> **Q2**: Should `wst install` support upgrading already-installed extras (`--upgrade` flag), or just initial install?

> **Q3**: `ocrmypdf` has a system-level dependency (Ghostscript, Tesseract). Should `wst install ocr` also check for and guide the user through system dependency installation, or scope this to Python packages only?

---

## Implementation Plan

- [ ] Add `wst install <extra>` command to `src/wst/cli.py`
- [ ] Add `--list` / `--list --json` output for status detection
- [ ] Write tests for install status detection (mock importlib)
- [ ] Add **Extras** section to the Tauri app settings UI
- [ ] Wire up `wst install <extra>` via Tauri `Command` API with streaming output
- [ ] Decide and implement bundled-case strategy (Q1)
- [ ] Update help text / docs for `wst ocr` and `wst topics` to reference `wst install`
