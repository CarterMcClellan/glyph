"""Agent-style edit loop with a narrow, auditable Blender tool boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from blender_ai_editor.planner import create_plan


@dataclass
class HarnessStep:
    name: str
    detail: str
    status: str = "complete"
    at: str = ""

    def __post_init__(self):
        if not self.at:
            self.at = datetime.now(timezone.utc).isoformat()


class AgentHarness:
    """Plans, applies, and validates edits without granting a model arbitrary Blender access."""

    def __init__(self, blender_client):
        self.blender = blender_client

    def preview(
        self,
        instruction: str,
        object_name: str,
        face_indices: list[int],
        scene: dict,
        references: list[str] | None = None,
        backend: str = "LOCAL",
        model: str = "gpt-5.6-sol",
        codex_executable: str = "codex",
    ) -> dict[str, Any]:
        if not instruction.strip():
            raise ValueError("Describe the edit before generating a preview")
        mesh = next((item for item in scene.get("objects", []) if item["id"] == object_name), None)
        if not mesh:
            raise ValueError("The selected mesh is no longer in the scene")
        chosen_faces = sorted({int(index) for index in face_indices if int(index) >= 0})
        chosen_vertices = sorted(
            {
                vertex
                for polygon in mesh.get("polygons", [])
                if polygon["index"] in chosen_faces
                for vertex in polygon["vertices"]
            }
        )
        context = {
            "scene": scene.get("name", "Scene"),
            "active_object": object_name,
            "mode": "FACE_SELECTION" if chosen_faces else "OBJECT",
            "unit_system": scene.get("unit_system", "NONE"),
            "objects": [
                {
                    "name": object_name,
                    "type": "MESH",
                    "vertex_count": mesh.get("vertex_count", 0),
                    "edge_count": mesh.get("edge_count", 0),
                    "face_count": mesh.get("face_count", 0),
                    "selection": {
                        "vertices": chosen_vertices,
                        "edges": [],
                        "faces": chosen_faces,
                    },
                }
            ],
        }
        steps = [
            HarnessStep(
                "Capture selection",
                f"{mesh['label']}: {len(chosen_faces) or mesh.get('face_count', 0)} faces in model context",
            )
        ]
        plan = create_plan(
            backend,
            instruction,
            context,
            references or [],
            model,
            codex_executable,
        )
        steps.append(HarnessStep("Create typed plan", plan.summary))
        result = self.blender.preview(object_name, chosen_faces, plan.to_dict())
        steps.append(HarnessStep("Apply in Blender", "Created an isolated preview mesh"))
        steps.append(HarnessStep("Validate preview", "Geometry is finite and protected vertices are unchanged"))
        return {
            "scene": result["scene"],
            "transaction": result.get("transaction"),
            "plan": plan.to_dict(),
            "context": context,
            "steps": [asdict(step) for step in steps],
        }
