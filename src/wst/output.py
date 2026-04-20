from __future__ import annotations

import dataclasses
import json
from enum import Enum
from pathlib import Path
from typing import Any

import click
from pydantic import BaseModel


class WstError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.exit_code = exit_code


def to_payload(obj: Any) -> Any:
    if obj is None:
        return None

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, Path):
        return str(obj)

    if isinstance(obj, Enum):
        return obj.value

    if dataclasses.is_dataclass(obj):
        return {k: to_payload(v) for k, v in dataclasses.asdict(obj).items()}

    if isinstance(obj, BaseModel):
        return {k: to_payload(v) for k, v in obj.model_dump().items()}

    if isinstance(obj, dict):
        return {str(k): to_payload(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [to_payload(v) for v in obj]

    return str(obj)


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": to_payload(data)}


def _err(code: str, message: str, details: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "details": to_payload(details)},
    }


def render_ok(data: Any, *, fmt: str) -> None:
    payload = _ok(data)
    _render_payload(payload, fmt=fmt)


def render_error(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None,
    fmt: str,
) -> None:
    payload = _err(code, message, details)
    _render_payload(payload, fmt=fmt)


def _render_payload(payload: dict[str, Any], *, fmt: str) -> None:
    fmt = fmt.lower()
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if fmt == "yaml":
        try:
            import yaml  # type: ignore
        except Exception as e:  # pragma: no cover
            raise WstError(
                "missing_dependency",
                "YAML output requires PyYAML. Install/update dependencies and retry.",
                details={"import_error": str(e)},
                exit_code=2,
            )
        click.echo(yaml.safe_dump(payload, sort_keys=True, allow_unicode=True))
        return
    if fmt == "md":
        click.echo(_to_markdown(payload))
        return

    raise WstError(
        "usage_error",
        f"Unknown format: {fmt}",
        details={"allowed": ["human", "md", "json", "yaml"]},
        exit_code=2,
    )


def _to_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    ok = payload.get("ok", False)
    lines.append("# wst output")
    lines.append("")
    lines.append(f"- ok: `{ok}`")
    lines.append("")

    if ok:
        lines.append("## data")
        lines.append("")
        lines.extend(_md_value(payload.get("data")))
    else:
        err = payload.get("error", {}) or {}
        lines.append("## error")
        lines.append("")
        lines.append(f"- code: `{err.get('code')}`")
        lines.append(f"- message: {err.get('message')}")
        details = err.get("details")
        if details not in (None, {}, []):
            lines.append("")
            lines.append("### details")
            lines.append("")
            lines.extend(_md_value(details))

    return "\n".join(lines).rstrip() + "\n"


def _md_value(v: Any) -> list[str]:
    if v is None:
        return ["- null"]

    if isinstance(v, (str, int, float, bool)):
        return [f"- `{v}`" if not isinstance(v, str) else f"- {v}"]

    if isinstance(v, list):
        if not v:
            return ["- []"]
        # Try to make a markdown table for list[dict]
        if all(isinstance(x, dict) for x in v):
            return _md_table(v)  # type: ignore[arg-type]
        out: list[str] = []
        for item in v:
            out.append(f"- {json.dumps(item, ensure_ascii=False)}")
        return out

    if isinstance(v, dict):
        if not v:
            return ["- {}"]
        out = []
        for k in sorted(v.keys()):
            out.append(f"- **{k}**: {json.dumps(v[k], ensure_ascii=False)}")
        return out

    return [f"- {json.dumps(v, ensure_ascii=False)}"]


def _md_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- []"]
    # Collect union of keys
    keys: list[str] = sorted({k for r in rows for k in r.keys()})
    header = "| " + " | ".join(keys) + " |"
    sep = "| " + " | ".join(["---"] * len(keys)) + " |"
    lines = [header, sep]
    for r in rows:
        vals = []
        for k in keys:
            val = r.get(k)
            cell = "" if val is None else json.dumps(val, ensure_ascii=False)
            vals.append(cell.replace("\n", " "))
        lines.append("| " + " | ".join(vals) + " |")
    return lines

