import tempfile
import unittest
from pathlib import Path

from canvas_study.application import CanvasApplication


class FakeAPI:
    def __init__(self):
        self.submitted = False
        self.requests = []

    def get(self, path, fields=None):
        if path.endswith("/submissions/self"):
            return {
                "workflow_state": "submitted" if self.submitted else "unsubmitted",
                "attempt": 1 if self.submitted else 0,
                "late": False,
                "missing": not self.submitted,
                "attachments": [{"id": 91}] if self.submitted else [],
            }, {}
        raise AssertionError(path)

    def request(self, method, path, fields=None):
        self.requests.append((method, path, fields))
        if path.endswith("/submissions/self/files"):
            return {"upload_url": "https://uploads.example.edu", "upload_params": {}}, {}, path
        if path.endswith("/submissions"):
            self.submitted = True
            return {}, {}, path
        raise AssertionError(path)


class FakeBackend:
    def __init__(self, root: Path):
        self.root = root
        self.cfg = {"timezone": "Asia/Singapore", "canvas_url": "https://canvas.example.edu"}
        self.api = FakeAPI()
        self.course_data = [
            {
                "id": 7, "name": "Statistics", "course_code": "STAT101",
                "workflow_state": "available",
                "enrollments": [{"type": "student"}],
            },
            {
                "id": 8, "name": "Teacher Workspace", "course_code": "ADMIN",
                "workflow_state": "available",
                "enrollments": [{"type": "teacher"}],
            },
        ]
        self.assignment_data = [
            {
                "id": 11, "name": "Regression report", "due_at": "2099-01-01T00:00:00Z",
                "description": "<p>Write a report.</p>",
                "submission": {"workflow_state": "unsubmitted"},
            },
            {
                "id": 12, "name": "Completed quiz", "due_at": "2099-01-02T00:00:00Z",
                "description": "Done", "submission": {"workflow_state": "graded"},
            },
        ]

    def app_dir(self): return self.root
    def config(self): return self.cfg
    def token_for(self, cfg): return "not-a-real-token"
    def client(self): return self.api, self.cfg
    def courses(self, api, cfg, refresh=False): return self.course_data
    def course(self, api, cfg, query, refresh=False): return self.course_data[0]
    def assignments(self, api, cfg, course_id, refresh=False): return self.assignment_data
    def assignment(self, api, cfg, course_id, query, refresh=False): return self.assignment_data[0]
    def clean_html(self, value): return "Write a report."
    def upload_form(self, url, fields, path):
        return {"id": 91, "display_name": path.name}


class CanvasApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.backend = FakeBackend(Path(self.temp.name))
        self.application = CanvasApplication(self.backend)

    def tearDown(self): self.temp.cleanup()

    def test_course_tools_enforce_student_scope(self):
        result = self.application.list_courses()
        self.assertEqual([course["id"] for course in result["courses"]], [7])

    def test_assignment_tool_returns_context_and_filters_completed(self):
        result = self.application.list_assignments("Statistics", pending_only=True)
        self.assertEqual(result["course"]["id"], 7)
        self.assertEqual(result["timezone"], "Asia/Singapore")
        self.assertEqual([item["id"] for item in result["assignments"]], [11])
        self.assertEqual(result["assignments"][0]["description"], "Write a report.")

    def test_schedule_rejects_unbounded_windows(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 365"):
            self.application.schedule(1000)

    def test_upload_and_submission_require_separate_previews(self):
        path = Path(self.temp.name) / "report.pdf"
        path.write_bytes(b"draft")

        upload_preview = self.application.preview_upload("Statistics", "Regression report", str(path))
        self.assertFalse(upload_preview["uploaded"])
        self.assertEqual(self.backend.api.requests, [])

        uploaded = self.application.upload_draft(
            "Statistics", "Regression report", str(path),
            upload_preview["confirmation_required"],
        )
        self.assertTrue(uploaded["uploaded"])
        self.assertFalse(uploaded["submitted"])

        submission_preview = self.application.preview_submission(
            "Statistics", "Regression report", str(uploaded["file_id"]),
        )
        self.assertEqual(submission_preview["current_submission"]["workflow_state"], "unsubmitted")

        submitted = self.application.submit_assignment(
            "Statistics", "Regression report", str(uploaded["file_id"]),
            submission_preview["confirmation_required"],
        )
        self.assertTrue(submitted["submitted"])
        self.assertEqual(submitted["observed"]["workflow_state"], "submitted")


if __name__ == "__main__": unittest.main()
