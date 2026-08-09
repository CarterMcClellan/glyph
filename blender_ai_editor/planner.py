"""Planning adapters: deterministic local parser, Codex CLI, and Responses API."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib import request

from .protocol import EditOperation, EditPlan, compact_context, edit_plan_schema


SYSTEM_PROMPT = """You plan safe, localized Blender mesh edits.
Return only an EditPlan matching the supplied schema. Every operation must target the current
selection. Prefer a small sequence. Never invent file paths or emit Python. Supported operations:
scale (amount or vector), translate (vector in local units), rotate (vector in degrees), inflate
(amount in local units), smooth (amount 0..1 and iterations), set_color (RGB/RGBA 0..1).
"""


def _number_after(pattern, text, default):
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else default


def local_plan(instruction, _context, _references):
    """Predictable offline planner, useful for tests and simple direct edits."""
    text = instruction.strip().lower()
    operations = []
    assumptions = []

    scale_match = re.search(r"(?:scale|make)\D{0,20}?(\d+(?:\.\d+)?)\s*(?:x|times)?", text)
    if "scale" in text or "larger" in text or "smaller" in text:
        if scale_match:
            factor = float(scale_match.group(1))
        elif "smaller" in text:
            factor = 0.9
            assumptions.append("Used a 0.9 scale factor because none was specified")
        else:
            factor = 1.1
            assumptions.append("Used a 1.1 scale factor because none was specified")
        operations.append(EditOperation("scale", amount=factor))

    directions = {
        "up": (0, 0, 1), "down": (0, 0, -1),
        "left": (-1, 0, 0), "right": (1, 0, 0),
        "forward": (0, -1, 0), "back": (0, 1, 0),
    }
    if any(word in text for word in ("move", "shift", "raise", "lower")):
        amount = _number_after(r"(?:move|shift|raise|lower).*?(\d+(?:\.\d+)?)", text, 0.1)
        direction = next((vec for word, vec in directions.items() if word in text), (0, 0, 1))
        if "lower" in text:
            direction = (0, 0, -1)
        operations.append(EditOperation("translate", vector=[amount * v for v in direction]))

    if "rotate" in text or "turn" in text:
        degrees = _number_after(r"(?:rotate|turn).*?(\d+(?:\.\d+)?)", text, 15.0)
        axis = [0.0, 0.0, degrees]
        if "x axis" in text:
            axis = [degrees, 0.0, 0.0]
        elif "y axis" in text:
            axis = [0.0, degrees, 0.0]
        operations.append(EditOperation("rotate", vector=axis))

    if any(word in text for word in ("inflate", "puff", "thicken")):
        amount = _number_after(r"(?:inflate|puff|thicken).*?(\d+(?:\.\d+)?)", text, 0.05)
        operations.append(EditOperation("inflate", amount=amount))

    if "smooth" in text:
        amount = _number_after(r"smooth.*?(0(?:\.\d+)?|1(?:\.0+)?)", text, 0.5)
        operations.append(EditOperation("smooth", amount=amount, iterations=2))

    colors = {
        "red": [0.8, 0.03, 0.03, 1.0], "blue": [0.03, 0.12, 0.8, 1.0],
        "green": [0.03, 0.65, 0.12, 1.0], "black": [0.01, 0.01, 0.01, 1.0],
        "white": [0.95, 0.95, 0.95, 1.0], "gold": [0.9, 0.55, 0.05, 1.0],
        "purple": [0.45, 0.05, 0.7, 1.0],
    }
    chosen_color = next((rgba for name, rgba in colors.items() if name in text), None)
    if chosen_color and any(word in text for word in ("color", "colour", "make", "paint")):
        operations.append(EditOperation("set_color", color=chosen_color))

    if not operations:
        raise ValueError(
            "The local planner understands scale, move, rotate, inflate, smooth, and basic colors. "
            "Choose Codex for a freer instruction."
        )
    return EditPlan(
        summary=f"Apply {len(operations)} localized operation(s) to the current selection",
        operations=operations,
        assumptions=assumptions,
    )


def _planner_prompt(instruction, context, references):
    return (
        SYSTEM_PROMPT
        + "\nUser instruction:\n"
        + instruction
        + "\n\nSelection context:\n"
        + json.dumps(compact_context(context), indent=2)
        + "\n\nReference image paths:\n"
        + json.dumps(references, indent=2)
    )


def codex_plan(instruction, context, references, model="gpt-5.6-sol", executable="codex"):
    binary = shutil.which(executable) if os.path.sep not in executable else executable
    if not binary or not Path(binary).exists():
        raise RuntimeError("Codex CLI was not found. Set its path in Advanced settings.")
    with tempfile.TemporaryDirectory(prefix="blender_ai_edit_") as folder:
        folder_path = Path(folder)
        schema_path = folder_path / "edit_plan.schema.json"
        output_path = folder_path / "edit_plan.json"
        schema_path.write_text(json.dumps(edit_plan_schema()), encoding="utf-8")
        command = [
            binary, "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
            "--model", model, "--output-schema", str(schema_path),
            "--output-last-message", str(output_path), "--color", "never",
        ]
        for image_path in references:
            if Path(image_path).is_file():
                command.extend(["--image", image_path])
        command.append("-")
        completed = subprocess.run(
            command,
            input=_planner_prompt(instruction, context, references),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Codex planning failed: {detail[-1200:]}")
        return EditPlan.from_json(output_path.read_text(encoding="utf-8"))


def _data_url(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def responses_plan(instruction, context, references, model="gpt-5.6-sol"):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not available to Blender")
    content = [{"type": "input_text", "text": _planner_prompt(instruction, context, references)}]
    for path in references:
        if Path(path).is_file():
            content.append({"type": "input_image", "image_url": _data_url(path)})
    payload = {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema", "name": "blender_edit_plan",
                "strict": True, "schema": edit_plan_schema(),
            }
        },
    }
    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"OpenAI planning failed: {exc}") from exc
    output_text = result.get("output_text")
    if not output_text:
        for item in result.get("output", []):
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    output_text = part.get("text")
                    break
    if not output_text:
        raise RuntimeError("The OpenAI response did not contain an edit plan")
    return EditPlan.from_json(output_text)


def create_plan(backend, instruction, context, references, model, codex_executable):
    if backend == "LOCAL":
        return local_plan(instruction, context, references)
    if backend == "CODEX":
        return codex_plan(instruction, context, references, model, codex_executable)
    if backend == "OPENAI":
        return responses_plan(instruction, context, references, model)
    raise ValueError(f"Unknown planner backend: {backend}")
