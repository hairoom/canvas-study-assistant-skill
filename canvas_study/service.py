from __future__ import annotations

from pathlib import Path

from .index import ResourceIndex
from .registry import REGISTRY


class CanvasStudyService:
    def __init__(self, index_path: str | Path): self.index_path = Path(index_path)

    def find_resource(self, course_id, query, kinds=None, limit=10):
        inferred = REGISTRY.kinds_for_query(query)
        selected = kinds or inferred or None
        source_specs = [REGISTRY.get(k) for k in selected] if selected else REGISTRY.all()
        index = ResourceIndex(self.index_path)
        try:
            return {"query": query, "inferred_kinds": inferred, "candidate_sources": sorted({s for spec in source_specs for s in spec.candidate_sources}),
                    "results": index.search(course_id, query, selected, limit)}
        finally: index.close()

    def course_tree(self, course_id):
        index = ResourceIndex(self.index_path)
        try: return {"course_id": str(course_id), "modules": index.course_tree(course_id)}
        finally: index.close()

    def sync_status(self):
        index = ResourceIndex(self.index_path)
        try: return index.status()
        finally: index.close()

    def registry(self):
        return [{"kind": spec.kind, "aliases": spec.aliases, "candidate_sources": spec.candidate_sources,
                 "list_endpoint": spec.list_endpoint.path if spec.list_endpoint else None,
                 "detail_endpoint": spec.detail_endpoint.path if spec.detail_endpoint else None}
                for spec in REGISTRY.all()]
