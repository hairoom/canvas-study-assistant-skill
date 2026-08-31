import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "canvas_cli.py"
SPEC = importlib.util.spec_from_file_location("canvas_cli", SCRIPT)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class FakeCanvas:
    def __init__(self):
        self.calls = []

    def pages(self, path, fields=None, limit=2000):
        self.calls.append(("pages", path, fields))
        if path == "/api/v1/courses/7/modules":
            return [{"id": 10, "name": "Week 1", "position": 1, "items": None}]
        if path == "/api/v1/courses/7/modules/10/items":
            return [
                {"id": 11, "type": "File", "content_id": 99, "title": "notes.pdf"},
                {"id": 12, "type": "FutureType", "content_id": 100, "title": "future"},
            ]
        if path == "/api/v1/courses/7/files":
            return []
        raise AssertionError(path)

    def get(self, path, fields=None):
        self.calls.append(("get", path, fields))
        if path == "/api/v1/files/99":
            return {"id": 99, "display_name": "notes.pdf", "size": 42}, {}
        raise AssertionError(path)


class ResourceDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ["CANVAS_ASSISTANT_HOME"] = self.temp.name
        self.cfg = {"cache_mode": "realtime"}

    def tearDown(self):
        os.environ.pop("CANVAS_ASSISTANT_HOME", None)
        self.temp.cleanup()

    def test_module_items_fall_back_when_not_inlined(self):
        api = FakeCanvas()
        modules = cli.normalized_modules(api, self.cfg, 7, True)
        self.assertEqual(modules[0]["items"][0]["kind"], "file")
        self.assertEqual(modules[0]["items"][1]["kind"], "unknown")
        self.assertFalse(modules[0]["items"][1]["supported"])
        self.assertTrue(any(call[1].endswith("/10/items") for call in api.calls))

    def test_module_only_file_is_merged_into_files(self):
        api = FakeCanvas()
        files = cli.course_files(api, self.cfg, 7, True)
        self.assertEqual([f["id"] for f in files], [99])
        self.assertEqual(files[0]["module_contexts"][0]["module_name"], "Week 1")

    def test_capability_keeps_permission_failure_distinct(self):
        def denied():
            raise cli.CanvasAPIError(403, "permission_denied", "not allowed")
        result = cli.capability(denied)
        self.assertEqual(result["status"], "permission_denied")
        self.assertEqual(result["http_status"], 403)

    def test_api_output_removes_credential_fields(self):
        value = {"id": 1, "token": "secret", "nested": {"access_token": "secret", "ok": True}}
        self.assertEqual(cli.scrub_api_output(value), {"id": 1, "nested": {"ok": True}})


if __name__ == "__main__":
    unittest.main()
