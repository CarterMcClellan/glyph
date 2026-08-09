from pathlib import Path
import tempfile
import unittest

from glyph_harness.project_store import ProjectStore
from glyph_harness.server import GlyphService


class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = ProjectStore(self.root)
        self.image = self.root / "source.png"
        self.image.write_bytes(b"not-a-real-png-but-stable-test-data")

    def tearDown(self):
        self.temporary.cleanup()

    def test_lock_is_forward_only_and_requires_confirmation(self):
        state = self.store.import_source(str(self.image), "A clean product shot")
        self.assertEqual(state["stage"], "IMAGINE")
        with self.assertRaises(ValueError):
            self.store.lock_source(False)
        state = self.store.lock_source(True)
        self.assertEqual(state["stage"], "MESH")
        self.assertEqual(state["source"]["locked"]["sha256"], state["source"]["versions"][0]["sha256"])
        with self.assertRaises(RuntimeError):
            self.store.import_source(str(self.image))
        with self.assertRaises(RuntimeError):
            self.store.set_active_source("source-v1")

    def test_fork_creates_editable_lineage_from_locked_source(self):
        self.store.import_source(str(self.image), "A clean product shot")
        locked = self.store.lock_source(True)
        fork = self.store.fork_project()
        self.assertEqual(fork["stage"], "IMAGINE")
        self.assertEqual(fork["parent_project_id"], locked["project_id"])
        self.assertIsNone(fork["source"]["locked"])
        self.assertEqual(len(fork["source"]["versions"]), 1)

    def test_edit_requires_approved_mesh_after_lock(self):
        mesh = self.root / "result.glb"
        mesh.write_bytes(b"test-glb")
        with self.assertRaises(RuntimeError):
            self.store.approve_mesh(str(mesh))
        self.store.import_source(str(self.image))
        self.store.lock_source(True)
        state = self.store.approve_mesh(str(mesh))
        self.assertEqual(state["stage"], "EDIT")
        self.assertTrue(Path(state["mesh"]["approved"]["path"]).is_file())

    def test_bundled_preset_origin_is_preserved(self):
        state = self.store.import_source(
            str(self.image),
            "Built-in source: Voxel Apprentice",
            "preset:voxel-apprentice",
        )
        self.assertEqual(state["source"]["versions"][0]["origin"], "preset:voxel-apprentice")

    def test_source_bytes_can_cross_a_remote_api_boundary(self):
        state = self.store.import_source_bytes(
            b"uploaded-image-bytes",
            "wizard.webp",
            "A remote upload",
            "upload",
        )
        source = state["source"]["versions"][0]
        self.assertEqual(Path(source["path"]).suffix, ".webp")
        self.assertEqual(source["origin"], "upload")
        self.assertEqual(source["prompt"], "A remote upload")

    def test_service_imports_bundled_source_preset(self):
        project_root = Path(__file__).resolve().parents[1]
        service = GlyphService(project_root, self.root / "service-workspace")
        state = service.import_source_preset("arcane-mage")
        source = state["source"]["versions"][0]
        self.assertEqual(source["origin"], "preset:arcane-mage")
        self.assertTrue(Path(source["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
