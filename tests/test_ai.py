import pytest

from wst.ai import (
    ClaudeCLIBackend,
    CodexCLIBackend,
    _build_enrich_prompt,
    _build_ingest_prompt,
    _extract_json,
    _normalize_enrich_result,
    get_ai_backend,
)
from wst.models import DocumentMetadata


class TestGetAIBackend:
    def test_returns_claude_backend(self):
        backend = get_ai_backend("claude")
        assert isinstance(backend, ClaudeCLIBackend)

    def test_returns_codex_backend(self):
        backend = get_ai_backend("codex")
        assert isinstance(backend, CodexCLIBackend)

    def test_claude_default_model(self):
        backend = get_ai_backend("claude")
        assert backend.model == "sonnet"

    def test_codex_default_model(self):
        backend = get_ai_backend("codex")
        assert backend.model == "gpt-5.4"

    def test_custom_model(self):
        backend = get_ai_backend("claude", model="opus")
        assert backend.model == "opus"

    def test_codex_custom_model(self):
        backend = get_ai_backend("codex", model="gpt-5.4-mini")
        assert backend.model == "gpt-5.4-mini"

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown AI backend"):
            get_ai_backend("nonexistent")


class TestPromptBuilders:
    def test_ingest_prompt_contains_key_info(self):
        prompt = _build_ingest_prompt(
            existing_meta={"title": "Test", "author": "Author"},
            text_sample="Chapter 1: Introduction\nThis book covers...",
            filename="test-book.pdf",
            schema='{"type": "object"}',
        )
        assert "test-book.pdf" in prompt
        assert "Test" in prompt
        assert "Chapter 1" in prompt

    def test_ingest_prompt_truncates_long_text(self):
        long_text = "x" * 20000
        prompt = _build_ingest_prompt({}, long_text, "file.pdf", schema="{}")
        assert "[...truncated]" in prompt
        assert len(prompt) < 25000

    def test_ingest_prompt_filters_empty_meta(self):
        prompt = _build_ingest_prompt(
            existing_meta={"title": "", "author": None, "subject": "Math"},
            text_sample="text",
            filename="f.pdf",
            schema="{}",
        )
        assert "Math" in prompt

    def test_enrich_prompt_contains_current_metadata(self):
        metadata = DocumentMetadata(
            title="El tunel",
            author="Ernesto Sabato",
            doc_type="book",
            year=1948,
            publisher="Sur",
            language="es",
        )
        prompt = _build_enrich_prompt(metadata, "sample text", "{}")
        assert "Ernesto Sabato" in prompt
        assert "isbn" in prompt
        assert "Missing fields to fill" in prompt

    def test_enrich_prompt_lists_missing_fields(self):
        metadata = DocumentMetadata(title="Test", author="Author", doc_type="book")
        prompt = _build_enrich_prompt(metadata, "", "{}")
        assert "year" in prompt
        assert "publisher" in prompt
        assert "isbn" in prompt


class TestExtractJson:
    def test_raw_json(self):
        data = _extract_json('{"title": "Test"}')
        assert data["title"] == "Test"

    def test_from_markdown(self):
        text = 'Some text\n```json\n{"title": "Test"}\n```\nmore text'
        data = _extract_json(text)
        assert data["title"] == "Test"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Could not extract JSON"):
            _extract_json("no json here")


class TestNormalizeEnrichResult:
    def test_normalizes_toc_list_to_string(self):
        data = {
            "title": "Test",
            "author": "Author",
            "doc_type": "book",
            "table_of_contents": ["Chapter 1", "Chapter 2"],
        }
        result = _normalize_enrich_result(data)
        assert result["table_of_contents"] == "Chapter 1\nChapter 2"

    def test_keeps_toc_string_unchanged(self):
        data = {"table_of_contents": "Chapter 1\nChapter 2"}
        result = _normalize_enrich_result(data)
        assert result["table_of_contents"] == "Chapter 1\nChapter 2"

    def test_keeps_toc_none(self):
        data = {"table_of_contents": None}
        result = _normalize_enrich_result(data)
        assert result["table_of_contents"] is None
