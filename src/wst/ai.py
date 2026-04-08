import json
import re
import subprocess
from abc import ABC, abstractmethod

from wst.models import DocumentMetadata


class AIBackend(ABC):
    @abstractmethod
    def generate_metadata(
        self, existing_meta: dict, text_sample: str, filename: str
    ) -> DocumentMetadata: ...


class ClaudeCLIBackend(AIBackend):
    def __init__(self, model: str = "sonnet"):
        self.model = model

    def generate_metadata(
        self, existing_meta: dict, text_sample: str, filename: str
    ) -> DocumentMetadata:
        schema = json.dumps(DocumentMetadata.model_json_schema())
        prompt = self._build_prompt(existing_meta, text_sample, filename, schema)

        result = subprocess.run(
            [
                "claude",
                "-p",
                "--model",
                self.model,
                "--output-format",
                "json",
                "--allowedTools",
                "WebSearch",
                "WebFetch",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {result.stderr}")

        wrapper = json.loads(result.stdout)
        raw = wrapper.get("result", "")

        return DocumentMetadata.model_validate(self._extract_json(raw))

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON object from a response that may contain markdown fences."""
        # Try direct parse first
        text = text.strip()
        if text.startswith("{"):
            return json.loads(text)
        # Extract from ```json ... ``` block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"Could not extract JSON from AI response: {text[:200]}")

    def _build_prompt(
        self, existing_meta: dict, text_sample: str, filename: str, schema: str
    ) -> str:
        meta_str = json.dumps({k: v for k, v in existing_meta.items() if v}, indent=2)
        max_chars = 8000
        if len(text_sample) > max_chars:
            text_sample = text_sample[:max_chars] + "\n[...truncated]"

        return f"""Analyze this PDF and return ONLY a JSON object matching the schema below.
No explanation, no markdown, just the raw JSON.

## JSON Schema
{schema}

## Filename
{filename}

## Existing PDF metadata
{meta_str}

## Text from first pages
{text_sample}

## Field guidelines
- doc_type: one of book, novel, textbook, paper, class-notes, exercises,
  guide-theory, guide-practice
- language: ISO 639-1 code (e.g. "en", "es")
- tags: relevant topics and keywords
- summary: 2-3 sentence description
- table_of_contents: chapter titles if visible, otherwise null
- subject: broad knowledge area (e.g. "Mathematics", "Computer Science")
- Use null for fields that cannot be determined
- Always provide title and author — infer from content if needed
- IMPORTANT: If year, publisher, or ISBN are missing from the PDF text,
  use web search to find the correct publication year, publisher, and ISBN.
  Search for the book title and author to find this information."""


def get_ai_backend(name: str, model: str = "sonnet") -> AIBackend:
    backends = {
        "claude": ClaudeCLIBackend,
    }
    cls = backends.get(name)
    if cls is None:
        raise ValueError(f"Unknown AI backend: {name}. Available: {', '.join(backends)}")
    return cls(model=model)
