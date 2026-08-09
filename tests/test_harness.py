import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import threading
import unittest

from glyph_harness.harness import AgentHarness
from glyph_harness.trellis_client import TrellisClient


SCENE = {
    "name": "Test Scene",
    "unit_system": "METRIC",
    "objects": [
        {
            "id": "TestMesh",
            "label": "Test Mesh",
            "vertex_count": 4,
            "edge_count": 4,
            "face_count": 1,
            "polygons": [{"index": 0, "vertices": [0, 1, 2, 3]}],
        }
    ],
}


class FakeBlender:
    def preview(self, object_name, face_indices, plan):
        self.call = (object_name, face_indices, plan)
        return {"scene": {**SCENE, "preview_active": True}, "transaction": {"id": "test"}}


class HarnessTests(unittest.TestCase):
    def test_harness_builds_exact_selection_context_and_typed_plan(self):
        blender = FakeBlender()
        result = AgentHarness(blender).preview(
            "inflate 0.05 and smooth 0.3", "TestMesh", [0], SCENE
        )
        self.assertEqual(result["context"]["objects"][0]["selection"]["vertices"], [0, 1, 2, 3])
        self.assertEqual([item["type"] for item in result["plan"]["operations"]], ["inflate", "smooth"])
        self.assertEqual(blender.call[0:2], ("TestMesh", [0]))
        self.assertEqual(len(result["steps"]), 4)


class _TrellisHandler(BaseHTTPRequestHandler):
    last_payload = None

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        type(self).last_payload = json.loads(self.rfile.read(length))
        body = json.dumps({"job_id": "job-123", "status": "queued"}).encode()
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        pass


class TrellisClientTests(unittest.TestCase):
    def test_submits_versioned_job_to_endpoint(self):
        server = HTTPServer(("127.0.0.1", 0), _TrellisHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = TrellisClient(f"http://127.0.0.1:{server.server_port}").submit(
                "generate a cuff", {"objects": []}, ["reference.png"]
            )
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(result["job_id"], "job-123")
        self.assertEqual(_TrellisHandler.last_payload["version"], 1)
        self.assertEqual(_TrellisHandler.last_payload["reference_images"], ["reference.png"])


if __name__ == "__main__":
    unittest.main()
