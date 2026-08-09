from pathlib import Path
import tempfile
import unittest

from glyph_harness.project_store import ProjectStore


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


if __name__ == "__main__":
    unittest.main()
