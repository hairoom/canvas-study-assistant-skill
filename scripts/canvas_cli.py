#!/usr/bin/env python3
"""Dependency-free Canvas student CLI with safe credentials and cached reads."""

from __future__ import annotations

import argparse, getpass, hashlib, html, json, mimetypes, os, re, shutil, subprocess, sys, tempfile, time, uuid
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

APP = "canvas-study-assistant"
SERVICE = APP
TTLS = {
    "standard": {"courses": 1800, "assignments": 300, "files": 900, "modules": 900},
    "realtime": {"courses": 0, "assignments": 0, "files": 0, "modules": 0},
    "low-request": {"courses": 14400, "assignments": 1800, "files": 7200, "modules": 7200},
}


class CanvasAPIError(RuntimeError):
    """Canvas failure with a stable category suitable for capability reports."""

    def __init__(self, status: int, category: str, detail: str):
        self.status, self.category, self.detail = status, category, detail
        super().__init__(f"Canvas HTTP {status} ({category}): {detail}")


class SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urlparse(req.full_url).netloc != urlparse(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


def app_dir() -> Path:
    override = os.environ.get("CANVAS_ASSISTANT_HOME")
    if override: path = Path(override).expanduser()
    elif os.name == "nt": path = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / APP
    elif sys.platform == "darwin": root = Path.home() / "Library/Application Support"
    else: root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    if not override and os.name != "nt": path = root / APP
    path.mkdir(parents=True, exist_ok=True); return path


def config_path() -> Path: return app_dir() / "config.json"
def cache_dir() -> Path: path = app_dir() / "cache"; path.mkdir(parents=True, exist_ok=True); return path
def session_path() -> Path:
    ident = hashlib.sha256(str(Path.home()).encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"{APP}-{ident}.json"


def read_json(path: Path, default=None):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError): return default


def secure_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    if os.name != "nt": os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def output(value: Any) -> None: print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
def config() -> dict[str, Any]: return read_json(config_path(), {})


def normalize_url(value: str) -> str:
    value = value.strip()
    if not value.startswith(("https://", "http://")): value = "https://" + value
    parsed = urlparse(value)
    if not parsed.netloc: raise RuntimeError("Invalid Canvas base URL")
    return f"{parsed.scheme}://{parsed.netloc}"


def keyring():
    try:
        import keyring as module  # type: ignore
        if getattr(module.get_keyring(), "priority", 0) <= 0: raise RuntimeError("No secure keyring backend")
        return module
    except ImportError as exc:
        raise RuntimeError("Persistent storage needs Python package 'keyring'; use session storage or install keyring") from exc


def credential_account(base: str, user_id: str) -> str:
    return f"{base}|{user_id}"


def mac_vault_set(account: str, token: str) -> None:
    result = subprocess.run(["security", "add-generic-password", "-U", "-a", account, "-s", SERVICE, "-w"], input=token + "\n", text=True, capture_output=True)
    if result.returncode != 0: raise RuntimeError("macOS Keychain could not save the credential")


def mac_vault_get(account: str) -> str | None:
    result = subprocess.run(["security", "find-generic-password", "-a", account, "-s", SERVICE, "-w"], text=True, capture_output=True)
    if result.returncode == 44: return None
    if result.returncode != 0: raise RuntimeError("macOS Keychain could not read the credential")
    return result.stdout.rstrip("\r\n")


def mac_vault_delete(account: str) -> None:
    result = subprocess.run(["security", "delete-generic-password", "-a", account, "-s", SERVICE], text=True, capture_output=True)
    if result.returncode not in (0, 44): raise RuntimeError("macOS Keychain could not delete the credential")


def windows_credential_api():
    import ctypes
    from ctypes import wintypes
    class FILETIME(ctypes.Structure): _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]
    class CREDENTIALW(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                    ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]; api.CredWriteW.restype = wintypes.BOOL
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]; api.CredReadW.restype = wintypes.BOOL
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]; api.CredDeleteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    return ctypes, api, CREDENTIALW


def windows_vault_set(account: str, token: str) -> None:
    ctypes, api, Credential = windows_credential_api(); blob = token.encode("utf-16-le")
    buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob); cred = Credential()
    cred.Type, cred.TargetName, cred.CredentialBlobSize = 1, f"{SERVICE}:{account}", len(blob)
    cred.CredentialBlob, cred.Persist, cred.UserName = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)), 2, account
    if not api.CredWriteW(ctypes.byref(cred), 0): raise RuntimeError(f"Windows Credential Manager error: {ctypes.get_last_error()}")


def windows_vault_get(account: str) -> str | None:
    ctypes, api, Credential = windows_credential_api(); pointer = ctypes.POINTER(Credential)()
    if not api.CredReadW(f"{SERVICE}:{account}", 1, 0, ctypes.byref(pointer)):
        if ctypes.get_last_error() == 1168: return None
        raise RuntimeError(f"Windows Credential Manager error: {ctypes.get_last_error()}")
    try: return ctypes.string_at(pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize).decode("utf-16-le")
    finally: api.CredFree(pointer)


def windows_vault_delete(account: str) -> None:
    ctypes, api, _ = windows_credential_api()
    if not api.CredDeleteW(f"{SERVICE}:{account}", 1, 0) and ctypes.get_last_error() != 1168:
        raise RuntimeError(f"Windows Credential Manager error: {ctypes.get_last_error()}")


def vault_set(account: str, token: str) -> None:
    if sys.platform == "darwin": mac_vault_set(account, token)
    elif os.name == "nt": windows_vault_set(account, token)
    else: keyring().set_password(SERVICE, account, token)


def vault_get(account: str) -> str | None:
    if sys.platform == "darwin": return mac_vault_get(account)
    if os.name == "nt": return windows_vault_get(account)
    return keyring().get_password(SERVICE, account)


def vault_delete(account: str) -> None:
    if sys.platform == "darwin": mac_vault_delete(account)
    elif os.name == "nt": windows_vault_delete(account)
    else:
        try: keyring().delete_password(SERVICE, account)
        except Exception: pass


def save_token(token: str, mode: str, base: str, user_id: str) -> None:
    if mode in {"system", "keyring"}: vault_set(credential_account(base, user_id), token)
    else: secure_write(session_path(), {"token": token, "expires_at": time.time() + 28800})


def token_for(cfg: dict[str, Any]) -> str:
    if cfg.get("credential_mode") in {"system", "keyring"}:
        value = vault_get(credential_account(cfg["canvas_url"], cfg["canvas_user_id"]))
        if not value: raise RuntimeError("Saved token unavailable; run init or update-token")
        return value
    data = read_json(session_path(), {})
    if not data or data.get("expires_at", 0) <= time.time():
        session_path().unlink(missing_ok=True); raise RuntimeError("Session token expired; run init or update-token")
    return data["token"]


def next_url(link: str, base: str) -> str | None:
    for part in link.split(","):
        match = re.search(r'<([^>]+)>;\s*rel="?next"?', part)
        if match: return urljoin(base, match.group(1))
    return None


class Canvas:
    def __init__(self, base: str, token: str): self.base, self.token, self.opener = base.rstrip("/"), token, build_opener(SafeRedirectHandler())

    def request(self, method: str, path: str, fields: list[tuple[str, str]] | None = None,
                data: bytes | None = None, headers: dict[str, str] | None = None):
        url = path if path.startswith(("http://", "https://")) else urljoin(self.base + "/", path.lstrip("/"))
        same_origin = urlparse(url).netloc == urlparse(self.base).netloc
        hdr = {"Accept": "application/json+canvas-string-ids", **(headers or {})}
        if same_origin:
            hdr["Authorization"] = f"Bearer {self.token}"
        if method == "GET" and fields: url += ("&" if "?" in url else "?") + urlencode(fields)
        elif fields is not None and data is None:
            data = urlencode(fields).encode(); hdr["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            with self.opener.open(Request(url, data=data, headers=hdr, method=method), timeout=90) as res:
                raw = res.read(); content_type = res.headers.get("Content-Type", "")
                payload = json.loads(raw) if raw and "json" in content_type else raw
                return payload, dict(res.headers), res.geturl()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:800]
            categories = {401: "unauthorized", 403: "permission_denied", 404: "hidden_or_missing", 429: "rate_limited"}
            category = categories.get(exc.code, "http_error")
            detail = "Canvas token is invalid, expired, or revoked; run update-token" if exc.code == 401 else body
            raise CanvasAPIError(exc.code, category, detail) from exc
        except URLError as exc: raise RuntimeError(f"Canvas connection failed: {exc.reason}") from exc

    def get(self, path: str, fields=None): return self.request("GET", path, fields)[:2]
    def pages(self, path: str, fields=None, limit=2000):
        items, url, params = [], path, fields
        while url and len(items) < limit:
            payload, headers, final = self.request("GET", url, params)
            if not isinstance(payload, list): raise RuntimeError("Expected a Canvas list response")
            items.extend(payload); url, params = next_url(headers.get("Link", ""), final), None
        return items[:limit]


def client():
    cfg = config()
    if not cfg: raise RuntimeError("Canvas is not configured; run init")
    return Canvas(cfg["canvas_url"], token_for(cfg)), cfg


def cached(cfg, category: str, key: str, producer, refresh=False):
    path = cache_dir() / f"{category}-{hashlib.sha256(key.encode()).hexdigest()[:16]}.json"
    old, ttl = read_json(path, {}), TTLS[cfg.get("cache_mode", "standard")][category]
    if not refresh and ttl and old.get("stored_at", 0) + ttl > time.time(): return old["data"]
    data = producer(); secure_write(path, {"stored_at": time.time(), "data": data}); return data


def capability(producer):
    """Run an optional student-readable endpoint without hiding why it failed."""
    try:
        return {"status": "available", "data": producer()}
    except CanvasAPIError as exc:
        return {"status": exc.category, "http_status": exc.status, "detail": exc.detail}
    except RuntimeError as exc:
        return {"status": "unsupported_or_unavailable", "detail": str(exc)}


def validate(base: str, token: str):
    api = Canvas(base, token); profile, _ = api.get("/api/v1/users/self/profile")
    courses = api.pages("/api/v1/courses", [("enrollment_state", "active"), ("include[]", "enrollments"), ("per_page", "100")])
    students = [c for c in courses if any(e.get("type") == "student" or e.get("role") == "StudentEnrollment" for e in c.get("enrollments", []))]
    if not students: raise RuntimeError("No active student enrollment found; this skill supports students only")
    return profile, students


def courses(api, cfg, refresh=False):
    return cached(cfg, "courses", "active", lambda: api.pages("/api/v1/courses", [("enrollment_state", "active"), ("include[]", "enrollments"), ("per_page", "100")]), refresh)


def resolve(items, query, kind):
    fields = ("name", "course_code") if kind == "course" else ("name",)
    exact = [x for x in items if str(x.get("id")) == query or any(str(x.get(f, "")).casefold() == query.casefold() for f in fields)]
    if len(exact) == 1: return exact[0]
    scored = sorted(((SequenceMatcher(None, query.casefold(), " ".join(str(x.get(f, "")) for f in fields).casefold()).ratio(), x) for x in items), reverse=True, key=lambda pair: pair[0])
    candidates = [x for score, x in scored[:5] if score >= .45]
    if len(candidates) != 1:
        raise RuntimeError(f"Ambiguous {kind}; candidates=" + json.dumps([{"id": x.get("id"), "name": x.get("name")} for x in candidates], ensure_ascii=False))
    return candidates[0]


def course(api, cfg, query, refresh=False): return resolve(courses(api, cfg, refresh), query, "course")
def assignments(api, cfg, cid, refresh=False):
    return cached(cfg, "assignments", str(cid), lambda: api.pages(f"/api/v1/courses/{cid}/assignments", [("include[]", "submission"), ("include[]", "overrides"), ("all_dates", "true"), ("per_page", "100")]), refresh)
def assignment(api, cfg, cid, query, refresh=False): return resolve(assignments(api, cfg, cid, refresh), query, "assignment")
def clean_html(value): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


MODULE_KIND = {
    "File": "file", "Page": "page", "Assignment": "assignment", "Quiz": "quiz",
    "Discussion": "discussion", "ExternalUrl": "external_url", "ExternalTool": "external_tool",
    "SubHeader": "subheader",
}


def normalize_module_item(item, module):
    raw_type = item.get("type") or "Unknown"
    details = item.get("content_details") or {}
    return {
        "kind": MODULE_KIND.get(raw_type, "unknown"), "raw_type": raw_type,
        "id": item.get("id"), "content_id": item.get("content_id"),
        "module_id": module.get("id"), "module_name": module.get("name"),
        "position": item.get("position"), "title": item.get("title"),
        "html_url": item.get("html_url"), "external_url": item.get("external_url"),
        "new_tab": item.get("new_tab"), "completion_requirement": item.get("completion_requirement"),
        "locked": bool(details.get("locked_for_user")), "lock_explanation": details.get("lock_explanation"),
        "supported": raw_type in MODULE_KIND,
    }


def course_modules(api, cfg, cid, refresh=False):
    def load():
        modules = api.pages(f"/api/v1/courses/{cid}/modules", [
            ("include[]", "items"), ("include[]", "content_details"), ("per_page", "100")])
        for module in modules:
            if not isinstance(module.get("items"), list):
                module["items"] = api.pages(
                    f"/api/v1/courses/{cid}/modules/{module['id']}/items",
                    [("include[]", "content_details"), ("per_page", "100")])
        return modules
    return cached(cfg, "modules", str(cid), load, refresh)


def normalized_modules(api, cfg, cid, refresh=False):
    result = []
    for module in course_modules(api, cfg, cid, refresh):
        result.append({
            "id": module.get("id"), "name": module.get("name"), "position": module.get("position"),
            "state": module.get("state"), "unlock_at": module.get("unlock_at"),
            "prerequisite_module_ids": module.get("prerequisite_module_ids") or [],
            "require_sequential_progress": module.get("require_sequential_progress"),
            "items": [normalize_module_item(item, module) for item in module.get("items", [])],
        })
    return result


def discover_course(api, cfg, c, refresh=False):
    cid = c["id"]
    detail = capability(lambda: api.get(f"/api/v1/courses/{cid}", [("include[]", "syllabus_body")])[0])
    specs = {
        "tabs": lambda: api.pages(f"/api/v1/courses/{cid}/tabs", [("per_page", "100")]),
        "modules": lambda: normalized_modules(api, cfg, cid, refresh),
        "files": lambda: course_files(api, cfg, cid, refresh),
        "pages": lambda: api.pages(f"/api/v1/courses/{cid}/pages", [("per_page", "100")]),
        "assignments": lambda: assignments(api, cfg, cid, refresh),
        "discussions": lambda: api.pages(f"/api/v1/courses/{cid}/discussion_topics", [("per_page", "100")]),
        "announcements": lambda: api.pages("/api/v1/announcements", [("context_codes[]", f"course_{cid}"), ("per_page", "100")]),
        "classic_quizzes": lambda: api.pages(f"/api/v1/courses/{cid}/quizzes", [("per_page", "100")]),
        "new_quizzes": lambda: api.pages(f"/api/quiz/v1/courses/{cid}/quizzes", [("per_page", "100")]),
        "external_tools": lambda: api.pages(f"/api/v1/courses/{cid}/external_tools/visible_course_nav_tools", [("per_page", "100")]),
    }
    found = {name: capability(loader) for name, loader in specs.items()}
    course_data = detail.get("data") if detail.get("status") == "available" else c
    return {
        "course": {"id": cid, "name": c.get("name"), "course_code": c.get("course_code")},
        "syllabus": {"status": detail.get("status"), "text": clean_html((course_data or {}).get("syllabus_body"))},
        "capabilities": found,
    }


def words(value):
    stop = {"the", "and", "for", "assignment", "file", "document", "week"}
    return {w for w in re.sub(r"[^\w]+", " ", value.casefold()).split() if len(w) > 1 and w not in stop}


def match_score(a, f):
    title, desc, name = str(a.get("name", "")), clean_html(a.get("description")), str(f.get("display_name") or f.get("filename") or "")
    tw, fw = words(title), words(name); overlap = len(tw & fw) / max(1, len(tw | fw)); score, reasons = int(overlap * 75), []
    if overlap: reasons.append("matching title words")
    if set(re.findall(r"\b\d+\b", title)) & set(re.findall(r"\b\d+\b", name)): score += 15; reasons.append("matching assignment number")
    if words(desc) & fw: score += min(10, len(words(desc) & fw) * 2); reasons.append("description keywords")
    return min(89, score), reasons


def cmd_init(args):
    base, tok = normalize_url(args.base_url), getpass.getpass("Canvas Access Token (hidden): ").strip()
    profile, student_courses = validate(base, tok); save_token(tok, args.storage, base, str(profile["id"]))
    cfg = {"canvas_url": base, "canvas_user_id": str(profile["id"]), "canvas_user_name": profile.get("name"), "timezone": profile.get("time_zone") or "UTC", "credential_mode": args.storage, "token_expires_at": args.expires, "cache_mode": "standard"}
    secure_write(config_path(), cfg); output({"connected": True, "user": cfg["canvas_user_name"], "user_id": cfg["canvas_user_id"], "timezone": cfg["timezone"], "student_courses": len(student_courses), "credential_mode": args.storage, "cache_mode": "standard"})


def cmd_update(args):
    cfg = config(); tok = getpass.getpass("New Canvas Access Token (hidden): ").strip(); profile, _ = validate(cfg["canvas_url"], tok)
    changed = str(profile["id"]) != str(cfg["canvas_user_id"])
    if changed and not args.confirm_account_switch: raise RuntimeError(f"New token belongs to {profile.get('name')} ({profile.get('id')}); account-switch confirmation required")
    old_account = credential_account(cfg["canvas_url"], cfg["canvas_user_id"])
    save_token(tok, cfg.get("credential_mode", "session"), cfg["canvas_url"], str(profile["id"]))
    if changed and cfg.get("credential_mode") in {"system", "keyring"}: vault_delete(old_account)
    cfg.update({"canvas_user_id": str(profile["id"]), "canvas_user_name": profile.get("name"), "timezone": profile.get("time_zone") or "UTC", "token_expires_at": args.expires}); secure_write(config_path(), cfg)
    shutil.rmtree(cache_dir(), ignore_errors=True); output({"updated": True, "account_switched": changed, "user": profile.get("name")})


def cmd_storage(args):
    cfg = config()
    if not cfg: raise RuntimeError("Canvas is not configured")
    old_mode, tok = cfg.get("credential_mode", "session"), token_for(cfg)
    if args.mode == old_mode: return output({"credential_mode": old_mode, "changed": False})
    save_token(tok, args.mode, cfg["canvas_url"], cfg["canvas_user_id"])
    if old_mode in {"system", "keyring"}:
        vault_delete(credential_account(cfg["canvas_url"], cfg["canvas_user_id"]))
    else: session_path().unlink(missing_ok=True)
    cfg["credential_mode"] = args.mode; secure_write(config_path(), cfg)
    output({"credential_mode": args.mode, "changed": True})


def cmd_status(args):
    cfg = config()
    if not cfg: return output({"configured": False})
    try: token_for(cfg); available = True
    except RuntimeError: available = False
    public = {k: cfg.get(k) for k in ("canvas_url", "canvas_user_id", "canvas_user_name", "timezone", "credential_mode", "token_expires_at", "cache_mode")}
    output({"configured": True, "credential_available": available, **public})


def cmd_courses(args):
    api, cfg = client(); output([{"id": c.get("id"), "name": c.get("name"), "course_code": c.get("course_code"), "workflow_state": c.get("workflow_state")} for c in courses(api, cfg, args.refresh)])


def cmd_assignments(args):
    api, cfg = client(); c = course(api, cfg, args.course, args.refresh); items = assignments(api, cfg, c["id"], args.refresh)
    if args.pending: items = [a for a in items if (a.get("submission") or {}).get("workflow_state") not in {"submitted", "graded"}]
    items.sort(key=lambda a: (a.get("due_at") is None, a.get("due_at") or ""))
    output({"course": {"id": c["id"], "name": c.get("name")}, "timezone": cfg.get("timezone"), "assignments": [{"id": a.get("id"), "name": a.get("name"), "due_at": a.get("due_at"), "unlock_at": a.get("unlock_at"), "lock_at": a.get("lock_at"), "points": a.get("points_possible"), "submission_types": a.get("submission_types"), "description": clean_html(a.get("description")), "submission": a.get("submission")} for a in items]})


def cmd_schedule(args):
    api, cfg = client(); cutoff, result = datetime.now(timezone.utc) + timedelta(days=args.days), []
    for c in courses(api, cfg, True):
        for a in assignments(api, cfg, c["id"], True):
            due, state = a.get("due_at"), (a.get("submission") or {}).get("workflow_state")
            if not due or state in {"submitted", "graded"}: continue
            try: when = datetime.fromisoformat(due.replace("Z", "+00:00"))
            except ValueError: continue
            if when <= cutoff: result.append({"course": c.get("name"), "course_id": c.get("id"), "assignment": a.get("name"), "assignment_id": a.get("id"), "due_at": due, "points": a.get("points_possible")})
    output({"timezone": cfg.get("timezone"), "days": args.days, "pending": sorted(result, key=lambda x: x["due_at"])})


def course_files(api, cfg, cid, refresh=False):
    def load():
        files = api.pages(f"/api/v1/courses/{cid}/files", [("per_page", "100")])
        by_id = {str(f.get("id")): f for f in files}
        try: modules = normalized_modules(api, cfg, cid, refresh)
        except CanvasAPIError: modules = []
        for module in modules:
            for item in module["items"]:
                if item["kind"] != "file" or item.get("content_id") is None: continue
                fid = str(item["content_id"])
                if fid not in by_id:
                    try: by_id[fid] = api.get(f"/api/v1/files/{fid}")[0]
                    except CanvasAPIError: continue
                by_id[fid].setdefault("module_contexts", []).append({
                    "module_id": module["id"], "module_name": module["name"], "module_item_id": item["id"]})
        return list(by_id.values())
    return cached(cfg, "files", str(cid), load, refresh)


def cmd_files(args):
    api, cfg = client(); c = course(api, cfg, args.course, args.refresh); files = course_files(api, cfg, c["id"], args.refresh)
    output({"course": {"id": c["id"], "name": c.get("name")}, "files": [{"id": f.get("id"), "name": f.get("display_name") or f.get("filename"), "content_type": f.get("content-type"), "size": f.get("size"), "updated_at": f.get("updated_at"), "module_contexts": f.get("module_contexts", [])} for f in files]})


def cmd_modules(args):
    api, cfg = client(); c = course(api, cfg, args.course, args.refresh)
    output({"course": {"id": c["id"], "name": c.get("name")}, "modules": normalized_modules(api, cfg, c["id"], args.refresh)})


def cmd_inspect(args):
    api, cfg = client(); c = course(api, cfg, args.course, args.refresh); report = discover_course(api, cfg, c, args.refresh)
    for name, cap in report["capabilities"].items():
        if cap.get("status") != "available": continue
        data = cap.get("data") or []
        if name == "modules":
            cap["count"] = len(data); cap["item_count"] = sum(len(m["items"]) for m in data)
        else: cap["count"] = len(data) if isinstance(data, list) else 1
        if not args.full: cap.pop("data", None)
    output(report)


def cmd_doctor(args):
    api, cfg = client(); c = course(api, cfg, args.course, True); report = discover_course(api, cfg, c, True)
    checks = {"syllabus": {"status": report["syllabus"]["status"], "present": bool(report["syllabus"].get("text"))}}
    for name, cap in report["capabilities"].items():
        check = {k: cap.get(k) for k in ("status", "http_status", "detail") if cap.get(k) is not None}
        if cap.get("status") == "available":
            data = cap.get("data") or []; check["count"] = len(data) if isinstance(data, list) else 1
            if name == "modules": check["item_count"] = sum(len(m["items"]) for m in data)
        checks[name] = check
    output({"course": report["course"], "checks": checks})


def scrub_api_output(value):
    if isinstance(value, list): return [scrub_api_output(v) for v in value]
    if not isinstance(value, dict): return value
    blocked = {"access_token", "authorization", "token"}
    return {k: scrub_api_output(v) for k, v in value.items() if k.casefold() not in blocked}


def cmd_api_get(args):
    api, _ = client(); path = args.path.strip()
    if not path.startswith("/api/") or path.startswith("//") or urlparse(path).netloc:
        raise RuntimeError("api-get only accepts same-origin paths beginning with /api/")
    if re.search(r"(?:access_token|authorization|token)=", path, re.I):
        raise RuntimeError("Credentials are not allowed in api-get paths")
    fields = []
    for pair in args.param:
        if "=" not in pair: raise RuntimeError("--param must use KEY=VALUE")
        key, value = pair.split("=", 1)
        if key.casefold() in {"access_token", "authorization", "token"}: raise RuntimeError("Credential parameters are forbidden")
        fields.append((key, value))
    data = api.pages(path, fields, limit=args.limit) if args.paginate else api.get(path, fields)[0]
    output(scrub_api_output(data))


def cmd_match(args):
    api, cfg = client(); c = course(api, cfg, args.course, True); a = assignment(api, cfg, c["id"], args.assignment, True); found = []
    for f in course_files(api, cfg, c["id"], True):
        score, reasons = match_score(a, f)
        if score >= 30: found.append({"file_id": f.get("id"), "name": f.get("display_name") or f.get("filename"), "confidence": score, "reasons": reasons, "fuzzy_match": True})
    output({"course": c.get("name"), "assignment": a.get("name"), "notice": "Canvas did not explicitly associate these candidates; results are fuzzy matches", "candidates": sorted(found, key=lambda x: x["confidence"], reverse=True)[:10]})


def safe_name(value): return (re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip(" .") or "download")[:180]


def cmd_download(args):
    api, _ = client(); f, _ = api.get(f"/api/v1/files/{args.file_id}")
    raw, _, _ = api.request("GET", f["url"])
    if not isinstance(raw, bytes): raise RuntimeError("Unexpected file response")
    folder = Path(args.output).expanduser().resolve(); folder.mkdir(parents=True, exist_ok=True); target = folder / safe_name(f.get("display_name") or f.get("filename") or str(args.file_id))
    if target.exists(): target = target.with_name(f"{target.stem}-{args.file_id}{target.suffix}")
    target.write_bytes(raw); output({"downloaded": True, "file_id": f.get("id"), "name": target.name, "content_type": f.get("content-type"), "bytes": len(raw), "path": str(target)})


def upload_form(url: str, fields: dict[str, Any], path: Path):
    boundary = "----Canvas" + uuid.uuid4().hex; chunks = []
    for name, value in fields.items(): chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    chunks += [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode(), path.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()]
    with build_opener(SafeRedirectHandler()).open(Request(url, data=b"".join(chunks), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST"), timeout=180) as res: return json.loads(res.read())


def cmd_upload(args):
    api, cfg = client(); c = course(api, cfg, args.course, True); a = assignment(api, cfg, c["id"], args.assignment, True); path = Path(args.file).expanduser().resolve(); phrase = f"UPLOAD:{c['id']}:{a['id']}"
    if not path.is_file(): raise RuntimeError("Local file not found")
    if args.confirm != phrase: return output({"uploaded": False, "confirmation_required": phrase, "course": c.get("name"), "assignment": a.get("name"), "file": str(path), "bytes": path.stat().st_size})
    init, _, _ = api.request("POST", f"/api/v1/courses/{c['id']}/assignments/{a['id']}/submissions/self/files", [("name", path.name), ("size", str(path.stat().st_size)), ("content_type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")])
    uploaded = upload_form(init["upload_url"], init.get("upload_params", {}), path); output({"uploaded": True, "submitted": False, "file_id": uploaded.get("id"), "filename": uploaded.get("display_name") or uploaded.get("filename")})


def submission(api, cid, aid): return api.get(f"/api/v1/courses/{cid}/assignments/{aid}/submissions/self")[0]


def cmd_preview(args):
    api, cfg = client(); c = course(api, cfg, args.course, True); a = assignment(api, cfg, c["id"], args.assignment, True); current = submission(api, c["id"], a["id"]); phrase = f"SUBMIT:{c['id']}:{a['id']}:{args.file_id}"
    output({"course": c.get("name"), "course_id": c["id"], "assignment": a.get("name"), "assignment_id": a["id"], "file_id": args.file_id, "due_at": a.get("due_at"), "unlock_at": a.get("unlock_at"), "lock_at": a.get("lock_at"), "timezone": cfg.get("timezone"), "current_submission": {k: current.get(k) for k in ("workflow_state", "submitted_at", "attempt", "late", "missing")}, "confirmation_required": phrase})


def cmd_submit(args):
    api, cfg = client(); c = course(api, cfg, args.course, True); a = assignment(api, cfg, c["id"], args.assignment, True); expected = f"SUBMIT:{c['id']}:{a['id']}:{args.file_id}"
    if args.confirm != expected: raise RuntimeError("Exact final confirmation required; run submission-preview")
    before = submission(api, c["id"], a["id"]); api.request("POST", f"/api/v1/courses/{c['id']}/assignments/{a['id']}/submissions", [("submission[submission_type]", "online_upload"), ("submission[file_ids][]", str(args.file_id))]); after = submission(api, c["id"], a["id"])
    output({"submitted": True, "previous_attempt": before.get("attempt"), "observed": {k: after.get(k) for k in ("workflow_state", "submitted_at", "attempt", "late", "missing", "attachments")}})


def cmd_cache(args):
    if args.mode == "clear": shutil.rmtree(cache_dir(), ignore_errors=True); return output({"cache_cleared": True})
    cfg = config(); cfg["cache_mode"] = args.mode; secure_write(config_path(), cfg); output({"cache_mode": args.mode})


def cmd_disconnect(args):
    cfg = config()
    if cfg.get("credential_mode") in {"system", "keyring"}:
        try: vault_delete(credential_account(cfg["canvas_url"], cfg["canvas_user_id"]))
        except Exception: pass
    session_path().unlink(missing_ok=True); config_path().unlink(missing_ok=True); shutil.rmtree(cache_dir(), ignore_errors=True); output({"disconnected": True, "downloaded_files_removed": False})


def make_parser():
    root = argparse.ArgumentParser(description="Canvas student assistant"); sub = root.add_subparsers(dest="command", required=True)
    p=sub.add_parser("init"); p.add_argument("--base-url", required=True); p.add_argument("--expires"); p.add_argument("--storage", choices=["session","system"], default="system"); p.set_defaults(fn=cmd_init)
    p=sub.add_parser("update-token"); p.add_argument("--expires"); p.add_argument("--confirm-account-switch", action="store_true"); p.set_defaults(fn=cmd_update)
    p=sub.add_parser("storage"); p.add_argument("mode", choices=["session","system"]); p.set_defaults(fn=cmd_storage)
    p=sub.add_parser("status"); p.set_defaults(fn=cmd_status); p=sub.add_parser("disconnect"); p.set_defaults(fn=cmd_disconnect)
    p=sub.add_parser("courses"); p.add_argument("--refresh", action="store_true"); p.set_defaults(fn=cmd_courses)
    p=sub.add_parser("assignments"); p.add_argument("--course", required=True); p.add_argument("--pending", action="store_true"); p.add_argument("--refresh", action="store_true"); p.set_defaults(fn=cmd_assignments)
    p=sub.add_parser("schedule"); p.add_argument("--days", type=int, default=7); p.set_defaults(fn=cmd_schedule)
    p=sub.add_parser("files"); p.add_argument("--course", required=True); p.add_argument("--refresh", action="store_true"); p.set_defaults(fn=cmd_files)
    p=sub.add_parser("modules"); p.add_argument("--course", required=True); p.add_argument("--refresh", action="store_true"); p.set_defaults(fn=cmd_modules)
    p=sub.add_parser("inspect-course"); p.add_argument("--course", required=True); p.add_argument("--refresh", action="store_true"); p.add_argument("--full", action="store_true"); p.set_defaults(fn=cmd_inspect)
    p=sub.add_parser("doctor"); p.add_argument("--course", required=True); p.set_defaults(fn=cmd_doctor)
    p=sub.add_parser("api-get"); p.add_argument("--path", required=True); p.add_argument("--param", action="append", default=[]); p.add_argument("--paginate", action="store_true"); p.add_argument("--limit", type=int, default=500); p.set_defaults(fn=cmd_api_get)
    p=sub.add_parser("match-files"); p.add_argument("--course", required=True); p.add_argument("--assignment", required=True); p.set_defaults(fn=cmd_match)
    p=sub.add_parser("download"); p.add_argument("--file-id", required=True); p.add_argument("--output", required=True); p.set_defaults(fn=cmd_download)
    p=sub.add_parser("upload-draft"); p.add_argument("--course", required=True); p.add_argument("--assignment", required=True); p.add_argument("--file", required=True); p.add_argument("--confirm"); p.set_defaults(fn=cmd_upload)
    p=sub.add_parser("submission-preview"); p.add_argument("--course", required=True); p.add_argument("--assignment", required=True); p.add_argument("--file-id", required=True); p.set_defaults(fn=cmd_preview)
    p=sub.add_parser("submit"); p.add_argument("--course", required=True); p.add_argument("--assignment", required=True); p.add_argument("--file-id", required=True); p.add_argument("--confirm", required=True); p.set_defaults(fn=cmd_submit)
    p=sub.add_parser("cache"); p.add_argument("mode", choices=["standard","realtime","low-request","clear"]); p.set_defaults(fn=cmd_cache)
    return root


def main():
    try: args = make_parser().parse_args(); args.fn(args); return 0
    except (RuntimeError, OSError, KeyError, ValueError) as exc: output({"error": str(exc)}); return 1


if __name__ == "__main__": raise SystemExit(main())
