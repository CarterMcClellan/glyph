"""Sidebar UI and persistent settings."""

from __future__ import annotations

import bpy
from bpy.props import CollectionProperty, EnumProperty, IntProperty, PointerProperty, StringProperty

from .transaction import active_transaction


class BAE_ReferenceImage(bpy.types.PropertyGroup):
    filepath: StringProperty(name="Image", subtype="FILE_PATH")


class BAE_Settings(bpy.types.PropertyGroup):
    instruction: StringProperty(
        name="Instruction",
        description="Describe the change to make to the current Blender selection",
        default="",
    )
    backend: EnumProperty(
        name="Planner",
        items=(
            ("LOCAL", "Local commands", "Offline parser for basic operations"),
            ("CODEX", "Codex (ChatGPT sign-in)", "Use the installed Codex CLI and attached images"),
            ("OPENAI", "OpenAI API", "Use OPENAI_API_KEY and the Responses API"),
        ),
        default="LOCAL",
    )
    model: StringProperty(name="Model", default="gpt-5.6-sol")
    codex_executable: StringProperty(name="Codex executable", default="codex")
    trellis_repo: StringProperty(name="TRELLIS repo", subtype="DIR_PATH", default="~/code/TRELLIS.2")
    trellis_jobs: StringProperty(
        name="TRELLIS jobs", subtype="DIR_PATH", default="~/code/glyph-jobs"
    )
    references: CollectionProperty(type=BAE_ReferenceImage)
    active_reference: IntProperty(default=0)
    status: StringProperty(default="Select geometry, describe an edit, then generate a preview.")
    last_context_json: StringProperty(default="", options={"HIDDEN"})
    last_plan_json: StringProperty(default="", options={"HIDDEN"})
    last_trellis_job: StringProperty(default="", options={"HIDDEN"})


class BAE_UL_references(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        layout.label(text=item.filepath.rsplit("/", 1)[-1], icon="IMAGE_DATA")


class BAE_PT_editor(bpy.types.Panel):
    bl_label = "Glyph"
    bl_idname = "BAE_PT_editor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Glyph"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bae_settings
        transaction = active_transaction(context.scene)

        layout.label(text="1. Select object, faces, or vertices")
        layout.operator("bae.capture_context", icon="RESTRICT_SELECT_OFF")

        layout.separator()
        layout.label(text="2. Describe the change")
        layout.prop(settings, "instruction", text="")

        layout.separator()
        header = layout.row()
        header.label(text="3. Reference images")
        header.operator("bae.add_reference", text="", icon="ADD")
        if settings.references:
            layout.template_list(
                "BAE_UL_references", "", settings, "references", settings, "active_reference", rows=2
            )
            layout.operator("bae.remove_reference", icon="REMOVE")

        layout.separator()
        layout.prop(settings, "backend")
        if settings.backend in {"CODEX", "OPENAI"}:
            layout.prop(settings, "model")
        if transaction:
            box = layout.box()
            box.label(text="Preview is active", icon="HIDE_OFF")
            row = box.row(align=True)
            row.operator("bae.accept_preview", icon="CHECKMARK")
            row.operator("bae.reject_preview", icon="X")
        else:
            layout.operator("bae.plan_preview", icon="PLAY")

        status = layout.box()
        status.label(text="Status", icon="INFO")
        for line in _wrap(settings.status, 44):
            status.label(text=line)


class BAE_PT_trellis(bpy.types.Panel):
    bl_label = "TRELLIS.2 Bridge"
    bl_parent_id = "BAE_PT_editor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Glyph"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bae_settings
        layout.prop(settings, "trellis_repo")
        layout.prop(settings, "trellis_jobs")
        row = layout.row(align=True)
        row.operator("bae.trellis_status", icon="GPU")
        row.operator("bae.export_trellis_job", icon="EXPORT")
        if settings.last_trellis_job:
            layout.operator("bae.launch_trellis_job", icon="PLAY")
        layout.label(text="Generation runs out-of-process on CUDA.")


class BAE_PT_advanced(bpy.types.Panel):
    bl_label = "Advanced"
    bl_parent_id = "BAE_PT_editor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Glyph"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.bae_settings
        self.layout.prop(settings, "codex_executable")
        if settings.last_plan_json:
            self.layout.label(text="Last plan stored in scene metadata")


def _wrap(text, width):
    words = text.split()
    lines, current = [], []
    for word in words:
        if current and len(" ".join(current + [word])) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines or [""]


CLASSES = (
    BAE_ReferenceImage,
    BAE_Settings,
    BAE_UL_references,
    BAE_PT_editor,
    BAE_PT_trellis,
    BAE_PT_advanced,
)


def register_scene_properties():
    bpy.types.Scene.bae_settings = PointerProperty(type=BAE_Settings)


def unregister_scene_properties():
    if hasattr(bpy.types.Scene, "bae_settings"):
        del bpy.types.Scene.bae_settings
