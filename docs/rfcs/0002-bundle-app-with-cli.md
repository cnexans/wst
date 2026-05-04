# RFC 0002: Bundle App with CLI

**Issue**: #8  
**Status**: Draft — awaiting approval  
**Branch**: `rfc/issue-8-bundle-app-cli`

---

## Problem

Currently, users must install two separate components independently:

1. **CLI** — `pipx install wst-library` (or `make install`)
2. **App** — `make build-app && make install-app`

The Tauri app (`app/src-tauri/src/commands.rs`) calls the `wst` binary via `std::process::Command`, searching `~/.local/bin/wst` and `/usr/local/bin/wst`. If the CLI isn't already installed, the app silently fails or produces cryptic errors.

A user who installs only the `.app` file gets a broken experience.

---

## Proposed Solution

Bundle the `wst` CLI as a **Tauri sidecar binary** so that the distributed `.app` (and `.dmg`) contains a working `wst` binary. Users get a single artifact that works out of the box.

### How Tauri sidecars work

Tauri's `bundle.externalBin` field declares binaries that are copied into the app bundle at `Contents/MacOS/`. The app reads the sidecar path via `tauri::api::process::current_binary()` or the `tauri_utils::platform::current_exe()` sibling path at runtime.

### Implementation plan

#### Step 1 — Build a standalone `wst` binary

Python is not directly embeddable as a sidecar. We need a self-contained executable. Two options:

**Option A — PyInstaller** (recommended)
- `pyinstaller --onefile src/wst/cli.py` produces a single binary with the Python runtime embedded
- Cross-platform; output is ~30–60 MB compressed
- Already battle-tested for CLI tools

**Option B — `shiv`**
- Produces a `.pyz` zipapp; requires Python on the target system (not truly self-contained)
- Not suitable here since users may not have Python

**Recommendation: PyInstaller**.

Add a Makefile target:

```makefile
build-cli-binary:
    pyinstaller --onefile \
        --name wst \
        --collect-all wst \
        --hidden-import wst \
        pyinstaller_entry.py
```

Where `pyinstaller_entry.py` is a minimal shim:

```python
from wst.cli import cli
if __name__ == "__main__":
    cli()
```

#### Step 2 — Register as a Tauri sidecar

In `app/src-tauri/tauri.conf.json`:

```json
"bundle": {
  "externalBin": ["../../../dist/wst"]
}
```

Tauri requires the binary to be named with a target triple suffix during build (e.g. `wst-aarch64-apple-darwin`) but strips it at runtime. The Makefile build step handles renaming.

#### Step 3 — Update `which_wst()` in `commands.rs`

```rust
fn which_wst() -> String {
    // 1. Try sidecar path (app bundle)
    if let Ok(exe) = std::env::current_exe() {
        let sidecar = exe.parent().unwrap().join("wst");
        if sidecar.exists() {
            return sidecar.to_string_lossy().to_string();
        }
    }
    // 2. Fall back to PATH locations (dev mode / pipx install)
    let candidates = [
        dirs::home_dir().map(|h| h.join(".local/bin/wst")),
        Some(std::path::PathBuf::from("/usr/local/bin/wst")),
    ];
    for c in candidates.into_iter().flatten() {
        if c.exists() {
            return c.to_string_lossy().to_string();
        }
    }
    "wst".to_string()
}
```

#### Step 4 — Update Makefile

```makefile
build-app: build-cli-binary
    cd app && npm install && npx tauri build

build-cli-binary:
    pip install pyinstaller
    pyinstaller --onefile --name wst --collect-all wst pyinstaller_entry.py
    # Rename for Tauri target-triple convention
    mv dist/wst dist/wst-$(shell rustc -vV | grep host | cut -d' ' -f2)
```

#### Step 5 — Add `pyinstaller_entry.py` at repo root

A one-line shim that PyInstaller uses as the entry point.

---

## Distribution

After this change:
- `make build-app` produces `app/src-tauri/target/release/bundle/macos/Wan Shi Tong.app`
- The `.app` contains a working `wst` binary at `Contents/MacOS/wst`
- The `.dmg` (from Tauri's `dmg` target) is a single drag-to-Applications artifact

---

## Open Questions

> **Q1**: Should the bundled `wst` binary also install itself to `~/.local/bin/wst` on first launch, so it's available from the terminal even if the user only has the `.app`? This would let people who install via the GUI still use the CLI.

> **Q2**: Are there plans for Windows/Linux distribution, or is macOS the only target for now? PyInstaller handles all three, but CI matrix and code-signing would differ.

> **Q3**: Do you want to keep `pipx install wst-library` as the CLI-only install path in addition to the bundled app? Or should the app become the canonical distribution?

---

## Files Changed (implementation phase)

- `pyinstaller_entry.py` — new entry point shim (3 lines)
- `app/src-tauri/tauri.conf.json` — add `externalBin`
- `app/src-tauri/src/commands.rs` — update `which_wst()` to check sidecar path first
- `Makefile` — add `build-cli-binary` target, update `build-app` to depend on it
- `pyproject.toml` — add `pyinstaller` to `[dev]` optional deps
