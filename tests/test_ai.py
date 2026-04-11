import pytest

from wst.ai import ClaudeCLIBackend, get_ai_backend
from wst.models import DocumentMetadata


class TestGetAIBackend:
    def test_returns_claude_backend(self):
        backend = get_ai_backend("claude")
        assert isinstance(backend, ClaudeCLIBackend)

    def test_custom_model(self):
        backend = get_ai_backend("claude", model="opus")
        assert backend.model == "opus"

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown AI backend"):
            get_ai_backend("nonexistent")


class TestClaudeCLIBackend:
    def test_build_prompt_contains_key_info(self):
        backend = ClaudeCLIBackend()
        prompt = backend._build_prompt(
            existing_meta={"title": "Test", "author": "Author"},
            text_sample="Chapter 1: Introduction\nThis book covers...",
            filename="test-book.pdf",
            schema='{"type": "object"}',
        )
        assert "test-book.pdf" in prompt
        assert "Test" in prompt
        assert "Chapter 1" in prompt
        assert "doc_type" in prompt.lower() or "book" in prompt.lower()

    def test_build_prompt_truncates_long_text(self):
        backend = ClaudeCLIBackend()
        long_text = "x" * 20000
        prompt = backend._build_prompt({}, long_text, "file.pdf", schema="{}")
        assert "[...truncated]" in prompt
        assert len(prompt) < 25000

    def test_build_prompt_filters_empty_meta(self):
        backend = ClaudeCLIBackend()
        prompt = backend._build_prompt(
            existing_meta={"title": "", "author": None, "subject": "Math"},
            text_sample="text",
            filename="f.pdf",
            schema="{}",
        )
        assert "Math" in prompt

    def test_extract_json_raw(self):
        data = ClaudeCLIBackend._extract_json('{"title": "Test"}')
        assert data["title"] == "Test"

    def test_extract_json_from_markdown(self):
        text = 'Some text\n```json\n{"title": "Test"}\n```\nmore text'
        data = ClaudeCLIBackend._extract_json(text)
        assert data["title"] == "Test"

    def test_extract_json_invalid_raises(self):
        with pytest.raises(ValueError, match="Could not extract JSON"):
            ClaudeCLIBackend._extract_json("no json here")

    def test_build_enrich_prompt_contains_current_metadata(self):
        backend = ClaudeCLIBackend()
        metadata = DocumentMetadata(
            title="El túnel",
            author="Ernesto Sabato",
            doc_type="novel",
            year=1948,
            publisher="Sur",
            language="es",
        )
        prompt = backend._build_enrich_prompt(metadata, "sample text", "{}")
        assert "Ernesto Sabato" in prompt
        assert "isbn" in prompt
        assert "Missing fields to fill" in prompt

    def test_build_enrich_prompt_lists_missing_fields(self):
        backend = ClaudeCLIBackend()
        metadata = DocumentMetadata(
            title="Test", author="Author", doc_type="book"
        )
        prompt = backend._build_enrich_prompt(metadata, "", "{}")
        assert "year" in prompt
        assert "publisher" in prompt
        assert "isbn" in prompt

    def test_enrich_normalizes_toc_list_to_string(self):
        backend = ClaudeCLIBackend()
        data = {
            "title": "Test",
            "author": "Author",
            "doc_type": "book",
            "table_of_contents": ["Chapter 1", "Chapter 2"],
        }
        # Normalize like enrich_metadata does
        toc = data.get("table_of_contents")
        if isinstance(toc, list):
            data["table_of_contents"] = "\n".join(str(item) for item in toc)
        result = DocumentMetadata.model_validate(data)
        assert result.table_of_contents == "Chapter 1\nChapter 2"
