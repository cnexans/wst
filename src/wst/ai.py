import json
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
        schema = DocumentMetadata.model_json_schema()

        prompt = self._build_prompt(existing_meta, text_sample, filename)

        result = subprocess.run(
            [
                "claude",
                "-p",
                "--model",
                self.model,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(schema),
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {result.stderr}")

        data = json.loads(result.stdout)
        return DocumentMetadata.model_validate(data)

    def _build_prompt(self, existing_meta: dict, text_sample: str, filename: str) -> str:
        meta_str = json.dumps({k: v for k, v in existing_meta.items() if v}, indent=2)
        # Truncate text sample to avoid overwhelming the model
        max_chars = 8000
        if len(text_sample) > max_chars:
            text_sample = text_sample[:max_chars] + "\n[...truncated]"

        return f"""Analyze this PDF document and generate complete metadata.

## Filename
{filename}

## Existing PDF metadata
{meta_str}

## Text from first pages
{text_sample}

## Instructions
Based on the filename, existing metadata, and text content,
generate accurate metadata for this document.

For doc_type, choose the most appropriate from:
- book: general non-fiction book
- novel: fiction/literature
- textbook: educational/academic textbook
- paper: scientific/academic paper
- class-notes: class notes or lecture notes
- exercises: problem sets or exercises
- guide-theory: theoretical study guide
- guide-practice: practical study guide

For language, use ISO 639-1 codes (e.g., "en", "es", "fr").
For tags, include relevant topics, keywords, and categories.
For summary, write a brief 2-3 sentence description.
For table_of_contents, include chapter titles if visible in the text, otherwise leave null.
For subject, indicate the broad knowledge area
(e.g., "Mathematics", "Computer Science", "Literature").

If information cannot be determined, use null for optional fields.
Always provide title and author — infer from content if not in metadata."""


def get_ai_backend(name: str, model: str = "sonnet") -> AIBackend:
    backends = {
        "claude": ClaudeCLIBackend,
    }
    cls = backends.get(name)
    if cls is None:
        raise ValueError(f"Unknown AI backend: {name}. Available: {', '.join(backends)}")
    return cls(model=model)
