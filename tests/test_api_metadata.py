from pathlib import Path
import tempfile
import unittest

from glyph_harness.server import GlyphService


class ApiMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.service = GlyphService(self.root, self.root / "workspace")

    def tearDown(self):
        self.temporary.cleanup()

    def test_trellis_contract_describes_both_job_operations(self):
        contract = self.service.trellis_contract()
        self.assertEqual(contract["version"], 1)
        self.assertIn("image_to_3d", contract["operations"])
        self.assertIn("selection_edit", contract["operations"])
        self.assertEqual(contract["routes"]["create_job"]["path"], "/jobs")

    def test_source_presets_have_stable_ids_and_prompts(self):
        response = self.service.source_presets()
        presets = response["presets"]
        self.assertGreaterEqual(len(presets), 4)
        self.assertEqual(len({preset["id"] for preset in presets}), len(presets))
        self.assertTrue(all(preset["prompt"] for preset in presets))

    def test_public_settings_never_return_trellis_token(self):
        self.service.save_settings({"trellis_api_token": "top-secret"})
        settings = self.service.public_settings()
        self.assertNotIn("trellis_api_token", settings)
        self.assertTrue(settings["trellis_auth_configured"])


if __name__ == "__main__":
    unittest.main()
