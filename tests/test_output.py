"""Regression: StrEnum must serialize before YAML (Enum check must precede str)."""

import json

import pytest
from click.testing import CliRunner

from wst.cli import cli
from wst.models import DocType, DocumentMetadata, LibraryEntry
from wst.output import _ok, to_payload


def _sample_entry() -> LibraryEntry:
    return LibraryEntry(
        id=1,
        metadata=DocumentMetadata(title="Sample", author="A", doc_type=DocType.BOOK),
        filename="t.pdf",
        original_filename="t.pdf",
        file_path="books/t.pdf",
        file_hash="abc",
        ingested_at="2020-01-01",
    )


class TestToPayload:
    def test_str_enum_becomes_plain_string(self):
        payload = to_payload([_sample_entry()])
        assert payload[0]["metadata"]["doc_type"] == "book"
        assert type(payload[0]["metadata"]["doc_type"]) is str
        json.dumps(payload)

    def test_ok_payload_json_serializable(self):
        payload = _ok([_sample_entry()])
        json.dumps(payload)

    def test_yaml_round_trip_when_pyyaml_installed(self):
        yaml = pytest.importorskip("yaml")
        payload = _ok([_sample_entry()])
        dumped = yaml.safe_dump(payload, allow_unicode=True)
        roundtrip = yaml.safe_load(dumped)
        assert roundtrip["ok"] is True
        assert roundtrip["data"][0]["metadata"]["doc_type"] == "book"


class TestSearchMachineOutputCli:
    """CLI → render_ok; StrEnum must not leak into structured output."""

    def _prep_db(self, tmp_path):
        from wst.config import WstConfig
        from wst.db import Database

        lib = tmp_path / "library"
        lib.mkdir(parents=True)
        db_path = lib / "wst.db"
        db = Database(db_path)
        db.insert(_sample_entry())
        db.close()

        cfg = WstConfig(
            home_path=tmp_path,
            inbox_path=tmp_path / "inbox",
            library_path=lib,
            db_path=db_path,
        )
        return cfg

    def test_search_json_emits_plain_doc_type(self, monkeypatch, tmp_path):
        monkeypatch.setattr("wst.cli.WstConfig", lambda: self._prep_db(tmp_path))

        runner = CliRunner()
        r = runner.invoke(cli, ["--format", "json", "search", "Sample"])
        assert r.exit_code == 0, r.output
        parsed = json.loads(r.output)
        assert parsed["ok"] is True
        assert parsed["data"][0]["metadata"]["doc_type"] == "book"

    def test_search_yaml_emits_plain_doc_type_when_pyyaml_installed(self, monkeypatch, tmp_path):
        pytest.importorskip("yaml")
        monkeypatch.setattr("wst.cli.WstConfig", lambda: self._prep_db(tmp_path))

        runner = CliRunner()
        r = runner.invoke(cli, ["--format", "yaml", "search", "Sample"])
        assert r.exit_code == 0, r.output
        assert "DocType." not in r.output

        import yaml

        parsed = yaml.safe_load(r.output)
        assert parsed["ok"] is True
        assert parsed["data"][0]["metadata"]["doc_type"] == "book"
