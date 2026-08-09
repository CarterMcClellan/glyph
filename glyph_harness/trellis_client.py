"""HTTP boundary for a remote TRELLIS model service."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from urllib import error, parse, request


class TrellisClient:
    def __init__(self, endpoint: str, api_token: str = ""):
        self.endpoint = endpoint.rstrip("/")
        self.api_token = api_token.strip()

    def submit(self, instruction: str, selection_context: dict, references: list[str]) -> dict:
        if not self.endpoint:
            raise ValueError("Configure a TRELLIS endpoint first")
        payload = {
            "version": 1,
            "instruction": instruction,
            "selection_context": selection_context,
            "reference_images": references,
            "requested_outputs": ["replacement.glb", "provenance.json", "validation.json"],
        }
        return self._request("POST", "/jobs", payload)

    def status(self, job_id: str) -> dict:
        return self._request("GET", f"/jobs/{parse.quote(job_id)}")

    def meshify(self, locked_source: dict) -> dict:
        if not self.endpoint:
            raise ValueError("Configure a TRELLIS endpoint first")
        image_path = Path(locked_source["path"])
        if not image_path.is_file():
            raise RuntimeError("The locked source image is missing")
        payload = {
            "version": 1,
            "operation": "image_to_3d",
            "source": {
                "filename": image_path.name,
                "mime_type": mimetypes.guess_type(image_path.name)[0] or "image/png",
                "base64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
                "sha256": locked_source["sha256"],
                "prompt": locked_source.get("prompt", ""),
                "locked_at": locked_source.get("locked_at"),
            },
            "requested_outputs": ["mesh.glb", "provenance.json", "validation.json"],
        }
        return self._request("POST", "/jobs", payload)

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        req = request.Request(
            self.endpoint + path,
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"TRELLIS returned HTTP {exc.code}: {detail[-800:]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Could not reach TRELLIS at {self.endpoint}: {exc.reason}") from exc
