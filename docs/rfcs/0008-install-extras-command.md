# RFC 0008: Install Extras via CLI and GUI

**Issue**: #22  
**Status**: Implementing  
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

Add a new top-level command that installs an optional extras group:

```
wst install ocr       # installs wst-library[ocr] + system deps (Ghostscript, Tesseract)
wst install topics    # installs wst-library[topics]
wst install --list    # shows all extras and their install status
wst install ocr --upgrade   # force upgrade of already-installed extra
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
@click.option("--upgrade", is_flag=True)
def install(extra: str | None, list_extras: bool, upgrade: bool) -> None:
    """Install optional feature packages."""
```

**Status detection**: check importability of key modules before installing:

```
$ wst install --list
ocr       ✗ not installed   → wst install ocr
topics    ✓ installed
```

**Auto-upgrade**: if `--upgrade` is passed (or will be triggered automatically by `wst` on startup when a newer version is detected), re-run the install with `--upgrade` on the pip call.

### 2 — System dependencies for OCR

`ocrmypdf` requires Ghostscript and Tesseract, which are not Python packages. `wst install ocr` will:

1. **Check** if Ghostscript and Tesseract are available (`shutil.which("gs")`, `shutil.which("tesseract")`).
2. If missing, **download and install** them using the platform-appropriate method:

| Platform | Ghostscript | Tesseract |
|----------|-------------|-----------|
| macOS | Download `.pkg` from ghostscript.com + run installer, or `brew install ghostscript` if Homebrew is present | `brew install tesseract` or download `.pkg` |
| Windows | Download NSIS `.exe` from ghostscript.com + silent install (`/S`), UB Mannheim Tesseract `.exe` + silent install | Same |
| Linux | `sudo apt-get install ghostscript tesseract-ocr` | Same |

The download-and-run approach (no Homebrew/apt required) is the baseline; package managers are used when detected.

### 3 — Bundled (PyInstaller) case: side-car venv with embedded Python

When `wst` is packaged as a PyInstaller one-file binary, `sys.executable` points to the frozen binary — `pip` is unavailable. Rather than requiring system Python, we bundle a Python interpreter alongside the app using **python-build-standalone**.

**Flow**:

1. The Tauri app ships a platform-specific `python-embed/` directory alongside the bundled `wst` binary, containing a standalone Python interpreter (from [python-build-standalone](https://github.com/indygreg/python-build-standalone) releases, ~30 MB compressed).
2. On first `wst install`, if running frozen, the command detects `sys.frozen` and uses `python-embed/python` (or `python-embed/python.exe`) instead of `sys.executable`.
3. A side-car venv is created at `~/.wst/extras/` using that embedded interpreter: `python-embed/python -m venv ~/.wst/extras/`.
4. The extras are installed into the venv, and `~/.wst/extras/lib/pythonX.Y/site-packages` is added to `sys.path` at `wst` startup.

The CI release workflow downloads the appropriate python-build-standalone artifact for each platform and places it in `app/src-tauri/resources/python-embed/` during the build.

### 4 — Tauri app: Settings / Extras page

Add a **Settings → Extras** section that:

1. On mount, calls `wst install --list --json` to fetch install status.
2. Renders a card per extra with name, description, install/upgrade button.
3. On button click, invokes `wst install <extra>` via Tauri's `Command` API and streams stdout/stderr to a log panel.
4. Shows a spinner while running, then ✓/✗ based on exit code.

---

## Decisions from review

| Question | Decision |
|----------|----------|
| Bundled case | Side-car venv at `~/.wst/extras/` using embedded Python (python-build-standalone) |
| Upgrades | `--upgrade` flag supported; auto-upgrade path TBD in a follow-up |
| System deps (OCR) | `wst install ocr` handles Ghostscript + Tesseract — downloads and runs installers, uses package managers when detected |

---

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| Bundle all extras in PyInstaller | Bundle grows ~300 MB; user pays the cost even if they never use OCR/topics |
| Require system Python for side-car | On Windows, Python is not installed by default; embedded Python removes this dependency |
| Scope to Python packages only (no system deps) | OCR is unusable without Ghostscript/Tesseract; completing the install in one step is better UX |
| Auto-install on first use (transparent) | Installs without consent and is potentially slow mid-command |

---

## Implementation Plan

- [ ] Add `wst install <extra>` command to `src/wst/cli.py`
- [ ] Add `--list` / `--list --json` and `--upgrade` flags
- [ ] Implement system dependency installer (Ghostscript + Tesseract) with platform detection
- [ ] Detect `sys.frozen` and route to embedded Python / side-car venv
- [ ] Download python-build-standalone in CI and bundle in `app/src-tauri/resources/`
- [ ] Add side-car venv creation + `sys.path` injection at `wst` startup
- [ ] Write tests for install status detection and frozen-mode path
- [ ] Add **Settings → Extras** section to Tauri app
- [ ] Wire up streaming `wst install` output in the GUI
- [ ] Update help text for `wst ocr` and `wst topics` to reference `wst install`
