import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "canvas_cli",
    ROOT / "scripts" / "canvas_cli.py",
)
canvas_cli = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(canvas_cli)


class CanvasCliTests(unittest.TestCase):
    def test_normalize_base_url(self):
        self.assertEqual(
            canvas_cli.normalize_url("canvas.example.edu/courses/123"),
            "https://canvas.example.edu",
        )

    def test_init_defaults_to_system_storage(self):
        args = canvas_cli.make_parser().parse_args(
            ["init", "--base-url", "https://canvas.example.edu"]
        )
        self.assertEqual(args.storage, "system")

    def test_assignment_file_match_is_marked_fuzzy(self):
        assignment = {
            "name": "Assignment 2 Customer Analysis",
            "description": "Use the customer dataset and submit a report.",
        }
        file_info = {"display_name": "Assignment 2 Customer Dataset.xlsx"}
        score, reasons = canvas_cli.match_score(assignment, file_info)
        self.assertGreaterEqual(score, 30)
        self.assertIn("matching assignment number", reasons)

    def test_redirect_handler_strips_cross_origin_authorization(self):
        from urllib.request import Request

        handler = canvas_cli.SafeRedirectHandler()
        original = Request(
            "https://canvas.example.edu/api/v1/files/1",
            headers={"Authorization": "Bearer example"},
        )
        redirected = handler.redirect_request(
            original,
            None,
            302,
            "Found",
            {},
            "https://files.example-cdn.edu/file.pdf",
        )
        self.assertIsNotNone(redirected)
        self.assertIsNone(redirected.get_header("Authorization"))


if __name__ == "__main__":
    unittest.main()
