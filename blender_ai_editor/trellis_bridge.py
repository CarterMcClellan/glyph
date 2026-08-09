"""Stable job boundary for the installed TRELLIS.2 worker.

Phase 1 exports explicit jobs instead of allowing a generator to mutate a .blend file. A future
worker can consume the same job, generate a replacement part, and return a GLB plus provenance.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid


def worker_status(repo_path):
    root = Path(repo_path).expanduser()
    python = root / ".venv" / "bin" / "python"
    status = {
        "repo": str(root),
        "available": (root / "trellis2").is_dir(),
        "python": str(python),
        "cuda_available": False,
        "cuda_device": None,
        "torch": None,
        "cuda_version": None,
        "entrypoints": {
            "image_to_3d": str(root / "example.py"),
            "texturing": str(root / "example_texturing.py"),
        },
    }
    if status["available"] and python.is_file():
        probe = (
            "import json,torch;print(json.dumps({'cuda_available':torch.cuda.is_available(),"
            "'cuda_device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,"
            "'torch':torch.__version__,'cuda_version':torch.version.cuda}))"
        )
        try:
            completed = subprocess.run(
                [str(python), "-c", probe], text=True, capture_output=True, timeout=15, check=True
            )
            status.update(json.loads(completed.stdout.strip().splitlines()[-1]))
        except Exception as exc:
            status["probe_error"] = str(exc)
    return status


def export_generation_job(repo_path, instruction, context, references, output_root):
    status = worker_status(repo_path)
    if not status["available"]:
        raise RuntimeError(f"TRELLIS.2 was not found at {repo_path}")
    job_id = uuid.uuid4().hex
    root = Path(output_root).expanduser() / job_id
    root.mkdir(parents=True, exist_ok=False)
    payload = {
        "version": 1,
        "job_id": job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "instruction": instruction,
        "selection_context": context,
        "reference_images": references,
        "runtime": status,
        "require_cuda": True,
        "requested_outputs": ["replacement.glb", "provenance.json", "validation.json"],
        "status": "queued",
    }
    (root / "job.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return root / "job.json"


def launch_generation_job(job_path):
    job_path = Path(job_path).expanduser().resolve()
    payload = json.loads(job_path.read_text(encoding="utf-8"))
    runtime = payload["runtime"]
    if not runtime.get("cuda_available"):
        raise RuntimeError("TRELLIS launch refused: CUDA is not available")
    if not payload.get("reference_images"):
        raise RuntimeError("TRELLIS image-to-3D needs at least one reference image")
    worker = Path(__file__).resolve().with_name("trellis_worker.py")
    log_path = job_path.with_name("worker.log")
    with log_path.open("ab") as log_handle:
        process = subprocess.Popen(
            [runtime["python"], str(worker), "--job", str(job_path)],
            cwd=runtime["repo"],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    payload["status"] = "starting"
    payload["worker_pid"] = process.pid
    payload["worker_log"] = str(log_path)
    job_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return process.pid, log_path
