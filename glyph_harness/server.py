"""Local HTTP API for the Glyph desktop shell."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import traceback
from urllib import request
from urllib.parse import urlparse

from .blender_client import BlenderClient
from .harness import AgentHarness
from .project_store import ProjectStore
from .trellis_client import TrellisClient
from blender_ai_editor.planner import codex_auth_status, resolve_codex_executable


class GlyphService:
    def __init__(self, project_root: Path, workspace: Path):
        self.workspace = workspace
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.settings_path = workspace / "settings.json"
        self.settings = self._load_settings()
        self.project = ProjectStore(workspace)
        self.blender = BlenderClient(project_root, workspace)
        self.harness = AgentHarness(self.blender)
        self.last_context: dict = {}

    def _load_settings(self) -> dict:
        defaults = {
            "planner": "CODEX",
            "model": "gpt-5.6-sol",
            "codex_executable": "codex",
            "trellis_endpoint": os.environ.get("GLYPH_TRELLIS_ENDPOINT", ""),
        }
        if self.settings_path.is_file():
            try:
                defaults.update(json.loads(self.settings_path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        # Remove the legacy image-generation credential from memory and future writes.
        defaults.pop("openai_api_key", None)
        defaults["planner"] = "CODEX"
        return defaults

    def public_settings(self) -> dict:
        return dict(self.settings)

    def save_settings(self, updates: dict) -> dict:
        allowed = {"planner", "model", "codex_executable", "trellis_endpoint"}
        self.settings.update({key: value for key, value in updates.items() if key in allowed})
        self.settings_path.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        try:
            self.settings_path.chmod(0o600)
        except OSError:
            pass
        return self.public_settings()

    def chatgpt_auth(self) -> dict:
        return codex_auth_status(self.settings.get("codex_executable", "codex"))

    def sign_in_chatgpt(self) -> dict:
        current = self.chatgpt_auth()
        if current["signed_in"]:
            return current
        binary = resolve_codex_executable(self.settings.get("codex_executable", "codex"))
        try:
            result = subprocess.run(
                [binary, "login"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("ChatGPT sign-in timed out. Try Sign in with ChatGPT again.") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"ChatGPT sign-in failed: {detail[-800:]}")
        status = self.chatgpt_auth()
        if not status["signed_in"]:
            raise RuntimeError("Codex did not report a ChatGPT sign-in after authentication completed.")
        return status

    def scene(self) -> dict:
        return self.blender.scene()

    def preview(self, payload: dict) -> dict:
        result = self.harness.preview(
            payload.get("instruction", ""),
            payload.get("object_name", ""),
            payload.get("face_indices", []),
            payload.get("scene") or self.scene(),
            payload.get("references", []),
            payload.get("backend", self.settings["planner"]),
            payload.get("model", self.settings["model"]),
            self.settings["codex_executable"],
        )
        self.last_context = result["context"]
        return result

    def submit_trellis(self, payload: dict) -> dict:
        context = payload.get("context") or self.last_context
        if not context:
            raise ValueError("Select mesh context before sending a TRELLIS job")
        return TrellisClient(self.settings.get("trellis_endpoint", "")).submit(
            payload.get("instruction", ""), context, payload.get("references", [])
        )

    def start_meshify(self) -> dict:
        state = self.project.state()
        locked = state["source"].get("locked")
        if state["stage"] != "MESH" or not locked:
            raise RuntimeError("Lock the source before starting TRELLIS")
        response = TrellisClient(self.settings.get("trellis_endpoint", "")).meshify(locked)
        job = {
            **response,
            "job_id": response.get("job_id") or response.get("id"),
            "status": response.get("status", "queued"),
        }
        if not job["job_id"]:
            raise RuntimeError("TRELLIS did not return a job id")
        self.project.record_mesh_job(job)
        return job

    def mesh_job_status(self, job_id: str) -> dict:
        job = TrellisClient(self.settings.get("trellis_endpoint", "")).status(job_id)
        job = {**job, "job_id": job.get("job_id") or job.get("id") or job_id}
        self.project.update_mesh_job(job)
        return job

    def approve_mesh(self, source: str) -> dict:
        scene = self.blender.import_mesh(source)
        project = self.project.approve_mesh(source)
        return {"project": project, "scene": scene}

    def approve_mesh_job(self) -> dict:
        state = self.project.state()
        job = state["mesh"].get("job") or {}
        candidate = self._mesh_output(job)
        if not candidate:
            raise RuntimeError("TRELLIS has not returned a GLB output. Choose the completed file manually.")
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"}:
            destination = self.project.meshes / f"trellis-{job.get('job_id', 'output')}.glb"
            req = request.Request(candidate, headers={"Accept": "model/gltf-binary, application/octet-stream"})
            with request.urlopen(req, timeout=300) as response:
                length = int(response.headers.get("Content-Length", "0") or 0)
                if length > 512 * 1024 * 1024:
                    raise RuntimeError("TRELLIS mesh exceeds Glyph's 512 MB import limit")
                data = response.read(512 * 1024 * 1024 + 1)
            if len(data) > 512 * 1024 * 1024:
                raise RuntimeError("TRELLIS mesh exceeds Glyph's 512 MB import limit")
            destination.write_bytes(data)
            candidate = str(destination)
        return self.approve_mesh(candidate)

    @staticmethod
    def _mesh_output(job: dict) -> str | None:
        for key in ("glb_url", "mesh_url", "output_url", "glb_path", "mesh_path"):
            if isinstance(job.get(key), str):
                return job[key]
        for container_key in ("output", "outputs", "result"):
            container = job.get(container_key)
            if isinstance(container, dict):
                for key in ("glb_url", "mesh_url", "glb", "mesh", "replacement_glb", "path", "url"):
                    if isinstance(container.get(key), str):
                        return container[key]
            if isinstance(container, list):
                for item in container:
                    if isinstance(item, dict) and str(item.get("format", item.get("type", ""))).lower() in {"glb", "mesh/glb", "model/gltf-binary"}:
                        for key in ("url", "path"):
                            if isinstance(item.get(key), str):
                                return item[key]
        return None


class Handler(BaseHTTPRequestHandler):
    service: GlyphService
    api_token = os.environ.get("GLYPH_API_TOKEN", "")

    def do_OPTIONS(self):
        self.send_response(204)
        self._headers()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            self._require_authorization()
            if path == "/api/health":
                self._json({"ok": True, "blender": self.service.blender.available()})
            elif path == "/api/scene":
                self._json(self.service.scene())
            elif path == "/api/settings":
                self._json(self.service.public_settings())
            elif path == "/api/auth/chatgpt":
                self._json(self.service.chatgpt_auth())
            elif path == "/api/project/state":
                self._json(self.service.project.state())
            elif path.startswith("/api/trellis/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                self._json(self.service.mesh_job_status(job_id))
            else:
                self._json({"error": "Not found"}, 404)
        except Exception as exc:
            self._error(exc)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            self._require_authorization()
            payload = self._body()
            if path == "/api/project/open":
                self._json(self.service.blender.open_project(payload.get("path", "")))
            elif path == "/api/project/rename":
                self._json(self.service.project.rename(payload.get("name", "")))
            elif path == "/api/project/fork":
                self._json(self.service.project.fork_project())
            elif path == "/api/source/import":
                self._json(self.service.project.import_source(payload.get("path", ""), payload.get("prompt", "")), 201)
            elif path == "/api/source/active":
                self._json(self.service.project.set_active_source(payload.get("source_id", "")))
            elif path == "/api/source/lock":
                self._json(self.service.project.lock_source(payload.get("confirmed") is True))
            elif path == "/api/preview":
                self._json(self.service.preview(payload))
            elif path == "/api/accept":
                self._json(self.service.blender.accept())
            elif path == "/api/reject":
                self._json(self.service.blender.reject())
            elif path == "/api/settings":
                self._json(self.service.save_settings(payload))
            elif path == "/api/auth/chatgpt/login":
                self._json(self.service.sign_in_chatgpt())
            elif path == "/api/trellis/jobs":
                self._json(self.service.submit_trellis(payload), 202)
            elif path == "/api/trellis/meshify":
                self._json(self.service.start_meshify(), 202)
            elif path == "/api/mesh/approve":
                self._json(self.service.approve_mesh(payload.get("path", "")))
            elif path == "/api/mesh/approve-job":
                self._json(self.service.approve_mesh_job())
            else:
                self._json({"error": "Not found"}, 404)
        except Exception as exc:
            self._error(exc)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def _headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, value, status=200):
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self._headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, exc: Exception):
        traceback.print_exc()
        status = 401 if isinstance(exc, PermissionError) else 400
        self._json({"error": str(exc), "type": type(exc).__name__}, status)

    def _require_authorization(self):
        if self.api_token and self.headers.get("Authorization") != f"Bearer {self.api_token}":
            raise PermissionError("Unauthorized local Glyph API request")

    def log_message(self, format, *args):
        print(f"GLYPH_API {self.address_string()} {format % args}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=47831)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.home() / "Library" / "Application Support" / "Glyph",
    )
    args = parser.parse_args()
    service = GlyphService(args.project_root.resolve(), args.workspace.expanduser().resolve())
    Handler.service = service
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"GLYPH_API_READY=http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
