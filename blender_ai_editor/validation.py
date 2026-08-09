"""Geometry validation used before an edit preview is shown."""

from __future__ import annotations

import math

import bpy


def validate_preview(transaction, tolerance=1e-6):
    errors = []
    warnings = []
    context_records = {item["name"]: item for item in transaction["context"]["objects"]}
    for item in transaction["items"]:
        original = bpy.data.objects.get(item["original_name"])
        preview = bpy.data.objects.get(item["preview_name"])
        if not original or not preview:
            errors.append(f"Transaction object missing: {item['original_name']}")
            continue
        if original.type != "MESH" or preview.type != "MESH":
            continue
        if len(original.data.vertices) != len(preview.data.vertices):
            warnings.append(f"{preview.name}: topology changed; protected vertices were not compared")
            continue
        selection = set(
            context_records.get(item["original_name"], {}).get("selection", {}).get("vertices", [])
        )
        if selection:
            for index, vertex in enumerate(preview.data.vertices):
                if index not in selection and (vertex.co - original.data.vertices[index].co).length > tolerance:
                    errors.append(f"{preview.name}: protected vertex {index} changed")
                    break
        for vertex in preview.data.vertices:
            if not all(math.isfinite(value) for value in vertex.co):
                errors.append(f"{preview.name}: non-finite vertex coordinate")
                break
        zero_faces = sum(1 for polygon in preview.data.polygons if polygon.area <= tolerance)
        if zero_faces:
            warnings.append(f"{preview.name}: {zero_faces} zero-area face(s)")
    return errors, warnings
