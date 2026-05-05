# RFC 0007: Multiplatform Releases

**Issue**: #21  
**Status**: Draft — awaiting approval  
**Branch**: `rfc/21-soporte-multiplataforma`

---

## Problem

Release artifacts currently cover only macOS (.dmg via the `dmg` job). The Chocolatey job publishes to the Chocolatey registry but does not attach a Windows installer to the GitHub release. Linux users have no binary artifact at all — they must install from PyPI and run the CLI only, or build Tauri locally.

The goal is for every tagged release to include installable artifacts for all three platforms directly on the GitHub release page.

---

## Proposed Solution

Add two new build jobs to `.github/workflows/release.yml` — one for Windows, one for Linux — mirroring the existing `dmg` job structure. Each job:

1. Checks out the tag.
2. Builds a standalone `wst` CLI binary via PyInstaller (must run on the target OS — no cross-compilation).
3. Copies the binary into `app/src-tauri/binaries/` with the Rust target triple suffix.
4. Runs `npx tauri build` to produce the platform installer.
5. Uploads the artifact.

The `github-release` job then downloads all artifacts and attaches them to the release.

### New jobs

#### `windows-installer` (runs-on: `windows-latest`)

Tauri on Windows produces an `.msi` (WiX) and a `.exe` (NSIS) installer. We attach the `.exe`.

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
        name: windows-exe
        path: ${{ steps.exe.outputs.path }}
```

#### `linux-x86_64` (runs-on: `ubuntu-22.04`)

Tauri on Linux produces `.deb` and `.AppImage`. We attach the `.AppImage` (runs without installation on any distro).

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

    - name: Locate .AppImage
      id: appimage
      run: |
        IMG=$(ls app/src-tauri/target/release/bundle/appimage/*.AppImage | head -1)
        echo "path=$IMG" >> "$GITHUB_OUTPUT"

    - uses: actions/upload-artifact@v4
      with:
        name: linux-x86_64-appimage
        path: ${{ steps.appimage.outputs.path }}
```

#### Linux ARM64

GitHub-hosted runners do not offer ARM Linux. Two viable options:

| Option | Tradeoff |
|--------|----------|
| `runs-on: ubuntu-22.04-arm` (GitHub larger runner, paid) | Simplest — same job structure as x86_64, but requires enabling larger runners on the org |
| QEMU cross-compilation via `docker/setup-qemu-action` + Tauri cross-compile | Free, but slower (~3×) and more complex toolchain setup |

**Recommendation**: start with the paid ARM runner if the repo is on a plan that includes it; fall back to QEMU otherwise. This RFC proposes the ARM runner path (`runs-on: ubuntu-22.04-arm`) and marks it `continue-on-error: true` until confirmed to work, same as the current Chocolatey job.

### Updated `github-release` job

The existing job generates release notes but does not attach binaries. Replace it with:

```yaml
github-release:
  needs: [publish, windows-installer, linux-x86_64]
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
```

The `.dmg` is already produced by the `dmg` job (uploaded as `macos-dmg`), so no changes to that job are needed.

---

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| Electron instead of Tauri | Much larger bundle size; we're already on Tauri |
| Only ship PyPI + Chocolatey (no Tauri binaries) | Linux users get no GUI app; Windows users have no direct download |
| Cross-compile all targets from macOS | PyInstaller cannot cross-compile; Tauri cross-compilation is experimental |
| Ship `.deb` instead of `.AppImage` for Linux | `.AppImage` is distro-agnostic; `.deb` only targets Debian/Ubuntu natively |

---

## Open Questions

> **Q1**: Does the repo's GitHub plan include `ubuntu-22.04-arm` larger runners? If not, should we use QEMU or simply skip ARM for now and add it later?

> **Q2**: Should we also attach the `.deb` artifact for users who prefer native package manager installation on Ubuntu?

> **Q3**: The Chocolatey job already runs on Windows but only pushes to the registry. Should the new `windows-installer` job replace it entirely, or should we keep both (registry push + direct .exe on the release)?

---

## Implementation Plan

- [ ] Add `windows-installer` job to `release.yml`
- [ ] Add `linux-x86_64` job to `release.yml`
- [ ] Add `linux-arm64` job to `release.yml` (`continue-on-error: true`)
- [ ] Update `github-release` job to download and attach all artifacts
- [ ] Test on a pre-release tag (`v0.x.y-rc1`) before merging
- [ ] Verify `.AppImage` runs on Ubuntu 22.04 and 24.04
- [ ] Verify `.exe` installs cleanly on Windows 11
