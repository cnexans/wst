"""Tests for wst install command and install module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from wst.cli import cli
from wst.install import EXTRAS, extra_status, is_module_available

# ---------------------------------------------------------------------------
# extra_status / is_module_available
# ---------------------------------------------------------------------------


def test_is_module_available_stdlib():
    assert is_module_available("os") is True


def test_is_module_available_missing():
    assert is_module_available("_nonexistent_module_xyz") is False


def test_extra_status_topics_installed():
    status = extra_status()
    assert "ocr" in status
    assert "topics" in status
    assert isinstance(status["ocr"], bool)
    assert isinstance(status["topics"], bool)


# ---------------------------------------------------------------------------
# CLI: wst install --list
# ---------------------------------------------------------------------------


def test_install_list_human():
    runner = CliRunner()
    result = runner.invoke(cli, ["install", "--list"])
    assert result.exit_code == 0
    assert "ocr" in result.output
    assert "topics" in result.output


def test_install_list_json():
    runner = CliRunner()
    result = runner.invoke(cli, ["install", "--list", "--json"])
    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    assert set(data.keys()) == set(EXTRAS.keys())
    for v in data.values():
        assert "installed" in v
        assert "description" in v


def test_install_no_args_shows_list():
    runner = CliRunner()
    result = runner.invoke(cli, ["install"])
    assert result.exit_code == 0
    assert "ocr" in result.output


# ---------------------------------------------------------------------------
# CLI: wst install <extra>
# ---------------------------------------------------------------------------


def test_install_unknown_extra():
    runner = CliRunner()
    result = runner.invoke(cli, ["install", "unknown_extra"])
    assert result.exit_code != 0
    assert "unknown_extra" in result.output.lower() or "unknown_extra" in result.output


@patch("wst.install.install_extra")
def test_install_ocr_calls_install_extra(mock_install):
    runner = CliRunner()
    result = runner.invoke(cli, ["install", "ocr"])
    assert result.exit_code == 0
    mock_install.assert_called_once_with("ocr", upgrade=False)


@patch("wst.install.install_extra")
def test_install_upgrade_flag(mock_install):
    runner = CliRunner()
    result = runner.invoke(cli, ["install", "ocr", "--upgrade"])
    assert result.exit_code == 0
    mock_install.assert_called_once_with("ocr", upgrade=True)


# ---------------------------------------------------------------------------
# inject_sidecar_path — no-op when not frozen
# ---------------------------------------------------------------------------


def test_inject_sidecar_path_noop_when_not_frozen():
    from wst.install import inject_sidecar_path

    original_path = sys.path.copy()
    inject_sidecar_path()
    assert sys.path == original_path


# ---------------------------------------------------------------------------
# install_extra — mocked subprocess
# ---------------------------------------------------------------------------


@patch("subprocess.run")
@patch("wst.install._check_sys_dep", return_value=True)
def test_install_extra_runs_pip(mock_sys_dep, mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    from wst.install import install_extra

    install_extra("topics")
    # Should call pip install
    calls = [str(c) for c in mock_run.call_args_list]
    assert any("topics" in c or "wst-library" in c for c in calls)


@patch("subprocess.run")
@patch("wst.install._check_sys_dep", return_value=False)
@patch("wst.install._install_sys_dep_macos", return_value=False)
@patch("wst.install._install_sys_dep_linux", return_value=False)
def test_install_extra_warns_on_missing_sys_dep(mock_linux, mock_mac, mock_check, mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    runner = CliRunner()
    result = runner.invoke(cli, ["install", "ocr"])
    # Should still proceed (warning only), not error
    assert result.exit_code == 0
