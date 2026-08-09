"""Blender operators exposed by the Glyph sidebar."""

from __future__ import annotations

import json
from pathlib import Path

import bpy
from bpy.props import StringProperty

from .context_capture import capture_context
from .executor import execute_plan
from .planner import create_plan
from .transaction import accept_preview, active_transaction, begin_preview, reject_preview
from .trellis_bridge import export_generation_job, launch_generation_job, worker_status
from .validation import validate_preview


class BAE_OT_add_reference(bpy.types.Operator):
    bl_idname = "bae.add_reference"
    bl_label = "Add Reference Image"
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff", options={"HIDDEN"})

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        path = str(Path(self.filepath).expanduser().resolve())
        if not Path(path).is_file():
            self.report({"ERROR"}, "Reference image does not exist")
            return {"CANCELLED"}
        settings = context.scene.bae_settings
        if path not in [item.filepath for item in settings.references]:
            item = settings.references.add()
            item.filepath = path
            settings.active_reference = len(settings.references) - 1
        return {"FINISHED"}


class BAE_OT_remove_reference(bpy.types.Operator):
    bl_idname = "bae.remove_reference"
    bl_label = "Remove Reference Image"

    @classmethod
    def poll(cls, context):
        return bool(context.scene.bae_settings.references)

    def execute(self, context):
        settings = context.scene.bae_settings
        settings.references.remove(settings.active_reference)
        settings.active_reference = min(
            settings.active_reference, max(0, len(settings.references) - 1)
        )
        return {"FINISHED"}


class BAE_OT_capture_context(bpy.types.Operator):
    bl_idname = "bae.capture_context"
    bl_label = "Capture Selection"
    bl_description = "Capture selected objects, mesh elements, bounds, and topology counts"

    def execute(self, context):
        settings = context.scene.bae_settings
        try:
            captured = capture_context(context)
            settings.last_context_json = json.dumps(captured, indent=2)
            settings.status = (
                f"Captured {len(captured['objects'])} object(s). "
                "Ready to create a preview."
            )
        except Exception as exc:
            settings.status = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class BAE_OT_plan_preview(bpy.types.Operator):
    bl_idname = "bae.plan_preview"
    bl_label = "Generate Preview"
    bl_description = "Plan a constrained edit, apply it to a duplicate, then validate it"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.bae_settings
        return bool(settings.instruction.strip()) and not active_transaction(context.scene)

    def execute(self, context):
        settings = context.scene.bae_settings
        transaction_started = False
        try:
            captured = capture_context(context)
            references = [item.filepath for item in settings.references]
            settings.status = f"Planning with {settings.backend}…"
            plan = create_plan(
                settings.backend,
                settings.instruction,
                captured,
                references,
                settings.model,
                settings.codex_executable,
            )
            transaction = begin_preview(context, captured)
            transaction_started = True
            execute_plan(transaction, plan)
            errors, warnings = validate_preview(transaction)
            if errors:
                raise RuntimeError("Validation failed: " + "; ".join(errors))
            settings.last_context_json = json.dumps(captured, indent=2)
            settings.last_plan_json = plan.to_json()
            suffix = f" Warnings: {'; '.join(warnings)}" if warnings else ""
            settings.status = f"Preview ready: {plan.summary}.{suffix}"
        except Exception as exc:
            if transaction_started and active_transaction(context.scene):
                try:
                    reject_preview(context)
                except Exception:
                    pass
            settings.status = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class BAE_OT_accept_preview(bpy.types.Operator):
    bl_idname = "bae.accept_preview"
    bl_label = "Accept"
    bl_description = "Keep the preview and move the original into a hidden backup collection"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(active_transaction(context.scene))

    def execute(self, context):
        settings = context.scene.bae_settings
        try:
            backup = accept_preview(context)
            settings.status = f"Edit accepted. Original preserved in {backup}."
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class BAE_OT_reject_preview(bpy.types.Operator):
    bl_idname = "bae.reject_preview"
    bl_label = "Reject"
    bl_description = "Delete the preview and restore the untouched original"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(active_transaction(context.scene))

    def execute(self, context):
        settings = context.scene.bae_settings
        try:
            reject_preview(context)
            settings.status = "Preview rejected; original restored."
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class BAE_OT_trellis_status(bpy.types.Operator):
    bl_idname = "bae.trellis_status"
    bl_label = "Check TRELLIS"

    def execute(self, context):
        settings = context.scene.bae_settings
        status = worker_status(settings.trellis_repo)
        settings.status = (
            f"TRELLIS.2 {'ready' if status['cuda_available'] else 'not CUDA-ready'}: "
            f"{status.get('cuda_device') or status['repo']}"
        )
        self.report({"INFO"}, settings.status)
        return {"FINISHED"}


class BAE_OT_export_trellis_job(bpy.types.Operator):
    bl_idname = "bae.export_trellis_job"
    bl_label = "Export TRELLIS Job"
    bl_description = "Create an auditable generation job for the local TRELLIS worker"

    @classmethod
    def poll(cls, context):
        return bool(context.scene.bae_settings.instruction.strip())

    def execute(self, context):
        settings = context.scene.bae_settings
        try:
            captured = capture_context(context)
            job = export_generation_job(
                settings.trellis_repo,
                settings.instruction,
                captured,
                [item.filepath for item in settings.references],
                settings.trellis_jobs,
            )
            settings.last_trellis_job = str(job)
            settings.status = f"TRELLIS job exported: {job}"
        except Exception as exc:
            settings.status = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class BAE_OT_launch_trellis_job(bpy.types.Operator):
    bl_idname = "bae.launch_trellis_job"
    bl_label = "Run Last Job on NVIDIA"
    bl_description = "Start TRELLIS.2 out-of-process and refuse CPU fallback"

    @classmethod
    def poll(cls, context):
        return bool(context.scene.bae_settings.last_trellis_job)

    def execute(self, context):
        settings = context.scene.bae_settings
        try:
            pid, log = launch_generation_job(settings.last_trellis_job)
            settings.status = f"TRELLIS running on CUDA (PID {pid}). Log: {log}"
        except Exception as exc:
            settings.status = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = (
    BAE_OT_add_reference,
    BAE_OT_remove_reference,
    BAE_OT_capture_context,
    BAE_OT_plan_preview,
    BAE_OT_accept_preview,
    BAE_OT_reject_preview,
    BAE_OT_trellis_status,
    BAE_OT_export_trellis_job,
    BAE_OT_launch_trellis_job,
)
