from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any


def normalize(value: str | None) -> str:
    return " ".join(re.findall(r"[\w]+", (value or "").casefold(), re.UNICODE))


class ResourceIndex:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try: self.db = sqlite3.connect(self.path)
        except sqlite3.Error as exc: raise RuntimeError(f"Cannot open Canvas resource index at {self.path}: {exc}") from exc
        self.db.row_factory = sqlite3.Row
        self._schema()

    def _schema(self):
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS courses (
          course_id TEXT PRIMARY KEY, name TEXT, course_code TEXT, synced_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS resources (
          resource_key TEXT PRIMARY KEY, course_id TEXT NOT NULL, kind TEXT NOT NULL,
          canvas_id TEXT, lookup_id TEXT, title TEXT, normalized_title TEXT NOT NULL,
          status TEXT NOT NULL, source TEXT, updated_at TEXT, metadata_json TEXT NOT NULL,
          detail_fetched_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_resources_course_kind ON resources(course_id, kind);
        CREATE INDEX IF NOT EXISTS idx_resources_title ON resources(course_id, normalized_title);
        CREATE TABLE IF NOT EXISTS relations (
          source_key TEXT NOT NULL, target_key TEXT NOT NULL, relation_type TEXT NOT NULL,
          position INTEGER, metadata_json TEXT NOT NULL,
          PRIMARY KEY(source_key, target_key, relation_type)
        );
        CREATE TABLE IF NOT EXISTS sync_state (
          course_id TEXT NOT NULL, resource_kind TEXT NOT NULL, status TEXT NOT NULL,
          count INTEGER, detail TEXT, checked_at REAL NOT NULL,
          PRIMARY KEY(course_id, resource_kind)
        );
        """)
        self.db.commit()

    def close(self): self.db.close()

    def upsert_course(self, course: dict[str, Any]):
        self.db.execute("""INSERT INTO courses(course_id,name,course_code,synced_at) VALUES(?,?,?,?)
          ON CONFLICT(course_id) DO UPDATE SET name=excluded.name,course_code=excluded.course_code,synced_at=excluded.synced_at""",
          (str(course["id"]), course.get("name"), course.get("course_code"), time.time()))

    def upsert_resource(self, resource: dict[str, Any]):
        safe = dict(resource.get("metadata") or {})
        for key in list(safe):
            if key.casefold() in {"url", "download_url", "access_token", "authorization", "token", "body", "description", "message"}:
                safe.pop(key, None)
        values = (
            resource["resource_key"], str(resource["course_id"]), resource["kind"],
            str(resource.get("canvas_id")) if resource.get("canvas_id") is not None else None,
            str(resource.get("lookup_id")) if resource.get("lookup_id") is not None else None,
            resource.get("title"), normalize(resource.get("title")), resource.get("status", "available"),
            resource.get("source"), resource.get("updated_at"), json.dumps(safe, ensure_ascii=False),
        )
        self.db.execute("""INSERT INTO resources(resource_key,course_id,kind,canvas_id,lookup_id,title,normalized_title,status,source,updated_at,metadata_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(resource_key) DO UPDATE SET
          title=excluded.title,normalized_title=excluded.normalized_title,status=excluded.status,source=excluded.source,
          updated_at=excluded.updated_at,metadata_json=excluded.metadata_json""", values)

    def add_relation(self, source, target, relation_type, position=None, metadata=None):
        self.db.execute("""INSERT OR REPLACE INTO relations(source_key,target_key,relation_type,position,metadata_json)
          VALUES(?,?,?,?,?)""", (source, target, relation_type, position, json.dumps(metadata or {}, ensure_ascii=False)))

    def set_sync_state(self, course_id, kind, status, count=None, detail=None):
        self.db.execute("""INSERT OR REPLACE INTO sync_state(course_id,resource_kind,status,count,detail,checked_at)
          VALUES(?,?,?,?,?,?)""", (str(course_id), kind, status, count, detail, time.time()))

    def commit(self): self.db.commit()

    def search(self, course_id, query, kinds=None, limit=10):
        query_norm = normalize(query); tokens = set(query_norm.split())
        sql = "SELECT * FROM resources WHERE course_id=?"
        args: list[Any] = [str(course_id)]
        if kinds:
            sql += " AND kind IN (%s)" % ",".join("?" for _ in kinds); args.extend(kinds)
        rows = self.db.execute(sql, args).fetchall(); ranked = []
        for row in rows:
            title = row["normalized_title"] or ""; title_tokens = set(title.split())
            score, reasons = 0, []
            if query_norm and title == query_norm: score += 100; reasons.append("exact title")
            elif query_norm and query_norm in title: score += 70; reasons.append("title phrase")
            overlap = len(tokens & title_tokens)
            if overlap: score += round(45 * overlap / max(1, len(tokens))); reasons.append(f"{overlap} query terms")
            context = self._context(row["resource_key"])
            context_norm = normalize(" ".join(x["title"] or "" for x in context))
            context_overlap = len(tokens & set(context_norm.split()))
            if context_overlap: score += round(30 * context_overlap / max(1, len(tokens))); reasons.append("module/context match")
            if score: ranked.append((min(score, 100), dict(row), reasons, context))
        ranked.sort(key=lambda item: (-item[0], item[1]["title"] or ""))
        return [{"resource": {k: row[k] for k in ("resource_key","course_id","kind","canvas_id","lookup_id","title","status","source")},
                 "confidence": score, "reasons": reasons,
                 "context": [{"resource_key": x["resource_key"], "kind": x["kind"], "title": x["title"]} for x in context]}
                for score, row, reasons, context in ranked[:limit]]

    def _context(self, key):
        return self.db.execute("""SELECT r.resource_key,r.kind,r.title FROM relations x JOIN resources r
          ON r.resource_key=x.source_key WHERE x.target_key=? UNION SELECT r.resource_key,r.kind,r.title FROM relations x
          JOIN resources r ON r.resource_key=x.target_key WHERE x.source_key=?""", (key, key)).fetchall()

    def course_tree(self, course_id):
        modules = list(self.db.execute("SELECT * FROM resources WHERE course_id=? AND kind='module'", (str(course_id),)).fetchall())
        modules.sort(key=lambda row: (json.loads(row["metadata_json"]).get("position") is None,
                                     json.loads(row["metadata_json"]).get("position") or 0))
        result = []
        for module in modules:
            children = self.db.execute("""SELECT r.resource_key,r.kind,r.title,r.status,x.position FROM relations x
              JOIN resources r ON r.resource_key=x.target_key WHERE x.source_key=? ORDER BY x.position""", (module["resource_key"],)).fetchall()
            result.append({"resource_key": module["resource_key"], "title": module["title"], "children": [dict(x) for x in children]})
        return result

    def status(self):
        courses = self.db.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        resources = self.db.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        states = [dict(row) for row in self.db.execute("SELECT * FROM sync_state ORDER BY course_id,resource_kind")]
        return {"courses": courses, "resources": resources, "states": states}
