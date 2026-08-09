"""Capture a compact, selection-aware description of the active Blender scene."""

from __future__ import annotations

import bmesh
import bpy
from mathutils import Vector


def _bounds(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return {
        "min": [min(point[i] for point in points) for i in range(3)],
        "max": [max(point[i] for point in points) for i in range(3)],
    }


def _mesh_selection(obj):
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        return {
            "vertices": [v.index for v in bm.verts if v.select],
            "edges": [e.index for e in bm.edges if e.select],
            "faces": [f.index for f in bm.faces if f.select],
        }
    return {
        "vertices": [v.index for v in obj.data.vertices if v.select],
        "edges": [e.index for e in obj.data.edges if e.select],
        "faces": [p.index for p in obj.data.polygons if p.select],
    }


def capture_context(context):
    active = context.view_layer.objects.active
    selected = list(context.selected_objects)
    if active and active.mode == "EDIT" and active not in selected:
        selected.append(active)
    if not selected:
        raise ValueError("Select at least one object or mesh region first")

    objects = []
    for obj in selected:
        record = {
            "name": obj.name,
            "type": obj.type,
            "mode": obj.mode,
            "bounds_world": _bounds(obj),
            "location": list(obj.location),
            "rotation_euler": list(obj.rotation_euler),
            "scale": list(obj.scale),
        }
        if obj.type == "MESH":
            record.update(
                {
                    "vertex_count": len(obj.data.vertices),
                    "edge_count": len(obj.data.edges),
                    "face_count": len(obj.data.polygons),
                    "selection": _mesh_selection(obj),
                }
            )
        objects.append(record)

    return {
        "scene": context.scene.name,
        "active_object": active.name if active else None,
        "mode": active.mode if active else "OBJECT",
        "unit_system": context.scene.unit_settings.system,
        "objects": objects,
    }
