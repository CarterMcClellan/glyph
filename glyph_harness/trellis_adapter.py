"""Single customization point for the future TRELLIS model server.

Replace the placeholder server paths and response field paths here when the hosted
TRELLIS API is finalized. The same public contract is returned to the renderer at
GET /api/trellis/contract, so backend transport and frontend parsing stay aligned.
"""

from __future__ import annotations

import os


# MODEL SERVER PLACEHOLDER ---------------------------------------------------
MODEL_SERVER = {
    "base_url": os.environ.get("GLYPH_TRELLIS_ENDPOINT", ""),
    "create_job_path": "/jobs",
    "status_path": "/jobs/{job_id}",
    "timeout_seconds": 60,
}


# EXPECTED RESPONSE PLACEHOLDER ----------------------------------------------
# Paths use dot notation and are tried from left to right by the frontend.
EXPECTED_RESPONSE = {
    "version": 1,
    "fields": {
        "job_id": ["job_id", "id"],
        "status": ["status", "state"],
        "progress": ["progress", "percent"],
        "message": ["message", "detail", "error.message"],
        "mesh_output": [
            "glb_url",
            "mesh_url",
            "output_url",
            "glb_path",
            "mesh_path",
            "output.glb_url",
            "output.mesh_url",
            "output.glb",
            "output.mesh",
            "result.glb_url",
            "result.mesh_url",
            "result.glb",
            "result.mesh",
        ],
    },
    "statuses": {
        "queued": ["queued", "pending"],
        "running": ["running", "processing", "reconstructing"],
        "complete": ["completed", "succeeded", "success"],
        "failed": ["failed", "error", "cancelled", "canceled"],
    },
    "example": {
        "job_id": "trellis_job_123",
        "status": "running",
        "progress": 0.62,
        "message": "Reconstructing geometry",
        "output": {"mesh_url": "https://model-server.example/output/mesh.glb"},
    },
}


def public_trellis_contract(endpoint_override: str = "") -> dict:
    server = {**MODEL_SERVER, "base_url": endpoint_override or MODEL_SERVER["base_url"]}
    return {"server": server, "response": EXPECTED_RESPONSE}


def value_at_paths(payload: dict, paths: list[str]):
    for path in paths:
        value = payload
        for key in path.split("."):
            if not isinstance(value, dict) or key not in value:
                value = None
                break
            value = value[key]
        if value is not None:
            return value
    return None
