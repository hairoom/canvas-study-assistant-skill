from __future__ import annotations

from .models import EndpointSpec, ResourceSpec


class ResourceRegistry:
    def __init__(self):
        self._specs: dict[str, ResourceSpec] = {}
        self._aliases: dict[str, str] = {}

    def register(self, spec: ResourceSpec) -> None:
        spec.validate()
        if spec.kind in self._specs:
            raise ValueError(f"Duplicate resource kind: {spec.kind}")
        self._specs[spec.kind] = spec
        for alias in spec.aliases:
            key = alias.casefold()
            if key in self._aliases:
                raise ValueError(f"Duplicate resource alias: {alias}")
            self._aliases[key] = spec.kind

    def get(self, kind: str) -> ResourceSpec:
        canonical = self._aliases.get(kind.casefold(), kind)
        if canonical not in self._specs:
            raise KeyError(kind)
        return self._specs[canonical]

    def all(self) -> tuple[ResourceSpec, ...]:
        return tuple(self._specs.values())

    def kinds_for_query(self, text: str) -> list[str]:
        folded = text.casefold()
        matches = []
        for spec in self.all():
            if spec.kind.casefold() in folded or any(alias.casefold() in folded for alias in spec.aliases):
                matches.append(spec.kind)
        return matches


REGISTRY = ResourceRegistry()


def add(kind, aliases, sources, list_path=None, detail_path=None, personal=False):
    REGISTRY.register(ResourceSpec(
        kind=kind, aliases=tuple(aliases), candidate_sources=tuple(sources),
        list_endpoint=EndpointSpec(list_path, True, (("per_page", "100"),)) if list_path else None,
        detail_endpoint=EndpointSpec(detail_path) if detail_path else None,
        contains_personal_data=personal,
    ))


add("module", ("module", "week", "模块", "周次"), ("modules",), "/api/v1/courses/{course_id}/modules")
add("syllabus", ("syllabus", "outline", "教学大纲", "课程大纲"), ("course", "syllabus_links"))
add("file", ("file", "pdf", "document", "lecture", "slides", "notes", "文件", "资料", "讲义", "课件"),
    ("module_items", "course_files", "syllabus_links", "page_links", "assignment_attachments", "discussion_attachments"),
    "/api/v1/courses/{course_id}/files", "/api/v1/files/{resource_id}")
add("page", ("page", "wiki", "页面", "网页"), ("module_items", "pages", "syllabus_links"),
    "/api/v1/courses/{course_id}/pages", "/api/v1/courses/{course_id}/pages/{lookup_id}")
add("assignment", ("assignment", "homework", "作业", "任务"), ("module_items", "assignments", "calendar"),
    "/api/v1/courses/{course_id}/assignments", "/api/v1/courses/{course_id}/assignments/{resource_id}", personal=True)
add("discussion", ("discussion", "forum", "讨论", "论坛"), ("module_items", "discussions", "announcements"),
    "/api/v1/courses/{course_id}/discussion_topics", "/api/v1/courses/{course_id}/discussion_topics/{resource_id}", personal=True)
add("announcement", ("announcement", "notice", "通知", "公告"), ("announcements",), "/api/v1/announcements")
add("quiz", ("quiz", "test", "测验", "考试"), ("module_items", "classic_quizzes", "new_quizzes", "assignments"),
    "/api/v1/courses/{course_id}/quizzes", "/api/v1/courses/{course_id}/quizzes/{resource_id}", personal=True)
add("external_url", ("link", "url", "链接", "外链"), ("module_items", "page_links", "syllabus_links"))
add("external_tool", ("tool", "lti", "工具", "外部工具"), ("module_items", "tabs", "external_tools"))
