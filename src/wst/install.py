"""Install optional wst extras (OCR, topics) including system dependencies."""

from __future__ import annotations

import importlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

EXTRAS: dict[str, dict] = {
    "ocr": {
        "package": "wst-library[ocr]",
        "check_modules": ["ocrmypdf"],
        "description": "OCR support for scanned PDFs (ocrmypdf)",
        "system_deps": ["tesseract", "ghostscript"],
    },
    "topics": {
        "package": "wst-library[topics]",
        "check_modules": ["sentence_transformers", "sklearn"],
        "description": "Topic modeling for document clustering",
        "system_deps": [],
    },
}

_SYSTEM_DEP_BREW = {
    "tesseract": ["tesseract", "tesseract-lang"],
    "ghostscript": ["ghostscript"],
}

_SYSTEM_DEP_APT = {
    "tesseract": ["tesseract-ocr"],
    "ghostscript": ["ghostscript"],
}

_SYSTEM_DEP_DNF = {
    "tesseract": ["tesseract"],
    "ghostscript": ["ghostscript"],
}

_SYSTEM_DEP_WHICH = {
    "tesseract": ["tesseract"],
    "ghostscript": ["gs", "gswin64c", "gswin32c"],
}


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _sidecar_venv() -> Path:
    return Path.home() / ".wst" / "extras"


def _find_python() -> str:
    """Return path to a usable Python interpreter."""
    if _is_frozen():
        # Look for embedded Python bundled alongside the app
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates = [
                Path(meipass) / "python-embed" / "python",
                Path(meipass) / "python-embed" / "python.exe",
                Path(meipass).parent / "python-embed" / "python",
                Path(meipass).parent / "python-embed" / "python.exe",
            ]
            for c in candidates:
                if c.exists():
                    return str(c)
        raise RuntimeError(
            "No embedded Python found. Please reinstall wst or install extras manually."
        )
    return sys.executable


def _pip_target() -> list[str]:
    """Return pip install target args for the appropriate environment."""
    if _is_frozen():
        venv = _sidecar_venv()
        venv.mkdir(parents=True, exist_ok=True)
        python = _find_python()
        # Create venv if it doesn't exist yet
        if not (venv / "pyvenv.cfg").exists():
            subprocess.run([python, "-m", "venv", str(venv)], check=True)
        # Use venv's pip
        pip = venv / ("Scripts" if platform.system() == "Windows" else "bin") / "pip"
        return [str(pip)]
    return [sys.executable, "-m", "pip"]


def inject_sidecar_path() -> None:
    """Add the side-car extras venv to sys.path at startup (frozen mode only)."""
    if not _is_frozen():
        return
    venv = _sidecar_venv()
    if not venv.exists():
        return
    py_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        venv / "lib" / py_version / "site-packages",
        venv / "Lib" / "site-packages",
    ]
    for site in candidates:
        if site.exists() and str(site) not in sys.path:
            sys.path.insert(0, str(site))


def is_module_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def extra_status() -> dict[str, bool]:
    """Return {extra_name: is_installed} for all known extras."""
    return {
        name: all(is_module_available(m) for m in info["check_modules"])
        for name, info in EXTRAS.items()
    }


def _check_sys_dep(dep: str) -> bool:
    return any(shutil.which(cmd) for cmd in _SYSTEM_DEP_WHICH[dep])


def _install_sys_dep_macos(dep: str) -> bool:
    """Returns True if installed successfully."""
    if shutil.which("brew"):
        pkgs = _SYSTEM_DEP_BREW[dep]
        result = subprocess.run(["brew", "install", *pkgs])
        return result.returncode == 0
    return False


def _install_sys_dep_linux(dep: str) -> bool:
    if shutil.which("apt-get"):
        pkgs = _SYSTEM_DEP_APT[dep]
        result = subprocess.run(["sudo", "apt-get", "install", "-y", *pkgs])
        return result.returncode == 0
    if shutil.which("dnf"):
        pkgs = _SYSTEM_DEP_DNF[dep]
        result = subprocess.run(["sudo", "dnf", "install", "-y", *pkgs])
        return result.returncode == 0
    return False


_MANUAL_INSTRUCTIONS: dict[str, dict[str, str]] = {
    "tesseract": {
        "Darwin": "  brew install tesseract tesseract-lang",
        "Linux": "  sudo apt-get install tesseract-ocr   # or: sudo dnf install tesseract",
        "Windows": "  Download from https://github.com/UB-Mannheim/tesseract/wiki",
    },
    "ghostscript": {
        "Darwin": "  brew install ghostscript",
        "Linux": "  sudo apt-get install ghostscript   # or: sudo dnf install ghostscript",
        "Windows": "  Download from https://www.ghostscript.com/releases/gsdnld.html",
    },
}


def install_system_dep(dep: str) -> tuple[bool, str]:
    """Try to install a system dependency. Returns (success, message)."""
    if _check_sys_dep(dep):
        return True, f"{dep} already installed"

    system = platform.system()
    success = False
    if system == "Darwin":
        success = _install_sys_dep_macos(dep)
    elif system == "Linux":
        success = _install_sys_dep_linux(dep)

    if success:
        return True, f"{dep} installed"

    instructions = _MANUAL_INSTRUCTIONS.get(dep, {}).get(system, f"Install {dep} manually.")
    return False, f"{dep} not found. Install it manually:\n{instructions}"


def install_extra(name: str, *, upgrade: bool = False) -> None:
    """Install a named extra. Raises on failure."""
    if name not in EXTRAS:
        raise ValueError(f"Unknown extra: {name!r}. Valid choices: {list(EXTRAS)}")

    info = EXTRAS[name]

    # Install system deps first
    for dep in info["system_deps"]:
        ok, msg = install_system_dep(dep)
        import click

        if ok:
            click.echo(f"  {msg}")
        else:
            click.echo(f"  Warning: {msg}", err=True)

    # Install Python package
    pip_cmd = _pip_target()
    cmd = [*pip_cmd, "install", info["package"]]
    if upgrade:
        cmd.append("--upgrade")

    import click

    click.echo(f"Installing {info['package']}...")
    subprocess.run(cmd, check=True)
    click.echo(f"Done. '{name}' extra installed.")


def list_extras(as_json: bool = False) -> None:
    """Print install status for all extras."""
    import click

    status = extra_status()
    if as_json:
        click.echo(json.dumps({k: {"installed": v, **EXTRAS[k]} for k, v in status.items()}))
        return

    for name, installed in status.items():
        icon = "✓" if installed else "✗"
        desc = EXTRAS[name]["description"]
        hint = "" if installed else f"   → wst install {name}"
        click.echo(f"  {icon}  {name:<10} {desc}{hint}")
