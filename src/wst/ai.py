import json
import re
import subprocess
import tempfile
from abc import ABC, abstractmethod

from wst.models import DocumentMetadata


class AIBackend(ABC):
    @abstractmethod
    def generate_metadata(
        self, existing_meta: dict, text_sample: str, filename: str
    ) -> DocumentMetadata: ...

    @abstractmethod
    def enrich_metadata(
        self, metadata: DocumentMetadata, text_sample: str
    ) -> DocumentMetadata: ...


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    raise ValueError(f"Could not extract JSON from AI response: {text[:200]}")


def _normalize_enrich_result(data: dict) -> dict:
    toc = data.get("table_of_contents")
    if isinstance(toc, list):
        data["table_of_contents"] = "\n".join(str(item) for item in toc)
    return data


def _build_ingest_prompt(
    existing_meta: dict, text_sample: str, filename: str, schema: str
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


def _build_enrich_prompt(
    metadata: DocumentMetadata, text_sample: str, schema: str
) -> str:
    current = metadata.model_dump(mode="json")
    current_str = json.dumps(
        {k: v for k, v in current.items() if v is not None}, indent=2
    )
    missing = [k for k, v in current.items() if v is None]

    max_chars = 8000
    if len(text_sample) > max_chars:
        text_sample = text_sample[:max_chars] + "\n[...truncated]"

    return f"""You have metadata for a document that is missing some fields.
Your job is to FILL IN the missing fields using web search. Return the COMPLETE
metadata as a JSON object matching the schema below.

IMPORTANT:
- Keep ALL existing values unchanged — do not modify fields that already have values.
- You MUST use web search to find missing fields. Do NOT guess or return null without searching first.
- For ISBN: search Google Books, Open Library, Amazon, or WorldCat. Try multiple queries:
  - Search by exact title and author
  - Try alternate titles (e.g. translated titles, original language titles)
  - Try different editions (paperback, hardcover, international)
  - Any valid ISBN for any edition of the book is acceptable
- For table_of_contents: search the publisher's page, Google Books preview, or Open Library.
- Search for the book by its title and author to find accurate publication info.
- Only use null if you have searched and truly cannot find the information.

## JSON Schema
{schema}

## Current metadata
{current_str}

## Missing fields to fill
{json.dumps(missing)}

## Text from first pages (for additional context)
{text_sample}

Return ONLY the JSON object, no explanation."""


class ClaudeCLIBackend(AIBackend):
    def __init__(self, model: str = "sonnet"):
        self.model = model

    def generate_metadata(
        self, existing_meta: dict, text_sample: str, filename: str
    ) -> DocumentMetadata:
        schema = json.dumps(DocumentMetadata.model_json_schema())
        prompt = _build_ingest_prompt(existing_meta, text_sample, filename, schema)
        result = self._run_claude(prompt)
        return DocumentMetadata.model_validate(_extract_json(result))

    def enrich_metadata(
        self, metadata: DocumentMetadata, text_sample: str
    ) -> DocumentMetadata:
        schema = json.dumps(DocumentMetadata.model_json_schema())
        prompt = _build_enrich_prompt(metadata, text_sample, schema)
        result = self._run_claude(prompt)
        data = _normalize_enrich_result(_extract_json(result))
        return DocumentMetadata.model_validate(data)

    def _run_claude(self, prompt: str) -> str:
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
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {result.stderr}")

        wrapper = json.loads(result.stdout)
        return wrapper.get("result", "")


class CodexCLIBackend(AIBackend):
    def __init__(self, model: str = "gpt-5.4"):
        self.model = model

    def generate_metadata(
        self, existing_meta: dict, text_sample: str, filename: str
    ) -> DocumentMetadata:
        schema = json.dumps(DocumentMetadata.model_json_schema())
        prompt = _build_ingest_prompt(existing_meta, text_sample, filename, schema)
        result = self._run_codex(prompt)
        return DocumentMetadata.model_validate(_extract_json(result))

    def enrich_metadata(
        self, metadata: DocumentMetadata, text_sample: str
    ) -> DocumentMetadata:
        schema = json.dumps(DocumentMetadata.model_json_schema())
        prompt = _build_enrich_prompt(metadata, text_sample, schema)
        result = self._run_codex(prompt)
        data = _normalize_enrich_result(_extract_json(result))
        return DocumentMetadata.model_validate(data)

    def _run_codex(self, prompt: str) -> str:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as out_file:
            out_path = out_file.name

        result = subprocess.run(
            [
                "codex",
                "exec",
                prompt,
                "--model",
                self.model,
                "-o",
                out_path,
                "--sandbox",
                "read-only",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            stderr = result.stderr or ""
            # Check JSONL output for error messages
            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                    if event.get("type") == "error":
                        stderr = event.get("message", stderr)
                except (json.JSONDecodeError, KeyError):
                    pass
            raise RuntimeError(f"codex CLI failed: {stderr}")

        try:
            from pathlib import Path

            output = Path(out_path).read_text().strip()
            Path(out_path).unlink(missing_ok=True)
        except Exception as e:
            raise RuntimeError(f"could not read codex output: {e}")

        if not output:
            raise RuntimeError("codex returned empty response")

        return output


DEFAULT_MODELS = {
    "claude": "sonnet",
    "codex": "gpt-5.4",
}


def get_ai_backend(name: str, model: str | None = None) -> AIBackend:
    backends = {
        "claude": ClaudeCLIBackend,
        "codex": CodexCLIBackend,
    }
    cls = backends.get(name)
    if cls is None:
        raise ValueError(f"Unknown AI backend: {name}. Available: {', '.join(backends)}")
    resolved_model = model or DEFAULT_MODELS.get(name, "")
    return cls(model=resolved_model)
