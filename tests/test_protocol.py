import json
import unittest

from blender_ai_editor.planner import local_plan
from blender_ai_editor.protocol import EditPlan, edit_plan_schema


class ProtocolTests(unittest.TestCase):
    def test_local_plan_round_trip(self):
        plan = local_plan("scale it 1.2 and move up 0.3", {}, [])
        restored = EditPlan.from_json(plan.to_json())
        self.assertEqual([op.type for op in restored.operations], ["scale", "translate"])
        self.assertEqual(restored.operations[0].amount, 1.2)
        self.assertEqual(restored.operations[1].vector, [0.0, 0.0, 0.3])

    def test_rejects_arbitrary_operation(self):
        data = {
            "summary": "unsafe",
            "operations": [{"type": "run_python", "target": "selection"}],
            "assumptions": [],
            "validation": [],
        }
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            EditPlan.from_dict(data)

    def test_rejects_incomplete_typed_operation(self):
        data = {
            "summary": "missing vector",
            "operations": [{"type": "translate", "target": "selection"}],
            "assumptions": [],
            "validation": [],
        }
        with self.assertRaisesRegex(ValueError, "requires a vector"):
            EditPlan.from_dict(data)

    def test_schema_is_json_serializable(self):
        serialized = json.dumps(edit_plan_schema())
        self.assertIn("protected_geometry", serialized)


if __name__ == "__main__":
    unittest.main()
