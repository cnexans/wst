# RFC 0007: Multiplatform Releases

**Issue**: #21  
**Status**: Draft — awaiting approval  
**Branch**: `rfc/21-soporte-multiplataforma`

---

## Problem

Release artifacts currently cover only macOS (.dmg via the `dmg` job). The Chocolatey job publishes to the Chocolatey registry but does not attach a Windows installer to the GitHub release. Linux users have no binary artifact at all — they must install from PyPI and run the CLI only, or build Tauri locally.

The goal is for every tagged release to include **both CLI and GUI artifacts** for all three platforms directly on the GitHub release page.

---

## Proposed Solution

Add two new build jobs to `.github/workflows/release.yml` — one for Windows, one for Linux — mirroring the existing `dmg` job structure. Each job produces **two artifacts per platform**:

1. A **standalone CLI binary** (`wst` / `wst.exe`) built via PyInstaller.
2. A **GUI installer** (Tauri app) that bundles the CLI internally.

Each job:
1. Checks out the tag.
2. Builds a standalone `wst` CLI binary via PyInstaller (must run on the target OS — no cross-compilation).
3. Copies the binary into `app/src-tauri/binaries/` with the Rust target triple suffix.
4. Runs `npx tauri build` to produce the platform GUI installer.
5. Uploads both artifacts.

The `github-release` job then downloads all artifacts and attaches them to the release.

### Artifact matrix

| Platform | CLI artifact | GUI artifact |
|----------|-------------|-------------|
| macOS    | `wst-macos` (standalone binary) | `wst_<ver>_universal.dmg` |
| Windows  | `wst.exe` (standalone binary) | `wst_<ver>_x64-setup.exe` (NSIS) |
| Linux x86_64 | `wst-linux-x86_64` (standalone binary) | `wst_<ver>_amd64.AppImage` + `wst_<ver>_amd64.deb` |

ARM64 Linux is skipped for now — no paid GitHub runners available, and QEMU cross-compilation is too fragile. Can be added later.

### Updated `dmg` job (macOS)

Add a step to upload the standalone CLI binary alongside the existing DMG:

```yaml
- name: Upload standalone CLI
  uses: actions/upload-artifact@v4
  with:
    name: macos-cli
    path: dist/wst

- name: Upload DMG
  uses: actions/upload-artifact@v4
  with:
    name: macos-dmg
    path: ${{ steps.dmg.outputs.path }}
```

### New `windows-installer` job (runs-on: `windows-latest`)

Tauri on Windows produces an `.msi` (WiX) and a `.exe` (NSIS) installer. We attach the `.exe`. The existing Chocolatey job is kept as-is — it remains a separate channel.

```yaml
windows-installer:
  needs: test
  runs-on: windows-latest
  steps:
    - uses: actions/checkout@v4
      with:
        ref: ${{ inputs.version && format('v{0}', inputs.version) || github.ref }}

    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"

    - uses: actions/setup-node@v4
      with:
        node-version: "20"

    - uses: dtolnay/rust-toolchain@stable

    - name: Build standalone wst CLI binary
      shell: pwsh
      run: |
        python -m venv .venv
        .venv\Scripts\pip install -e . pyinstaller
        .venv\Scripts\pyinstaller --onefile --name wst --collect-all wst pyinstaller_entry.py
        $triple = rustc -vV | Select-String "^host:" | ForEach-Object { $_.Line.Split(" ")[1] }
        New-Item -ItemType Directory -Force app\src-tauri\binaries
        Copy-Item dist\wst.exe "app\src-tauri\binaries\wst-$triple.exe"

    - name: Build Tauri app
      run: cd app && npm ci && npx tauri build
      shell: pwsh
      env:
        TAURI_SIGNING_PRIVATE_KEY: ""

    - name: Locate .exe installer
      id: exe
      shell: pwsh
      run: |
        $exe = Get-ChildItem app\src-tauri\target\release\bundle\nsis\*.exe | Select-Object -First 1
        echo "path=$($exe.FullName)" >> $env:GITHUB_OUTPUT

    - uses: actions/upload-artifact@v4
      with:
        name: windows-cli
        path: dist/wst.exe

    - uses: actions/upload-artifact@v4
      with:
        name: windows-exe
        path: ${{ steps.exe.outputs.path }}
```

### New `linux-x86_64` job (runs-on: `ubuntu-22.04`)

Tauri on Linux produces `.deb` and `.AppImage`. We attach **both** — `.AppImage` for distro-agnostic use, `.deb` for native Ubuntu/Debian package management.

```yaml
linux-x86_64:
  needs: test
  runs-on: ubuntu-22.04
  steps:
    - uses: actions/checkout@v4
      with:
        ref: ${{ inputs.version && format('v{0}', inputs.version) || github.ref }}

    - name: Install system dependencies
      run: |
        sudo apt-get update
        sudo apt-get install -y libwebkit2gtk-4.1-dev libappindicator3-dev \
          librsvg2-dev patchelf libssl-dev

    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"

    - uses: actions/setup-node@v4
      with:
        node-version: "20"

    - uses: dtolnay/rust-toolchain@stable

    - name: Build standalone wst CLI binary
      run: |
        python -m venv .venv
        .venv/bin/pip install -e . pyinstaller
        .venv/bin/pyinstaller --onefile --name wst --collect-all wst pyinstaller_entry.py
        mkdir -p app/src-tauri/binaries
        TRIPLE=$(rustc -vV | grep '^host:' | cut -d' ' -f2)
        cp dist/wst "app/src-tauri/binaries/wst-$TRIPLE"
        chmod +x "app/src-tauri/binaries/wst-$TRIPLE"

    - name: Build Tauri app
      run: cd app && npm ci && npx tauri build
      env:
        TAURI_SIGNING_PRIVATE_KEY: ""

    - name: Locate .AppImage and .deb
      id: linux-artifacts
      run: |
        IMG=$(ls app/src-tauri/target/release/bundle/appimage/*.AppImage | head -1)
        DEB=$(ls app/src-tauri/target/release/bundle/deb/*.deb | head -1)
        echo "appimage=$IMG" >> "$GITHUB_OUTPUT"
        echo "deb=$DEB" >> "$GITHUB_OUTPUT"

    - uses: actions/upload-artifact@v4
      with:
        name: linux-cli
        path: dist/wst

    - uses: actions/upload-artifact@v4
      with:
        name: linux-x86_64-appimage
        path: ${{ steps.linux-artifacts.outputs.appimage }}

    - uses: actions/upload-artifact@v4
      with:
        name: linux-x86_64-deb
        path: ${{ steps.linux-artifacts.outputs.deb }}
```

### Updated `github-release` job

```yaml
github-release:
  needs: [publish, dmg, windows-installer, linux-x86_64]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - uses: actions/download-artifact@v4
      with:
        path: release-artifacts

    - name: Flatten artifacts
      run: find release-artifacts -type f | xargs -I{} mv {} release-artifacts/

    - uses: softprops/action-gh-release@v2
      with:
        tag_name: ${{ github.ref_name }}
        generate_release_notes: true
        files: |
          release-artifacts/*.dmg
          release-artifacts/*.exe
          release-artifacts/*.AppImage
          release-artifacts/*.deb
          release-artifacts/wst
          release-artifacts/wst.exe
          release-artifacts/wst-macos
```

---

## Decisions from review

| Question | Decision |
|----------|----------|
| ARM64 Linux | Skip for now — no paid runners available |
| Linux artifacts | Ship both `.AppImage` and `.deb` |
| Windows Chocolatey vs direct download | Keep both — Chocolatey job unchanged, `windows-installer` adds direct `.exe` to the release |
| Per-platform artifacts | Each platform ships **both** a standalone CLI binary and the GUI installer |

---

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| Electron instead of Tauri | Much larger bundle size; we're already on Tauri |
| Only ship PyPI + Chocolatey (no Tauri binaries) | Linux users get no GUI app; Windows users have no direct download |
| Cross-compile all targets from macOS | PyInstaller cannot cross-compile; Tauri cross-compilation is experimental |
| Ship only `.AppImage` for Linux | `.deb` requested for users who prefer native package management |

---

## Implementation Plan

- [ ] Update `dmg` job to also upload standalone `wst` CLI binary
- [ ] Add `windows-installer` job to `release.yml` (CLI + NSIS .exe)
- [ ] Add `linux-x86_64` job to `release.yml` (CLI + .AppImage + .deb)
- [ ] Update `github-release` job to download and attach all artifacts
- [ ] Test on a pre-release tag (`v0.x.y-rc1`) before merging
- [ ] Verify `.AppImage` and `.deb` work on Ubuntu 22.04 and 24.04
- [ ] Verify `.exe` installs cleanly on Windows 11
- [ ] Verify standalone CLI binaries run without the GUI installed
