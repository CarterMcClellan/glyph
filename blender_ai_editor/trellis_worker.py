"""Out-of-process NVIDIA TRELLIS.2 image-to-3D worker."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import traceback


def _save(path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run(job_path):
    job_path = Path(job_path).resolve()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    repo = Path(job["runtime"]["repo"])
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    job["status"] = "loading_model"
    job["started_at"] = datetime.now(timezone.utc).isoformat()
    _save(job_path, job)

    import torch
    from PIL import Image
    import o_voxel
    from trellis2.pipelines import Trellis2ImageTo3DPipeline

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required; refusing to fall back to CPU")
    reference = Path(job["reference_images"][0]).expanduser().resolve()
    if not reference.is_file():
        raise FileNotFoundError(reference)
    image = Image.open(reference)
    pipeline = Trellis2ImageTo3DPipeline.from_pretrained("microsoft/TRELLIS.2-4B")
    pipeline.cuda()
    job["status"] = "generating"
    _save(job_path, job)
    mesh = pipeline.run(image)[0]
    mesh.simplify(16_777_216)

    output = job_path.with_name("replacement.glb")
    glb = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices,
        faces=mesh.faces,
        attr_volume=mesh.attrs,
        coords=mesh.coords,
        attr_layout=mesh.layout,
        voxel_size=mesh.voxel_size,
        aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=300_000,
        texture_size=2048,
        remesh=True,
        remesh_band=1,
        remesh_project=0,
        verbose=True,
    )
    glb.export(str(output), extension_webp=True)
    provenance = {
        "model": "microsoft/TRELLIS.2-4B",
        "device": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "reference_images": job["reference_images"],
        "instruction": job["instruction"],
        "note": "TRELLIS.2 image-to-3D currently uses the first reference; text guides review only.",
    }
    _save(job_path.with_name("provenance.json"), provenance)
    _save(job_path.with_name("validation.json"), {"glb_exists": output.is_file()})
    job["status"] = "complete"
    job["completed_at"] = datetime.now(timezone.utc).isoformat()
    job["output_glb"] = str(output)
    _save(job_path, job)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    job_path = Path(args.job).resolve()
    try:
        run(job_path)
    except Exception as exc:
        try:
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["status"] = "failed"
            job["error"] = str(exc)
            job["traceback"] = traceback.format_exc()
            _save(job_path, job)
        finally:
            raise


if __name__ == "__main__":
    main()
