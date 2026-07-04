"""Generate frontend TypeScript types from the Pydantic domain models.

Single source of truth: the same models FastAPI uses for its OpenAPI schema are
introspected here and emitted as `frontend/src/types/api.ts`. The frontend never
hand-copies backend shapes — regenerate after changing domain/models.py:

    cd backend && python -m scripts.gen_frontend_types

Kept intentionally small (the domain models are flat and simple). If the models
grow complex, swap this for `openapi-typescript` against the live schema.
"""
from __future__ import annotations

import os
import typing
from enum import Enum

from pydantic import BaseModel

from domain.models import (
    ComputedComposition,
    NutrientVector,
    RejectedFormula,
    ResolvedLine,
    ValidatedFormula,
    ValidationReport,
    Violation,
)

# Emit in dependency order so referenced interfaces are declared first.
MODELS: list[type[BaseModel]] = [
    NutrientVector,
    ResolvedLine,
    Violation,
    ValidationReport,
    ComputedComposition,
    ValidatedFormula,
    RejectedFormula,
]
_MODEL_NAMES = {m.__name__ for m in MODELS}

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "frontend", "src", "types", "api.ts")


def _ts_type(annotation) -> str:
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if annotation is type(None):
        return "null"
    if annotation in (int, float):
        return "number"
    if annotation is str:
        return "string"
    if annotation is bool:
        return "boolean"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return " | ".join(f'"{e.value}"' for e in annotation)
    if isinstance(annotation, type) and annotation.__name__ in _MODEL_NAMES:
        return annotation.__name__
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__

    if origin is typing.Literal:
        return " | ".join(f'"{a}"' if isinstance(a, str) else str(a) for a in args)
    if origin in (list, typing.List):
        return f"{_ts_type(args[0])}[]"
    if origin in (dict, typing.Dict):
        return "Record<string, unknown>"
    if origin is typing.Union:
        parts = [_ts_type(a) for a in args]
        return " | ".join(dict.fromkeys(parts))  # dedupe, keep order
    return "unknown"


def _emit_interface(model: type[BaseModel]) -> str:
    lines = [f"export interface {model.__name__} {{"]
    for name, field in model.model_fields.items():
        ts = _ts_type(field.annotation)
        optional = "?" if not field.is_required() else ""
        lines.append(f"  {name}{optional}: {ts};")
    lines.append("}")
    return "\n".join(lines)


_SSE_UNION = """
// ── Server-sent event envelope (matches backend/main.py _stream_agent) ─────────
export interface TokenEvent { type: "token"; content: string; }
export interface FormulaEvent { type: "formula"; formula: ValidatedFormula; response: string; }
export interface RejectionEvent { type: "rejection"; rejection: RejectedFormula; response: string; }
export interface ErrorEvent { type: "error"; message: string; }
export interface DoneEvent { type: "done"; session_id: string; }
export type SSEEvent = TokenEvent | FormulaEvent | RejectionEvent | ErrorEvent | DoneEvent;
"""


def build() -> str:
    header = ("// GENERATED FROM backend/domain/models.py — DO NOT EDIT BY HAND.\n"
              "// Regenerate: cd backend && python -m scripts.gen_frontend_types\n")
    body = "\n\n".join(_emit_interface(m) for m in MODELS)
    return f"{header}\n{body}\n{_SSE_UNION}"


def main() -> int:
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    with open(_OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(build())
    print(f"Wrote {os.path.relpath(_OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
