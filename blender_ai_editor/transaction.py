"""Recoverable preview transactions for AI-generated edits."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid

import bpy


PREVIEW_PREFIX = "AI_EDIT_PREVIEW_"
BACKUP_PREFIX = "AI_EDIT_BACKUP_"
TRANSACTION_KEY = "bae_transaction_json"


def active_transaction(scene):
    raw = scene.get(TRANSACTION_KEY, "")
    return json.loads(raw) if raw else None


def _set_transaction(scene, transaction):
    scene[TRANSACTION_KEY] = json.dumps(transaction) if transaction else ""


def begin_preview(context, captured_context):
    if active_transaction(context.scene):
        raise RuntimeError("Accept or reject the current preview before starting another")

    selected_names = [item["name"] for item in captured_context["objects"]]
    originals = [bpy.data.objects.get(name) for name in selected_names]
    originals = [obj for obj in originals if obj is not None]
    if not originals:
        raise RuntimeError("The captured objects no longer exist")

    active = context.view_layer.objects.active
    original_mode = active.mode if active else "OBJECT"
    if active and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    transaction_id = uuid.uuid4().hex[:10]
    collection_name = PREVIEW_PREFIX + transaction_id
    preview_collection = bpy.data.collections.new(collection_name)
    context.scene.collection.children.link(preview_collection)
    items = []

    for original in originals:
        duplicate = original.copy()
        if original.data:
            duplicate.data = original.data.copy()
        duplicate.name = f"{original.name}__AI_PREVIEW"
        duplicate["bae_preview"] = True
        duplicate["bae_original_name"] = original.name
        preview_collection.objects.link(duplicate)
        original_collections = [collection.name for collection in original.users_collection]
        items.append(
            {
                "original_name": original.name,
                "preview_name": duplicate.name,
                "original_collections": original_collections,
                "hide_viewport": bool(original.hide_viewport),
                "hide_render": bool(original.hide_render),
            }
        )
        original.hide_viewport = True
        original.hide_render = True
        original.select_set(False)
        duplicate.select_set(True)

    if active:
        matching = next(
            (item for item in items if item["original_name"] == active.name), items[0]
        )
        context.view_layer.objects.active = bpy.data.objects[matching["preview_name"]]

    transaction = {
        "id": transaction_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "collection": collection_name,
        "original_mode": original_mode,
        "items": items,
        "context": captured_context,
    }
    _set_transaction(context.scene, transaction)
    return transaction


def reject_preview(context):
    transaction = active_transaction(context.scene)
    if not transaction:
        raise RuntimeError("There is no active preview")
    for item in transaction["items"]:
        preview = bpy.data.objects.get(item["preview_name"])
        if preview:
            bpy.data.objects.remove(preview, do_unlink=True)
        original = bpy.data.objects.get(item["original_name"])
        if original:
            original.hide_viewport = item["hide_viewport"]
            original.hide_render = item["hide_render"]
            original.select_set(True)
    collection = bpy.data.collections.get(transaction["collection"])
    if collection:
        bpy.data.collections.remove(collection)
    first = bpy.data.objects.get(transaction["items"][0]["original_name"])
    if first:
        context.view_layer.objects.active = first
    _set_transaction(context.scene, None)


def accept_preview(context):
    transaction = active_transaction(context.scene)
    if not transaction:
        raise RuntimeError("There is no active preview")

    backup_name = BACKUP_PREFIX + transaction["id"]
    backup_collection = bpy.data.collections.new(backup_name)
    context.scene.collection.children.link(backup_collection)
    backup_collection.hide_viewport = True
    backup_collection.hide_render = True

    accepted = []
    for item in transaction["items"]:
        original = bpy.data.objects.get(item["original_name"])
        preview = bpy.data.objects.get(item["preview_name"])
        if not original or not preview:
            continue
        final_name = item["original_name"]
        original.name = f"{final_name}__AI_BACKUP_{transaction['id']}"
        original["bae_backup_for"] = final_name
        for collection in list(original.users_collection):
            collection.objects.unlink(original)
        backup_collection.objects.link(original)
        original.hide_viewport = True
        original.hide_render = True

        for collection_name in item["original_collections"]:
            collection = bpy.data.collections.get(collection_name)
            if collection and preview.name not in collection.objects:
                collection.objects.link(preview)
        preview_collection = bpy.data.collections.get(transaction["collection"])
        if preview_collection and preview.name in preview_collection.objects:
            preview_collection.objects.unlink(preview)
        preview.name = final_name
        if "bae_preview" in preview:
            del preview["bae_preview"]
        if "bae_original_name" in preview:
            del preview["bae_original_name"]
        preview.select_set(True)
        accepted.append(preview)

    preview_collection = bpy.data.collections.get(transaction["collection"])
    if preview_collection:
        bpy.data.collections.remove(preview_collection)
    if accepted:
        context.view_layer.objects.active = accepted[0]
    _set_transaction(context.scene, None)
    return backup_name
