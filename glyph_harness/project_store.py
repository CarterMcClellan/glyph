"""Persistent, forward-only project state for the Glyph desktop workflow."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import threading
import uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
    STAGES = {"IMAGINE", "MESH", "EDIT"}

    def __init__(self, workspace: Path):
        self.root = Path(workspace) / "project"
        self.assets = self.root / "assets"
        self.sources = self.assets / "sources"
        self.meshes = self.assets / "meshes"
        self.forks = self.root / "forks"
        for folder in (self.sources, self.meshes, self.forks):
            folder.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "project.json"
        self._lock = threading.RLock()
        if not self.path.is_file():
            self._write(self._new_state())

    def _new_state(self, parent_project_id: str | None = None) -> dict:
        return {
            "version": 1,
            "project_id": uuid.uuid4().hex,
            "parent_project_id": parent_project_id,
            "name": "Untitled Object",
            "stage": "IMAGINE",
            "created_at": _now(),
            "updated_at": _now(),
            "source": {"versions": [], "active_id": None, "locked": None},
            "mesh": {"job": None, "approved": None},
        }

    def _read(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("Glyph project state is unreadable") from exc
        if value.get("stage") not in self.STAGES:
            raise RuntimeError("Glyph project state has an invalid stage")
        return value

    def _write(self, state: dict) -> dict:
        state["updated_at"] = _now()
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return deepcopy(state)

    def state(self) -> dict:
        with self._lock:
            return deepcopy(self._read())

    def rename(self, name: str) -> dict:
        with self._lock:
            state = self._read()
            cleaned = str(name).strip()
            if cleaned:
                state["name"] = cleaned[:120]
            return self._write(state)

    def _require_imagine(self, state: dict):
        if state["stage"] != "IMAGINE" or state["source"].get("locked"):
            raise RuntimeError("This source is locked. Fork the project to create a different source.")

    def _add_source(self, image_bytes: bytes, suffix: str, prompt: str, origin: str, model: str | None = None) -> dict:
        with self._lock:
            state = self._read()
            self._require_imagine(state)
            number = len(state["source"]["versions"]) + 1
            source_id = f"source-v{number}"
            safe_suffix = suffix.lower() if suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else ".png"
            image_path = self.sources / f"{source_id}{safe_suffix}"
            image_path.write_bytes(image_bytes)
            record = {
                "id": source_id,
                "path": str(image_path),
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
                "prompt": prompt.strip(),
                "origin": origin,
                "model": model,
                "created_at": _now(),
            }
            state["source"]["versions"].append(record)
            state["source"]["active_id"] = source_id
            return self._write(state)

    def import_source(self, source: str, prompt: str = "") -> dict:
        path = Path(source).expanduser().resolve()
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} or not path.is_file():
            raise ValueError("Choose an existing PNG, JPEG, or WebP image")
        return self._add_source(path.read_bytes(), path.suffix, prompt, "import")

    def add_generated_source(self, image_bytes: bytes, prompt: str, model: str) -> dict:
        return self._add_source(image_bytes, ".png", prompt, "generated", model)

    def set_active_source(self, source_id: str) -> dict:
        with self._lock:
            state = self._read()
            self._require_imagine(state)
            if not any(item["id"] == source_id for item in state["source"]["versions"]):
                raise ValueError("Source version not found")
            state["source"]["active_id"] = source_id
            return self._write(state)

    def lock_source(self, confirmed: bool) -> dict:
        if not confirmed:
            raise ValueError("Permanent source lock must be explicitly confirmed")
        with self._lock:
            state = self._read()
            self._require_imagine(state)
            source_id = state["source"].get("active_id")
            active = next((item for item in state["source"]["versions"] if item["id"] == source_id), None)
            if not active:
                raise ValueError("Generate or import a source image before locking")
            locked = deepcopy(active)
            locked["locked_at"] = _now()
            state["source"]["locked"] = locked
            state["stage"] = "MESH"
            return self._write(state)

    def record_mesh_job(self, job: dict) -> dict:
        with self._lock:
            state = self._read()
            if state["stage"] != "MESH" or not state["source"].get("locked"):
                raise RuntimeError("Lock the source before starting TRELLIS")
            state["mesh"]["job"] = {**job, "updated_at": _now()}
            return self._write(state)

    def update_mesh_job(self, job: dict) -> dict:
        return self.record_mesh_job(job)

    def approve_mesh(self, source: str) -> dict:
        path = Path(source).expanduser().resolve()
        if path.suffix.lower() not in {".glb", ".gltf"} or not path.is_file():
            raise ValueError("Choose an existing GLB or glTF mesh")
        with self._lock:
            state = self._read()
            if state["stage"] != "MESH" or not state["source"].get("locked"):
                raise RuntimeError("A locked source is required before mesh approval")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            destination = self.meshes / f"mesh-{digest[:12]}{path.suffix.lower()}"
            if path != destination:
                shutil.copy2(path, destination)
            state["mesh"]["approved"] = {
                "path": str(destination),
                "sha256": digest,
                "approved_at": _now(),
            }
            state["stage"] = "EDIT"
            return self._write(state)

    def fork_project(self) -> dict:
        with self._lock:
            previous = self._read()
            if previous["stage"] == "IMAGINE":
                raise RuntimeError("Forking is available after the source has been locked")
            archive = self.forks / f"{previous['project_id']}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            archive.write_text(json.dumps(previous, indent=2), encoding="utf-8")
            state = self._new_state(previous["project_id"])
            state["name"] = f"{previous['name']} fork"
            locked = previous["source"].get("locked")
            if locked and Path(locked["path"]).is_file():
                image = Path(locked["path"])
                number = 1
                destination = self.sources / f"fork-{state['project_id'][:8]}-source-v{number}{image.suffix}"
                shutil.copy2(image, destination)
                record = {
                    **{key: value for key, value in locked.items() if key != "locked_at"},
                    "id": "source-v1",
                    "path": str(destination),
                    "origin": "fork",
                    "created_at": _now(),
                }
                state["source"]["versions"] = [record]
                state["source"]["active_id"] = record["id"]
            return self._write(state)
