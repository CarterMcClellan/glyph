from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from glyph_harness.blender_client import BlenderClient, DEFAULT_BLENDER
from glyph_harness.harness import AgentHarness


@unittest.skipUnless(Path(DEFAULT_BLENDER).is_file(), "Blender app is not installed")
class StandaloneBlenderTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="glyph_standalone_test_"))
        self.client = BlenderClient(Path(__file__).resolve().parents[1], self.folder)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_preview_reject_and_accept_are_persistent(self):
        scene = self.client.scene()
        mesh = scene["objects"][0]
        preview = AgentHarness(self.client).preview(
            "inflate 0.05 and smooth 0.3", mesh["id"], [0], scene
        )
        self.assertTrue(preview["scene"]["preview_active"])
        self.assertEqual(len(preview["steps"]), 4)

        rejected = self.client.reject()
        self.assertFalse(rejected["scene"]["preview_active"])

        mesh = rejected["scene"]["objects"][0]
        AgentHarness(self.client).preview("move up 0.1", mesh["id"], [0], rejected["scene"])
        accepted = self.client.accept()
        self.assertFalse(accepted["scene"]["preview_active"])
        self.assertTrue(accepted["backup"].startswith("AI_EDIT_BACKUP_"))

    def test_imported_glb_becomes_the_edit_session(self):
        glb = self.folder / "trellis-output.glb"
        script = (
            "import bpy; "
            "bpy.ops.object.select_all(action='SELECT'); "
            "bpy.ops.object.delete(use_global=False); "
            "bpy.ops.mesh.primitive_cube_add(); "
            "bpy.context.object.name='Trellis Cube'; "
            f"bpy.ops.export_scene.gltf(filepath={str(glb)!r}, export_format='GLB')"
        )
        subprocess.run(
            [DEFAULT_BLENDER, "--background", "--factory-startup", "--python-expr", script],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        scene = self.client.import_mesh(str(glb))
        self.assertEqual([item["label"] for item in scene["objects"]], ["Trellis Cube"])


if __name__ == "__main__":
    unittest.main()
