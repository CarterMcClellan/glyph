import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blender_ai_editor.planner import codex_auth_status, resolve_codex_executable
from glyph_harness.server import GlyphService


class ChatGPTAuthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.codex = self.root / "codex"
        self.codex.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"--version\" ]; then echo 'codex-test'; exit 0; fi\n"
            "if [ \"$1\" = \"login\" ] && [ \"$2\" = \"status\" ]; then echo 'Logged in using ChatGPT'; exit 0; fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        self.codex.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def test_resolves_healthy_codex_and_requires_chatgpt_auth(self):
        with patch("blender_ai_editor.planner._codex_candidates", return_value=[str(self.codex)]):
            self.assertEqual(resolve_codex_executable(), str(self.codex))
            status = codex_auth_status()
        self.assertTrue(status["available"])
        self.assertTrue(status["signed_in"])
        self.assertEqual(status["method"], "chatgpt")

    def test_legacy_openai_key_is_removed_from_settings(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        (workspace / "settings.json").write_text(
            json.dumps({"openai_api_key": "legacy-secret", "trellis_endpoint": "https://trellis.test"}),
            encoding="utf-8",
        )
        service = GlyphService(self.root, workspace)
        self.assertNotIn("openai_api_key", service.public_settings())
        service.save_settings({"model": "test-model"})
        saved = json.loads((workspace / "settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("openai_api_key", saved)


if __name__ == "__main__":
    unittest.main()
