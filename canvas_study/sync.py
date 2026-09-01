from __future__ import annotations

from typing import Any

from .index import ResourceIndex


CAPABILITY_KIND = {
    "files": "file", "pages": "page", "assignments": "assignment",
    "discussions": "discussion", "announcements": "announcement",
    "classic_quizzes": "quiz", "new_quizzes": "quiz", "external_tools": "external_tool",
}


def item_key(course_id, kind, identifier): return f"{kind}:course-{course_id}:{identifier}"


def title_of(raw):
    return raw.get("title") or raw.get("name") or raw.get("display_name") or raw.get("filename") or "Untitled"


def ingest_course_report(index: ResourceIndex, report: dict[str, Any]) -> dict[str, Any]:
    """Persist only structure and metadata from an inspect-course report."""
    course = report["course"]; cid = str(course["id"]); index.upsert_course(course); counts = {}
    syllabus = report.get("syllabus") or {}
    index.set_sync_state(cid, "syllabus", syllabus.get("status", "unknown"), int(bool(syllabus.get("text"))))
    if syllabus.get("status") == "available" and (syllabus.get("text") or syllabus.get("links")):
        skey = item_key(cid, "syllabus", "main")
        index.upsert_resource({"resource_key": skey, "course_id": cid, "kind": "syllabus", "canvas_id": "main",
                               "title": "Syllabus", "status": "available", "source": "course"})
        for link in syllabus.get("links", []):
            target = item_key(cid, link["kind"], link["id"])
            index.upsert_resource({"resource_key": target, "course_id": cid, "kind": link["kind"],
                                   "canvas_id": link["id"], "lookup_id": link["id"],
                                   "title": f"{link['kind']} {link['id']}", "status": "available",
                                   "source": "syllabus_links"})
            index.add_relation(skey, target, "links_to")
    for cap_name, cap in (report.get("capabilities") or {}).items():
        status = cap.get("status", "unknown"); data = cap.get("data") or []
        if status != "available":
            index.set_sync_state(cid, cap_name, status, detail=cap.get("detail")); continue
        if cap_name == "modules":
            item_count = 0
            for module in data:
                mid = module.get("id"); mkey = item_key(cid, "module", mid)
                index.upsert_resource({"resource_key": mkey, "course_id": cid, "kind": "module", "canvas_id": mid,
                    "title": module.get("name"), "status": module.get("state") or "available", "source": "modules",
                    "metadata": {k: module.get(k) for k in ("position", "unlock_at", "prerequisite_module_ids", "require_sequential_progress")}})
                for item in module.get("items", []):
                    kind = item.get("kind") or "unknown"; rid = item.get("content_id") or item.get("id")
                    rkey = item_key(cid, kind, rid)
                    index.upsert_resource({"resource_key": rkey, "course_id": cid, "kind": kind, "canvas_id": item.get("content_id"),
                        "lookup_id": item.get("content_id"), "title": item.get("title"),
                        "status": "locked" if item.get("locked") else ("available" if item.get("supported") else "unsupported"),
                        "source": "module_items", "metadata": {"raw_type": item.get("raw_type"), "module_item_id": item.get("id")}})
                    index.add_relation(mkey, rkey, "contains", item.get("position")); item_count += 1
            counts[cap_name] = len(data); index.set_sync_state(cid, cap_name, status, item_count)
            continue
        kind = CAPABILITY_KIND.get(cap_name)
        if kind:
            for raw in data:
                rid = raw.get("id") or raw.get("url") or raw.get("html_url") or title_of(raw)
                rkey = item_key(cid, kind, rid)
                index.upsert_resource({"resource_key": rkey, "course_id": cid, "kind": kind,
                    "canvas_id": raw.get("id"), "lookup_id": raw.get("url") or raw.get("id"), "title": title_of(raw),
                    "status": "locked" if raw.get("locked_for_user") else "available", "source": cap_name,
                    "updated_at": raw.get("updated_at"),
                    "metadata": {k: raw.get(k) for k in ("content-type", "size", "due_at", "unlock_at", "lock_at", "published")}})
                for attachment in raw.get("attachments") or []:
                    fid = attachment.get("id")
                    if fid is None: continue
                    fkey = item_key(cid, "file", fid)
                    index.upsert_resource({"resource_key": fkey, "course_id": cid, "kind": "file", "canvas_id": fid,
                                           "lookup_id": fid, "title": title_of(attachment), "status": "available",
                                           "source": f"{cap_name}_attachments",
                                           "metadata": {k: attachment.get(k) for k in ("content-type", "size", "updated_at")}})
                    index.add_relation(rkey, fkey, "attachment")
        counts[cap_name] = len(data) if isinstance(data, list) else 1
        index.set_sync_state(cid, cap_name, status, counts[cap_name])
    index.commit()
    return {"course_id": cid, "resources_by_capability": counts}


def sync_all(api, cfg, courses, discover_course, index_path):
    index = ResourceIndex(index_path); summaries, failures = [], []
    try:
        for course in courses:
            try: summaries.append(ingest_course_report(index, discover_course(api, cfg, course, True)))
            except Exception as exc:
                failures.append({"course_id": course.get("id"), "error": str(exc)[:300]})
        status = index.status()
        return {"completed": not failures, "indexed": summaries, "failures": failures, **status}
    finally: index.close()
