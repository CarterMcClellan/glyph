"""Pure-Python protocol shared by Blender, Codex, and remote planners."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from typing import Any, Dict, Iterable, List, Optional


OPERATION_TYPES = (
    "scale",
    "translate",
    "rotate",
    "inflate",
    "smooth",
    "set_color",
)


@dataclass
class EditOperation:
    type: str
    target: str = "selection"
    amount: Optional[float] = None
    vector: Optional[List[float]] = None
    color: Optional[List[float]] = None
    iterations: Optional[int] = None

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "EditOperation":
        unknown = set(value) - {
            "type", "target", "amount", "vector", "color", "iterations"
        }
        if unknown:
            raise ValueError(f"Unknown operation fields: {sorted(unknown)}")
        operation = cls(**value)
        operation.validate()
        return operation

    def validate(self) -> None:
        if self.type not in OPERATION_TYPES:
            raise ValueError(f"Unsupported operation type: {self.type!r}")
        if self.target != "selection":
            raise ValueError("Only the current selection may be edited in Phase 1")
        if self.amount is not None and not math.isfinite(float(self.amount)):
            raise ValueError("Operation amount must be finite")
        if self.vector is not None:
            if len(self.vector) != 3 or not all(math.isfinite(float(v)) for v in self.vector):
                raise ValueError("Operation vector must contain three finite numbers")
        if self.color is not None:
            if len(self.color) not in (3, 4):
                raise ValueError("Color must be RGB or RGBA")
            if not all(math.isfinite(float(v)) and 0.0 <= float(v) <= 1.0 for v in self.color):
                raise ValueError("Color channels must be between 0 and 1")
        if self.iterations is not None and not 1 <= int(self.iterations) <= 20:
            raise ValueError("Iterations must be between 1 and 20")
        if self.type == "scale":
            values = self.vector if self.vector is not None else [self.amount]
            if any(value is None or float(value) <= 0 for value in values):
                raise ValueError("Scale requires a positive amount or vector")
        elif self.type in {"translate", "rotate"} and self.vector is None:
            raise ValueError(f"{self.type} requires a vector")
        elif self.type == "inflate" and self.amount is None:
            raise ValueError("inflate requires an amount")
        elif self.type == "smooth":
            if self.amount is not None and not 0.0 <= float(self.amount) <= 1.0:
                raise ValueError("smooth amount must be between 0 and 1")
        elif self.type == "set_color" and self.color is None:
            raise ValueError("set_color requires a color")


@dataclass
class EditPlan:
    summary: str
    operations: List[EditOperation] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    validation: List[str] = field(
        default_factory=lambda: ["finite_geometry", "protected_geometry"]
    )

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "EditPlan":
        unknown = set(value) - {"summary", "operations", "assumptions", "validation"}
        if unknown:
            raise ValueError(f"Unknown plan fields: {sorted(unknown)}")
        plan = cls(
            summary=str(value.get("summary", "")),
            operations=[EditOperation.from_dict(item) for item in value.get("operations", [])],
            assumptions=[str(item) for item in value.get("assumptions", [])],
            validation=[str(item) for item in value.get("validation", [])],
        )
        plan.validate()
        return plan

    @classmethod
    def from_json(cls, value: str) -> "EditPlan":
        return cls.from_dict(json.loads(value))

    def validate(self) -> None:
        if not self.summary.strip():
            raise ValueError("The edit plan needs a summary")
        if not self.operations:
            raise ValueError("The edit plan contains no operations")
        if len(self.operations) > 12:
            raise ValueError("An edit plan may contain at most 12 operations")
        for operation in self.operations:
            operation.validate()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def edit_plan_schema() -> Dict[str, Any]:
    """Strict schema accepted by both Codex CLI and the Responses API."""
    nullable_number = {"type": ["number", "null"]}
    nullable_vector = {
        "anyOf": [
            {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
            },
            {"type": "null"},
        ]
    }
    nullable_color = {
        "anyOf": [
            {
                "type": "array",
                "items": {"type": "number", "minimum": 0, "maximum": 1},
                "minItems": 3,
                "maxItems": 4,
            },
            {"type": "null"},
        ]
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "operations", "assumptions", "validation"],
        "properties": {
            "summary": {"type": "string", "minLength": 1},
            "operations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "type", "target", "amount", "vector", "color", "iterations"
                    ],
                    "properties": {
                        "type": {"type": "string", "enum": list(OPERATION_TYPES)},
                        "target": {"type": "string", "enum": ["selection"]},
                        "amount": nullable_number,
                        "vector": nullable_vector,
                        "color": nullable_color,
                        "iterations": {"type": ["integer", "null"], "minimum": 1, "maximum": 20},
                    },
                },
            },
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "validation": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["finite_geometry", "protected_geometry", "nonzero_faces"],
                },
            },
        },
    }


def compact_context(context: Dict[str, Any], max_indices: int = 256) -> Dict[str, Any]:
    """Keep prompts bounded while retaining exact indices in the Blender transaction."""
    result = json.loads(json.dumps(context))
    for obj in result.get("objects", []):
        selection = obj.get("selection", {})
        for key in ("vertices", "edges", "faces"):
            values: Iterable[int] = selection.get(key, [])
            values = list(values)
            if len(values) > max_indices:
                selection[key] = values[:max_indices]
                selection[f"{key}_truncated"] = len(values) - max_indices
    return result
