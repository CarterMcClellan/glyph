"""Execute the narrow, auditable operation vocabulary on preview meshes."""

from __future__ import annotations

import math

import bpy
from mathutils import Euler, Vector


def _selection_for(transaction, original_name, mesh):
    record = next(
        (item for item in transaction["context"]["objects"] if item["name"] == original_name),
        None,
    )
    indices = (record or {}).get("selection", {}).get("vertices", [])
    valid = [index for index in indices if 0 <= index < len(mesh.vertices)]
    return valid if valid else list(range(len(mesh.vertices)))


def _center(mesh, indices):
    return sum((mesh.vertices[index].co for index in indices), Vector()) / max(len(indices), 1)


def _neighbors(mesh):
    result = {vertex.index: set() for vertex in mesh.vertices}
    for edge in mesh.edges:
        a, b = edge.vertices
        result[a].add(b)
        result[b].add(a)
    return result


def _set_color(obj, color):
    rgba = list(color)
    if len(rgba) == 3:
        rgba.append(1.0)
    source_material = obj.active_material
    if source_material is not None and not source_material.library:
        material = source_material.copy()
        material.name = f"{source_material.name}_AI_PREVIEW"
        obj.active_material = material
    else:
        material = bpy.data.materials.new(name=f"{obj.name}_AI_Material")
        if obj.data.materials:
            obj.data.materials[0] = material
        else:
            obj.data.materials.append(material)
    material.diffuse_color = rgba
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled:
        principled.inputs["Base Color"].default_value = rgba


def execute_plan(transaction, plan):
    for item in transaction["items"]:
        obj = bpy.data.objects.get(item["preview_name"])
        if not obj:
            raise RuntimeError(f"Missing preview object: {item['preview_name']}")
        for operation in plan.operations:
            if operation.type == "set_color":
                _set_color(obj, operation.color)
                continue
            if obj.type != "MESH":
                raise RuntimeError(f"Geometry operation requires a mesh: {obj.name}")
            mesh = obj.data
            indices = _selection_for(transaction, item["original_name"], mesh)
            if not indices:
                raise RuntimeError(f"No editable vertices in {obj.name}")
            center = _center(mesh, indices)
            if operation.type == "scale":
                scale = Vector(operation.vector) if operation.vector else Vector((operation.amount,) * 3)
                for index in indices:
                    vertex = mesh.vertices[index]
                    vertex.co = center + (vertex.co - center) * scale
            elif operation.type == "translate":
                offset = Vector(operation.vector)
                for index in indices:
                    mesh.vertices[index].co += offset
            elif operation.type == "rotate":
                rotation = Euler(tuple(math.radians(value) for value in operation.vector), "XYZ")
                for index in indices:
                    vertex = mesh.vertices[index]
                    offset = vertex.co - center
                    offset.rotate(rotation)
                    vertex.co = center + offset
            elif operation.type == "inflate":
                mesh.update()
                for index in indices:
                    vertex = mesh.vertices[index]
                    vertex.co += vertex.normal * operation.amount
            elif operation.type == "smooth":
                neighbors = _neighbors(mesh)
                selected = set(indices)
                factor = operation.amount if operation.amount is not None else 0.5
                for _ in range(operation.iterations or 1):
                    updates = {}
                    for index in indices:
                        adjacent = [n for n in neighbors[index] if n in selected]
                        if adjacent:
                            average = sum((mesh.vertices[n].co for n in adjacent), Vector()) / len(adjacent)
                            updates[index] = mesh.vertices[index].co.lerp(average, factor)
                    for index, coordinate in updates.items():
                        mesh.vertices[index].co = coordinate
            mesh.update()
