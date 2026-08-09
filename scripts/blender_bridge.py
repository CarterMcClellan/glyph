"""Run one safe Glyph command inside Blender and persist the working .blend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blender_ai_editor.executor import execute_plan
from blender_ai_editor.protocol import EditPlan
from blender_ai_editor.transaction import (
    accept_preview,
    active_transaction,
    begin_preview,
    reject_preview,
)
from blender_ai_editor.validation import validate_preview


def _args():
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session", type=Path, required=True)
    return parser.parse_args(values)


def _ensure_scene():
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if meshes:
        return
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12)
    obj = bpy.context.object
    obj.name = "Starter Mesh"
    obj.scale = (1.35, 1.0, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def _visible_meshes():
    return [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH"
        and not obj.hide_get()
        and not obj.hide_viewport
        and not obj.name.startswith("AI_EDIT_BACKUP_")
    ]


def _mesh_record(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    matrix = obj.matrix_world
    positions = []
    vertex_positions = []
    for vertex in mesh.vertices:
        point = matrix @ vertex.co
        vertex_positions.extend((round(point.x, 7), round(point.y, 7), round(point.z, 7)))
    triangle_polygons = []
    for triangle in mesh.loop_triangles:
        for vertex_index in triangle.vertices:
            point = matrix @ mesh.vertices[vertex_index].co
            positions.extend((round(point.x, 7), round(point.y, 7), round(point.z, 7)))
        triangle_polygons.append(triangle.polygon_index)
    polygons = [
        {"index": polygon.index, "vertices": list(polygon.vertices)} for polygon in mesh.polygons
    ]
    label = obj.name.replace("__AI_PREVIEW", "")
    material_color = (
        list(obj.active_material.diffuse_color[:3])
        if obj.active_material is not None
        else [0.68, 0.71, 0.73]
    )
    return {
        "id": obj.name,
        "label": label,
        "collection": obj.users_collection[0].name if obj.users_collection else "Scene",
        "vertex_count": len(mesh.vertices),
        "edge_count": len(mesh.edges),
        "face_count": len(mesh.polygons),
        "positions": positions,
        "vertex_positions": vertex_positions,
        "edges": [list(edge.vertices) for edge in mesh.edges],
        "triangle_polygons": triangle_polygons,
        "polygons": polygons,
        "preview": bool(obj.get("bae_preview", False)),
        "material_color": material_color,
    }


def scene_data():
    objects = [_mesh_record(obj) for obj in _visible_meshes()]
    collections = []
    for collection in bpy.data.collections:
        ids = [obj.name for obj in collection.objects if any(item["id"] == obj.name for item in objects)]
        if ids:
            collections.append({"name": collection.name, "objects": ids})
    return {
        "name": bpy.context.scene.name,
        "unit_system": bpy.context.scene.unit_settings.system,
        "objects": objects,
        "collections": collections,
        "preview_active": bool(active_transaction(bpy.context.scene)),
    }


def _select_mesh(object_name: str, face_indices: list[int]):
    if active_transaction(bpy.context.scene):
        raise RuntimeError("Accept or reject the current preview first")
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj = bpy.data.objects.get(object_name)
    if not obj or obj.type != "MESH":
        raise ValueError(f"Mesh not found: {object_name}")
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for vertex in obj.data.vertices:
        vertex.select = False
    for edge in obj.data.edges:
        edge.select = False
    for polygon in obj.data.polygons:
        polygon.select = False
    valid_faces = [index for index in face_indices if 0 <= index < len(obj.data.polygons)]
    for index in valid_faces:
        polygon = obj.data.polygons[index]
        polygon.select = True
        for vertex_index in polygon.vertices:
            obj.data.vertices[vertex_index].select = True
    if not valid_faces:
        for vertex in obj.data.vertices:
            vertex.select = True
    return obj


def _captured_context(obj, face_indices):
    valid_faces = [index for index in face_indices if 0 <= index < len(obj.data.polygons)]
    vertices = sorted(
        {vertex for index in valid_faces for vertex in obj.data.polygons[index].vertices}
    )
    if not valid_faces:
        vertices = list(range(len(obj.data.vertices)))
    return {
        "scene": bpy.context.scene.name,
        "active_object": obj.name,
        "mode": "EDIT",
        "unit_system": bpy.context.scene.unit_settings.system,
        "objects": [
            {
                "name": obj.name,
                "type": "MESH",
                "mode": "OBJECT",
                "vertex_count": len(obj.data.vertices),
                "edge_count": len(obj.data.edges),
                "face_count": len(obj.data.polygons),
                "selection": {"vertices": vertices, "edges": [], "faces": valid_faces},
            }
        ],
    }


def run(command: str, payload: dict):
    _ensure_scene()
    if command == "scene":
        return scene_data()
    if command == "import_mesh":
        path = Path(payload["path"]).expanduser().resolve()
        if path.suffix.lower() not in {".glb", ".gltf"} or not path.is_file():
            raise ValueError("Choose an existing GLB or glTF mesh")
        if active_transaction(bpy.context.scene):
            reject_preview(bpy.context)
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.gltf(filepath=str(path))
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        if not meshes:
            raise RuntimeError("The imported file did not contain a mesh")
        bpy.context.view_layer.objects.active = meshes[0]
        meshes[0].select_set(True)
        return scene_data()
    if command == "preview":
        obj = _select_mesh(payload["object_name"], payload.get("face_indices", []))
        context = _captured_context(obj, payload.get("face_indices", []))
        plan = EditPlan.from_dict(payload["plan"])
        transaction = begin_preview(bpy.context, context)
        try:
            execute_plan(transaction, plan)
            errors, warnings = validate_preview(transaction)
            if errors:
                raise RuntimeError("Validation failed: " + "; ".join(errors))
        except Exception:
            if active_transaction(bpy.context.scene):
                reject_preview(bpy.context)
            raise
        return {"scene": scene_data(), "transaction": transaction, "warnings": warnings}
    if command == "accept":
        backup = accept_preview(bpy.context)
        return {"scene": scene_data(), "backup": backup}
    if command == "reject":
        reject_preview(bpy.context)
        return {"scene": scene_data()}
    raise ValueError(f"Unknown Blender bridge command: {command}")


def main():
    args = _args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    try:
        data = run(args.command, payload)
        bpy.ops.wm.save_as_mainfile(filepath=str(args.session))
        result = {"ok": True, "data": data}
    except Exception as exc:
        traceback.print_exc()
        result = {"ok": False, "error": str(exc), "type": type(exc).__name__}
    args.output.write_text(json.dumps(result), encoding="utf-8")


main()
