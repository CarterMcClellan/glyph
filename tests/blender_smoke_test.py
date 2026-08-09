"""Run with: blender --background --factory-startup --python tests/blender_smoke_test.py"""

import json
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import blender_ai_editor
from blender_ai_editor.context_capture import capture_context
from blender_ai_editor.executor import execute_plan
from blender_ai_editor.planner import local_plan
from blender_ai_editor.transaction import accept_preview, begin_preview, reject_preview
from blender_ai_editor.validation import validate_preview


def reset_cube():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.object
    cube.name = "SmokeCube"
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for index in (4, 5, 6, 7):
        cube.data.vertices[index].select = True
    bpy.ops.object.mode_set(mode="EDIT")
    return cube


def test_reject():
    cube = reset_cube()
    original = [vertex.co.copy() for vertex in cube.data.vertices]
    context_data = capture_context(bpy.context)
    plan = local_plan("move up 0.25", context_data, [])
    transaction = begin_preview(bpy.context, context_data)
    execute_plan(transaction, plan)
    errors, _warnings = validate_preview(transaction)
    assert not errors, errors
    reject_preview(bpy.context)
    restored = bpy.data.objects["SmokeCube"]
    assert all((a - b.co).length < 1e-7 for a, b in zip(original, restored.data.vertices))


def test_accept_backup():
    cube = reset_cube()
    context_data = capture_context(bpy.context)
    plan = local_plan("scale 1.2", context_data, [])
    transaction = begin_preview(bpy.context, context_data)
    execute_plan(transaction, plan)
    errors, _warnings = validate_preview(transaction)
    assert not errors, errors
    backup = accept_preview(bpy.context)
    assert bpy.data.objects.get("SmokeCube") is not None
    assert bpy.data.collections.get(backup) is not None


def test_preview_color_does_not_touch_source_material():
    cube = reset_cube()
    material = bpy.data.materials.new("SourceMaterial")
    material.diffuse_color = (0.8, 0.1, 0.1, 1.0)
    cube.data.materials.append(material)
    original_color = tuple(material.diffuse_color)
    context_data = capture_context(bpy.context)
    plan = local_plan("make it blue", context_data, [])
    transaction = begin_preview(bpy.context, context_data)
    execute_plan(transaction, plan)
    assert tuple(material.diffuse_color) == original_color
    reject_preview(bpy.context)


blender_ai_editor.register()
test_reject()
test_accept_backup()
test_preview_color_does_not_touch_source_material()
print("BLENDER_SMOKE_TEST_OK")
