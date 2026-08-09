"""Out-of-process Blender bridge used by the standalone Glyph app."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


DEFAULT_BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"


class BlenderClient:
    def __init__(self, project_root: Path, workspace: Path, executable: str | None = None):
        self.project_root = Path(project_root).resolve()
        self.workspace = Path(workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.session_path = self.workspace / "session.blend"
        configured = executable or os.environ.get("GLYPH_BLENDER") or DEFAULT_BLENDER
        found = shutil.which(configured) if os.path.sep not in configured else configured
        self.executable = Path(found) if found else Path(configured)
        self.bridge_script = self.project_root / "scripts" / "blender_bridge.py"

    def available(self) -> bool:
        return self.executable.is_file() and self.bridge_script.is_file()

    def open_project(self, source: str) -> dict:
        path = Path(source).expanduser().resolve()
        if path.suffix.lower() != ".blend" or not path.is_file():
            raise ValueError("Choose an existing .blend file")
        shutil.copy2(path, self.session_path)
        return self.scene()

    def scene(self) -> dict:
        return self.execute("scene")

    def preview(self, object_name: str, face_indices: list[int], plan: dict) -> dict:
        return self.execute(
            "preview",
            {"object_name": object_name, "face_indices": face_indices, "plan": plan},
        )

    def accept(self) -> dict:
        return self.execute("accept")

    def reject(self) -> dict:
        return self.execute("reject")

    def import_mesh(self, source: str) -> dict:
        path = Path(source).expanduser().resolve()
        if path.suffix.lower() not in {".glb", ".gltf"} or not path.is_file():
            raise ValueError("Choose an existing GLB or glTF mesh")
        return self.execute("import_mesh", {"path": str(path)})

    def execute(self, command: str, payload: dict | None = None) -> dict:
        if not self.available():
            raise RuntimeError(f"Blender was not found at {self.executable}")
        with tempfile.TemporaryDirectory(prefix="glyph_bridge_", dir=self.workspace) as folder:
            folder_path = Path(folder)
            payload_path = folder_path / "payload.json"
            output_path = folder_path / "output.json"
            payload_path.write_text(json.dumps(payload or {}), encoding="utf-8")
            command_line = [str(self.executable), "--background"]
            if self.session_path.is_file():
                command_line.append(str(self.session_path))
            command_line.extend(
                [
                    "--python",
                    str(self.bridge_script),
                    "--",
                    "--command",
                    command,
                    "--payload",
                    str(payload_path),
                    "--output",
                    str(output_path),
                    "--session",
                    str(self.session_path),
                ]
            )
            completed = subprocess.run(
                command_line,
                cwd=self.project_root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=180,
                check=False,
            )
            if completed.returncode != 0 or not output_path.is_file():
                detail = completed.stdout.strip()[-4000:]
                raise RuntimeError(f"Blender bridge failed ({command}): {detail}")
            result = json.loads(output_path.read_text(encoding="utf-8"))
            if not result.get("ok"):
                raise RuntimeError(result.get("error", f"Blender command failed: {command}"))
            return result["data"]
