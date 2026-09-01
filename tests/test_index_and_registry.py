import tempfile
import unittest
from pathlib import Path

from canvas_study.index import ResourceIndex
from canvas_study.registry import REGISTRY
from canvas_study.service import CanvasStudyService
from canvas_study.sync import ingest_course_report


REPORT = {
    "course": {"id": 7, "name": "Statistics", "course_code": "STAT101"},
    "syllabus": {"status": "available", "text": "Week 3 regression resources",
                 "links": [{"kind": "file", "id": "101", "path": "/courses/7/files/101"}]},
    "capabilities": {
        "modules": {"status": "available", "data": [{
            "id": 10, "name": "Week 3 Regression", "position": 3, "state": "unlocked",
            "items": [{"id": 11, "kind": "file", "raw_type": "File", "content_id": 99,
                       "title": "lecture.pdf", "position": 1, "locked": False, "supported": True}],
        }]},
        "files": {"status": "available", "data": [
            {"id": 99, "display_name": "lecture.pdf", "content-type": "application/pdf", "size": 42,
             "url": "https://signed.example/secret"}
        ]},
        "pages": {"status": "available", "data": []},
        "new_quizzes": {"status": "permission_denied", "http_status": 403, "detail": "denied"},
    },
}


class RegistryAndIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "index.sqlite3"

    def tearDown(self): self.temp.cleanup()

    def test_registry_maps_file_language_to_multiple_sources(self):
        spec = REGISTRY.get("文件")
        self.assertEqual(spec.kind, "file")
        self.assertIn("module_items", spec.candidate_sources)
        self.assertIn("syllabus_links", spec.candidate_sources)

    def test_ingest_and_context_search(self):
        index = ResourceIndex(self.path)
        ingest_course_report(index, REPORT)
        results = index.search(7, "week 3 regression lecture", ["file"], 5)
        index.close()
        self.assertEqual(results[0]["resource"]["canvas_id"], "99")
        self.assertIn("module/context match", results[0]["reasons"])

    def test_signed_url_and_syllabus_body_are_not_indexed(self):
        index = ResourceIndex(self.path)
        ingest_course_report(index, REPORT)
        metadata = " ".join(row[0] for row in index.db.execute("SELECT metadata_json FROM resources"))
        columns = {row[1] for row in index.db.execute("PRAGMA table_info(resources)")}
        index.close()
        self.assertNotIn("signed.example", metadata)
        self.assertNotIn("content_text", columns)

    def test_syllabus_internal_link_becomes_a_relation_without_body_storage(self):
        index = ResourceIndex(self.path); ingest_course_report(index, REPORT)
        relation = index.db.execute("SELECT relation_type FROM relations WHERE source_key=? AND target_key=?",
                                    ("syllabus:course-7:main", "file:course-7:101")).fetchone()
        index.close()
        self.assertEqual(relation[0], "links_to")

    def test_service_returns_registry_sources_and_compact_results(self):
        index = ResourceIndex(self.path); ingest_course_report(index, REPORT); index.close()
        result = CanvasStudyService(self.path).find_resource(7, "find the regression file", None, 5)
        self.assertIn("file", result["inferred_kinds"])
        self.assertIn("course_files", result["candidate_sources"])


if __name__ == "__main__": unittest.main()
