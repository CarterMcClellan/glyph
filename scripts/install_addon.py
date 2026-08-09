"""Install or update Glyph in the current Blender user profile."""

from pathlib import Path
import shutil

import addon_utils
import bpy


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "blender_ai_editor"
TARGET = Path(bpy.utils.user_resource("SCRIPTS", path="addons", create=True)) / SOURCE.name

if TARGET.exists():
    shutil.rmtree(TARGET)
shutil.copytree(SOURCE, TARGET)
addon_utils.modules_refresh()
addon_utils.enable("blender_ai_editor", default_set=True, persistent=True)
bpy.ops.wm.save_userpref()
print(f"GLYPH_INSTALLED={TARGET}")
