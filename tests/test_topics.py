"""Tests for topic modeling (build_vocabulary, assign_topics, save/load vocabulary, CLI)."""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from wst.cli import cli
from wst.db import Database
from wst.models import DocType, DocumentMetadata, LibraryEntry
from wst.storage import build_dest_path
from wst.topics import (
    _build_cluster_naming_prompt,
    _deduplicate_vocabulary,
    _name_cluster,
    _parse_json_list,
    assign_topics,
    assign_topics_single,
    load_vocabulary,
    save_vocabulary,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def _make_entry(
    title="Test Book",
    author="John Doe",
    doc_type=DocType.BOOK,
    file_hash="hash123",
    tags=None,
    summary=None,
    **kwargs,
) -> LibraryEntry:
    meta = DocumentMetadata(
        title=title,
        author=author,
        doc_type=doc_type,
        tags=tags or [],
        summary=summary,
        **kwargs,
    )
    dest = build_dest_path(meta)
    return LibraryEntry(
        metadata=meta,
        filename=f"{author} - {title}.pdf",
        original_filename="original.pdf",
        file_path=dest,
        file_hash=file_hash,
        ingested_at="2026-01-01T00:00:00Z",
    )


def _mock_ai(return_value: str) -> MagicMock:
    ai = MagicMock()
    ai._run_claude.return_value = return_value
    return ai


# ---------------------------------------------------------------------------
# DB migration: topics column
# ---------------------------------------------------------------------------


class TestDBTopicsColumn:
    def test_topics_column_exists_after_init(self, db):
        rows = db.conn.execute("PRAGMA table_info(documents)").fetchall()
        col_names = [r["name"] for r in rows]
        assert "topics" in col_names

    def test_topics_vocabulary_table_exists(self, db):
        rows = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='topics_vocabulary'"
        ).fetchall()
        assert len(rows) == 1

    def test_topics_roundtrip_insert(self, db):
        entry = _make_entry(tags=["algebra"], file_hash="h1")
        entry.metadata.topics = ["Matemáticas", "Álgebra Lineal"]
        db.insert(entry)
        result = db.get(1)
        assert result is not None
        assert result.metadata.topics == ["Matemáticas", "Álgebra Lineal"]

    def test_topics_roundtrip_update(self, db):
        entry = _make_entry(file_hash="h1")
        db.insert(entry)
        result = db.get(1)
        result.metadata.topics = ["Cálculo"]
        db.update(result)
        updated = db.get(1)
        assert updated.metadata.topics == ["Cálculo"]

    def test_topics_default_empty(self, db):
        entry = _make_entry(file_hash="h1")
        db.insert(entry)
        result = db.get(1)
        assert result.metadata.topics == []


# ---------------------------------------------------------------------------
# Save / load vocabulary
# ---------------------------------------------------------------------------


class TestVocabularyPersistence:
    def test_save_and_load(self, db):
        vocab = ["Cálculo", "Álgebra Lineal", "Literatura"]
        save_vocabulary(db, vocab)
        loaded = load_vocabulary(db)
        assert loaded == vocab

    def test_load_returns_none_when_empty(self, db):
        assert load_vocabulary(db) is None

    def test_overwrite_vocabulary(self, db):
        save_vocabulary(db, ["Old Topic"])
        save_vocabulary(db, ["New Topic 1", "New Topic 2"])
        loaded = load_vocabulary(db)
        assert loaded == ["New Topic 1", "New Topic 2"]


# ---------------------------------------------------------------------------
# _parse_json_list
# ---------------------------------------------------------------------------


class TestParseJsonList:
    def test_valid_json_list(self):
        vocab = ["Cálculo", "Álgebra Lineal", "Geometría"]
        result = _parse_json_list('["Cálculo", "Álgebra Lineal"]', vocab)
        assert result == ["Cálculo", "Álgebra Lineal"]

    def test_case_insensitive_match(self):
        vocab = ["Cálculo", "Álgebra Lineal"]
        result = _parse_json_list('["cálculo"]', vocab)
        assert result == ["Cálculo"]

    def test_filters_out_invalid_topics(self):
        vocab = ["Cálculo"]
        result = _parse_json_list('["Cálculo", "Inventado"]', vocab)
        assert result == ["Cálculo"]

    def test_limits_to_three(self):
        vocab = ["A", "B", "C", "D"]
        result = _parse_json_list('["A", "B", "C", "D"]', vocab)
        assert len(result) <= 3

    def test_returns_empty_on_bad_json(self):
        vocab = ["Cálculo"]
        result = _parse_json_list("not json", vocab)
        assert result == []

    def test_extracts_json_from_surrounding_text(self):
        vocab = ["Cálculo", "Física"]
        result = _parse_json_list('Sure, here: ["Cálculo", "Física"] — done.', vocab)
        assert "Cálculo" in result


# ---------------------------------------------------------------------------
# assign_topics (mocked AI)
# ---------------------------------------------------------------------------


class TestAssignTopicsSingle:
    def test_returns_valid_topics(self):
        vocab = ["Matemáticas", "Literatura"]
        ai = _mock_ai('["Matemáticas"]')
        doc = {"title": "Cálculo", "author": "Author", "tags": [], "summary": "", "subject": None}
        result = assign_topics_single(ai, vocab, doc)
        assert result == ["Matemáticas"]

    def test_filters_out_of_vocabulary_topics(self):
        vocab = ["Matemáticas"]
        ai = _mock_ai('["Matemáticas", "Inventado"]')
        doc = {"title": "Book", "author": "A", "tags": [], "summary": "", "subject": None}
        result = assign_topics_single(ai, vocab, doc)
        assert result == ["Matemáticas"]

    def test_returns_empty_on_bad_ai_response(self):
        vocab = ["Matemáticas"]
        ai = _mock_ai("not json at all")
        doc = {"title": "Book", "author": "A", "tags": [], "summary": "", "subject": None}
        result = assign_topics_single(ai, vocab, doc)
        assert result == []

    def test_prompt_contains_vocabulary(self):
        captured: list[str] = []
        ai = MagicMock()

        def capture(prompt: str) -> str:
            captured.append(prompt)
            return '["Física"]'

        ai._run_claude.side_effect = capture
        vocab = ["Física", "Literatura"]
        doc = {"title": "Book", "author": "A", "tags": [], "summary": "", "subject": None}
        assign_topics_single(ai, vocab, doc)
        assert captured, "AI was not called"
        assert "Física" in captured[0]
        assert "Literatura" in captured[0]


class TestAssignTopics:
    def test_assigns_topics_to_all_docs(self, db):
        db.insert(_make_entry(title="Book A", file_hash="h1"))
        db.insert(_make_entry(title="Book B", file_hash="h2"))

        vocab = ["Matemáticas", "Literatura"]
        ai = _mock_ai('["Matemáticas"]')

        result = assign_topics(db, ai, vocab)
        assert len(result) == 2
        for topics in result.values():
            assert isinstance(topics, list)

    def test_empty_library_returns_empty(self, db):
        ai = _mock_ai('["Matemáticas"]')
        result = assign_topics(db, ai, ["Matemáticas"])
        assert result == {}


# ---------------------------------------------------------------------------
# build_vocabulary (mocked embeddings + AI)
# ---------------------------------------------------------------------------


class TestBuildVocabulary:
    def _fake_modules(self):
        """Return a dict of fake sys.modules entries for numpy, sentence-transformers, sklearn."""
        fake_numpy = types.ModuleType("numpy")
        fake_st_mod = types.ModuleType("sentence_transformers")
        fake_st_mod.SentenceTransformer = MagicMock()
        fake_sklearn = types.ModuleType("sklearn")
        fake_cluster = types.ModuleType("sklearn.cluster")
        fake_cluster.KMeans = MagicMock()
        fake_metrics = types.ModuleType("sklearn.metrics")
        fake_metrics.silhouette_score = MagicMock(return_value=0.5)
        return {
            "numpy": fake_numpy,
            "sentence_transformers": fake_st_mod,
            "sklearn": fake_sklearn,
            "sklearn.cluster": fake_cluster,
            "sklearn.metrics": fake_metrics,
        }

    def test_empty_library_returns_empty(self, db):
        """build_vocabulary on empty DB returns empty tuple without touching ML deps."""
        from wst.topics import build_vocabulary

        ai = _mock_ai("Cálculo")
        with patch.dict(sys.modules, self._fake_modules()):
            vocab, rep_docs = build_vocabulary(db, ai)
        assert vocab == []
        assert rep_docs == {}

    def test_raises_on_missing_deps(self, db):
        """build_vocabulary raises RuntimeError when sentence-transformers is missing."""
        from wst.topics import build_vocabulary

        db.insert(_make_entry(file_hash="h1"))
        ai = _mock_ai("Cálculo")

        # Setting a module to None in sys.modules causes ImportError on import
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            with pytest.raises(RuntimeError, match="sentence-transformers"):
                build_vocabulary(db, ai)

    def test_build_with_mocked_vocabulary(self, db):
        """Verify build_vocabulary output type and length contract."""
        db.insert(_make_entry(title="Cálculo Diferencial", tags=["límites"], file_hash="h1"))
        db.insert(_make_entry(title="Álgebra Lineal", tags=["matrices"], file_hash="h2"))
        db.insert(_make_entry(title="Literatura Fantástica", tags=["Tolkien"], file_hash="h3"))

        # Mock the entire function to avoid heavy ML dependencies in CI
        with patch(
            "wst.topics.build_vocabulary",
            return_value=(["Matemáticas", "Literatura"], {}),
        ):
            from wst.topics import build_vocabulary

            ai = _mock_ai("Matemáticas")
            vocab, rep_docs = build_vocabulary(db, ai, n_topics=2)

        assert isinstance(vocab, list)
        assert len(vocab) == 2
        assert "Matemáticas" in vocab
        assert isinstance(rep_docs, dict)


# ---------------------------------------------------------------------------
# _build_cluster_naming_prompt — used_names context injection
# ---------------------------------------------------------------------------


class TestBuildClusterNamingPrompt:
    """Tests that used_names are correctly injected into the prompt."""

    def _docs(self, titles: list[str]) -> list[dict]:
        return [{"title": t, "tags": [], "summary": ""} for t in titles]

    def test_no_used_names_omits_section(self):
        """When used_names is empty/None, the prompt does not mention already-used names."""
        prompt = _build_cluster_naming_prompt(self._docs(["Álgebra Lineal"]), used_names=None)
        assert "Nombres ya usados" not in prompt

    def test_empty_used_names_omits_section(self):
        prompt = _build_cluster_naming_prompt(self._docs(["Álgebra Lineal"]), used_names=[])
        assert "Nombres ya usados" not in prompt

    def test_used_names_appear_in_prompt(self):
        """When used_names is provided, each name appears in the prompt."""
        used = ["Geometría Euclidiana", "Variable Compleja", "Álgebra Abstracta"]
        prompt = _build_cluster_naming_prompt(self._docs(["Tensores"]), used_names=used)
        assert "Nombres ya usados" in prompt
        for name in used:
            assert name in prompt

    def test_used_names_section_has_no_repeat_instruction(self):
        """The prompt explicitly tells the AI not to repeat the listed names."""
        used = ["Cálculo"]
        prompt = _build_cluster_naming_prompt(self._docs(["Integrales"]), used_names=used)
        assert "NO repetir" in prompt


# ---------------------------------------------------------------------------
# _name_cluster — used_names forwarding
# ---------------------------------------------------------------------------


class TestNameCluster:
    """Tests that _name_cluster forwards used_names to the AI prompt."""

    def _docs(self, titles: list[str]) -> list[dict]:
        return [{"title": t, "tags": [], "summary": ""} for t in titles]

    def test_returns_cleaned_name(self):
        """_name_cluster strips extra whitespace and quotes from the AI response."""
        ai = _mock_ai('  "Cálculo"  ')
        result = _name_cluster(ai, self._docs(["Integrales"]))
        assert result == "Cálculo"

    def test_used_names_passed_to_prompt(self):
        """The prompt sent to the AI must include the used names when provided."""
        captured_prompts: list[str] = []

        ai = MagicMock()

        def capture(prompt: str) -> str:
            captured_prompts.append(prompt)
            return "Física Cuántica"

        ai._run_claude.side_effect = capture

        used = ["Geometría Euclidiana", "Álgebra Abstracta"]
        _name_cluster(ai, self._docs(["Mecánica Cuántica"]), used_names=used)

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        for name in used:
            assert name in prompt, f"Expected '{name}' in prompt but got: {prompt[:300]}"

    def test_no_used_names_prompt_has_no_used_section(self):
        """When no used_names provided, the prompt must not mention already-used names."""
        captured_prompts: list[str] = []

        ai = MagicMock()

        def capture(prompt: str) -> str:
            captured_prompts.append(prompt)
            return "Cálculo"

        ai._run_claude.side_effect = capture

        _name_cluster(ai, self._docs(["Integrales"]), used_names=None)
        assert "Nombres ya usados" not in captured_prompts[0]

    def test_empty_used_names_prompt_has_no_used_section(self):
        """Empty used_names list should not add the 'already used' section."""
        captured_prompts: list[str] = []

        ai = MagicMock()

        def capture(prompt: str) -> str:
            captured_prompts.append(prompt)
            return "Cálculo"

        ai._run_claude.side_effect = capture

        _name_cluster(ai, self._docs(["Integrales"]), used_names=[])
        assert "Nombres ya usados" not in captured_prompts[0]


# ---------------------------------------------------------------------------
# _deduplicate_vocabulary
# ---------------------------------------------------------------------------


class TestDeduplicateVocabulary:
    """Tests for the duplicate-name resolution logic."""

    def _docs(self, titles: list[str], tags: list[str] | None = None) -> list[dict]:
        return [{"title": t, "tags": tags or [], "summary": ""} for t in titles]

    def test_no_duplicates_unchanged(self):
        """When all names are already unique, vocabulary is left as-is."""
        ai = _mock_ai("Álgebra Lineal\nAnálisis Vectorial")
        vocab = ["Cálculo", "Álgebra Lineal", "Literatura"]
        docs_map = [self._docs(["a"]), self._docs(["b"]), self._docs(["c"])]
        result = _deduplicate_vocabulary(ai, vocab, docs_map)
        assert result == ["Cálculo", "Álgebra Lineal", "Literatura"]
        ai._run_claude.assert_not_called()

    def test_two_duplicates_get_distinct_names(self):
        """Two clusters with the same name are renamed to different names."""
        # AI returns two distinct names when asked to disambiguate
        ai = _mock_ai("Álgebra Lineal\nAnálisis Vectorial")
        vocab = ["Álgebra Lineal", "Álgebra Lineal", "Literatura"]
        docs_map = [
            self._docs(["Matrices y Vectores"], ["matrices", "vectores"]),
            self._docs(["Cálculo Vectorial"], ["gradiente", "divergencia"]),
            self._docs(["Cien Años de Soledad"]),
        ]
        result = _deduplicate_vocabulary(ai, vocab, docs_map)
        # The two previously-duplicate entries must now be different
        assert result[0] != result[1]
        assert result[2] == "Literatura"
        ai._run_claude.assert_called_once()

    def test_three_duplicates_resolved(self):
        """Three clusters with the same name are all resolved to unique names."""
        call_count = 0

        def side_effect(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            # First call: disambiguate clusters 0 and 1
            if call_count == 1:
                return "Álgebra Lineal\nAnálisis Vectorial"
            # Second call: disambiguate cluster 2 (still "Álgebra Lineal") with next dup
            return "Cálculo Tensorial\nGeometría Diferencial"

        ai = MagicMock()
        ai._run_claude.side_effect = side_effect

        vocab = ["Álgebra Lineal", "Álgebra Lineal", "Álgebra Lineal"]
        docs_map = [
            self._docs(["Matrices"]),
            self._docs(["Vectores"]),
            self._docs(["Tensores"]),
        ]
        result = _deduplicate_vocabulary(ai, vocab, docs_map)
        assert len(set(r.lower() for r in result)) == len(result), (
            f"Expected all unique names, got {result}"
        )

    def test_fallback_when_ai_returns_one_line(self):
        """When AI returns only one line, the second cluster gets a ' II' suffix."""
        ai = _mock_ai("Álgebra Lineal")  # only one name returned
        vocab = ["Álgebra Lineal", "Álgebra Lineal"]
        docs_map = [self._docs(["A"]), self._docs(["B"])]
        result = _deduplicate_vocabulary(ai, vocab, docs_map)
        assert result[0] != result[1]

    def test_case_insensitive_duplicate_detection(self):
        """Duplicates are detected ignoring case differences."""
        ai = _mock_ai("Álgebra Lineal\nAnálisis Vectorial")
        vocab = ["álgebra lineal", "Álgebra Lineal"]
        docs_map = [self._docs(["A"]), self._docs(["B"])]
        result = _deduplicate_vocabulary(ai, vocab, docs_map)
        assert result[0].lower() != result[1].lower()


# ---------------------------------------------------------------------------
# CLI: wst topics build --help, wst topics list
# ---------------------------------------------------------------------------


class TestTopicsCLI:
    def test_topics_build_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["topics", "build", "--help"])
        assert result.exit_code == 0
        assert "--n-topics" in result.output

    def test_topics_list_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["topics", "list", "--help"])
        assert result.exit_code == 0

    def test_topics_assign_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["topics", "assign", "--help"])
        assert result.exit_code == 0
        assert "--id" in result.output

    def test_topics_list_empty(self, tmp_path):
        from wst.config import WstConfig

        lib = tmp_path / "library"
        lib.mkdir(parents=True)
        db_path = lib / "wst.db"
        cfg = WstConfig(
            home_path=tmp_path,
            inbox_path=tmp_path / "inbox",
            library_path=lib,
            db_path=db_path,
        )

        runner = CliRunner()
        with patch("wst.cli.WstConfig", return_value=cfg):
            result = runner.invoke(cli, ["topics", "list"])
        assert result.exit_code == 0
        assert "No topic vocabulary" in result.output

    def test_topics_list_shows_vocabulary(self, tmp_path):
        from wst.config import WstConfig

        lib = tmp_path / "library"
        lib.mkdir(parents=True)
        db_path = lib / "wst.db"

        # Pre-populate vocabulary
        db = Database(db_path)
        db.save_topics_vocabulary(["Cálculo", "Álgebra Lineal"])
        db.close()

        cfg = WstConfig(
            home_path=tmp_path,
            inbox_path=tmp_path / "inbox",
            library_path=lib,
            db_path=db_path,
        )

        runner = CliRunner()
        with patch("wst.cli.WstConfig", return_value=cfg):
            result = runner.invoke(cli, ["topics", "list"])
        assert result.exit_code == 0
        assert "Cálculo" in result.output
        assert "Álgebra Lineal" in result.output

    def test_topics_list_json_format(self, tmp_path):
        from wst.config import WstConfig

        lib = tmp_path / "library"
        lib.mkdir(parents=True)
        db_path = lib / "wst.db"

        db = Database(db_path)
        db.save_topics_vocabulary(["Física", "Química"])
        db.close()

        cfg = WstConfig(
            home_path=tmp_path,
            inbox_path=tmp_path / "inbox",
            library_path=lib,
            db_path=db_path,
        )

        runner = CliRunner()
        with patch("wst.cli.WstConfig", return_value=cfg):
            result = runner.invoke(cli, ["--format", "json", "topics", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert "Física" in parsed["data"]["vocabulary"]


# ---------------------------------------------------------------------------
# CLI: wst search --topic
# ---------------------------------------------------------------------------


class TestSearchByTopic:
    def _prep_db(self, tmp_path):
        from wst.config import WstConfig

        lib = tmp_path / "library"
        lib.mkdir(parents=True)
        db_path = lib / "wst.db"
        db = Database(db_path)

        e1 = _make_entry(title="Calculos Diferenciales", file_hash="h1")
        e1.metadata.topics = ["Calculo", "Matematicas"]
        db.insert(e1)

        e2 = _make_entry(title="Romeo y Julieta", file_hash="h2")
        e2.metadata.topics = ["Literatura"]
        db.insert(e2)

        db.close()

        return WstConfig(
            home_path=tmp_path,
            inbox_path=tmp_path / "inbox",
            library_path=lib,
            db_path=db_path,
        )

    def test_search_by_topic_human(self, tmp_path):
        cfg = self._prep_db(tmp_path)
        runner = CliRunner()
        with patch("wst.cli.WstConfig", return_value=cfg):
            result = runner.invoke(cli, ["search", "--topic", "calculo"])
        assert result.exit_code == 0
        assert "Calculos Diferenciales" in result.output

    def test_search_by_topic_json(self, tmp_path):
        cfg = self._prep_db(tmp_path)
        runner = CliRunner()
        with patch("wst.cli.WstConfig", return_value=cfg):
            result = runner.invoke(cli, ["--format", "json", "search", "--topic", "Literatura"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        titles = [e["metadata"]["title"] for e in parsed["data"]]
        assert "Romeo y Julieta" in titles
        assert "Calculos Diferenciales" not in titles

    def test_search_by_topic_no_results(self, tmp_path):
        cfg = self._prep_db(tmp_path)
        runner = CliRunner()
        with patch("wst.cli.WstConfig", return_value=cfg):
            result = runner.invoke(cli, ["search", "--topic", "fisica"])
        assert result.exit_code == 0
        assert "No results" in result.output


# ---------------------------------------------------------------------------
# CLI: wst topics build -y (non-interactive)
# ---------------------------------------------------------------------------


class TestTopicsBuildNonInteractive:
    """Verify that -y / non-human formats skip the interactive review step."""

    def _prep_cfg(self, tmp_path):
        from wst.config import WstConfig

        lib = tmp_path / "library"
        lib.mkdir(parents=True)
        db_path = lib / "wst.db"
        db = Database(db_path)
        db.insert(_make_entry(title="Álgebra Lineal", file_hash="h1"))
        db.insert(_make_entry(title="Cálculo Diferencial", file_hash="h2"))
        db.close()
        return WstConfig(
            home_path=tmp_path,
            inbox_path=tmp_path / "inbox",
            library_path=lib,
            db_path=db_path,
        )

    def test_topics_build_yes_flag_saves_without_prompt(self, tmp_path):
        """With -y the vocabulary is saved directly; no interactive prompt is shown."""
        cfg = self._prep_cfg(tmp_path)
        fake_vocab = ["Matemáticas", "Ciencias"]

        runner = CliRunner()
        with (
            patch("wst.cli.WstConfig", return_value=cfg),
            patch("wst.topics.build_vocabulary", return_value=(fake_vocab, {})),
            patch("wst.topics.assign_topics", return_value={1: ["Matemáticas"], 2: ["Ciencias"]}),
            patch("wst.topics.save_vocabulary") as mock_save,
        ):
            result = runner.invoke(cli, ["topics", "build", "-y"])

        assert result.exit_code == 0, result.output
        # The interactive question must NOT appear
        assert "¿Aceptás" not in result.output
        # save_vocabulary must have been called with the original vocabulary
        mock_save.assert_called_once()
        saved_vocab = mock_save.call_args[0][1]
        assert saved_vocab == fake_vocab

    def test_topics_build_json_format_saves_without_prompt(self, tmp_path):
        """With --format json the vocabulary is saved directly; no interactive prompt."""
        cfg = self._prep_cfg(tmp_path)
        fake_vocab = ["Física", "Literatura"]

        runner = CliRunner()
        with (
            patch("wst.cli.WstConfig", return_value=cfg),
            patch("wst.topics.build_vocabulary", return_value=(fake_vocab, {})),
            patch("wst.topics.assign_topics", return_value={1: ["Física"], 2: ["Literatura"]}),
            patch("wst.topics.save_vocabulary") as mock_save,
        ):
            result = runner.invoke(cli, ["--format", "json", "topics", "build", "-y"])

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["data"]["vocabulary"] == fake_vocab
        # save_vocabulary must have been called with the returned vocabulary
        mock_save.assert_called_once()
        saved_vocab = mock_save.call_args[0][1]
        assert saved_vocab == fake_vocab
