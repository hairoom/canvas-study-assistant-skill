#!/usr/bin/env python3
"""Install and register the Canvas Study Assistant MCP server for Codex."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from canvas_study.runtime import app_dir

DEFAULT_SERVER_NAME = "canvas-study-assistant"


def environment_python(environment: Path) -> Path:
    directory = "Scripts" if os.name == "nt" else "bin"
    filename = "python.exe" if os.name == "nt" else "python"
    return environment / directory / filename


def find_codex(explicit: str | None = None) -> str:
    candidates = [
        explicit,
        os.environ.get("CODEX_CLI_PATH"),
        shutil.which("codex"),
        "/Applications/ChatGPT.app/Contents/Resources/codex",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RuntimeError(
        "Codex CLI was not found. Run this setup from Codex, add 'codex' to PATH, "
        "or pass --codex-bin PATH."
    )


def run(command: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(list(command), text=True, capture_output=True)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Command failed: {detail or 'unknown error'}")
    return result


def current_registration(codex: str, name: str) -> dict[str, Any] | None:
    result = run([codex, "mcp", "get", name, "--json"], check=False)
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Codex returned an unreadable MCP registration") from exc
    return value if isinstance(value, dict) else None


def registration_matches(registration: dict[str, Any] | None, python: Path, server: Path) -> bool:
    if not registration:
        return False
    transport = registration.get("transport", registration)
    return (
        transport.get("type") == "stdio"
        and Path(str(transport.get("command", ""))).resolve() == python.resolve()
        and [str(item) for item in transport.get("args", [])] == [str(server.resolve())]
    )


def register(codex: str, name: str, python: Path, server: Path) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise RuntimeError("MCP server name may contain only letters, numbers, '.', '_' and '-'")
    existing = current_registration(codex, name)
    if registration_matches(existing, python, server):
        return "unchanged"
    if existing:
        run([codex, "mcp", "remove", name])
    run([codex, "mcp", "add", name, "--", str(python.resolve()), str(server.resolve())])
    saved = current_registration(codex, name)
    if not registration_matches(saved, python, server):
        raise RuntimeError("Codex did not retain the expected MCP registration")
    return "updated" if existing else "created"


def install_dependencies(python: Path, requirements: Path) -> None:
    run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)])


def verify_server(python: Path, root: Path) -> None:
    source = (
        "import sys; "
        f"sys.path.insert(0, {str(root)!r}); "
        "from mcp_server.server import mcp; "
        "assert mcp is not None"
    )
    run([str(python), "-c", source])


def setup(
    *,
    root: Path = ROOT,
    environment: Path | None = None,
    codex_bin: str | None = None,
    server_name: str = DEFAULT_SERVER_NAME,
) -> dict[str, Any]:
    root = root.resolve()
    environment = (environment or app_dir() / "mcp-venv").expanduser().resolve()
    python = environment_python(environment)
    requirements = root / "requirements-mcp.txt"
    server = root / "mcp_server" / "server.py"
    if not requirements.is_file() or not server.is_file():
        raise RuntimeError("Run setup_mcp.py from a complete Canvas Study Assistant installation")

    if not python.is_file():
        environment.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    install_dependencies(python, requirements)
    verify_server(python, root)

    codex = find_codex(codex_bin)
    action = register(codex, server_name, python, server)
    return {
        "status": "ok",
        "server_name": server_name,
        "registration": action,
        "python": str(python),
        "server": str(server),
        "restart_required": True,
        "next_step": "Restart Codex, then connect your Canvas account in a new conversation.",
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Install MCP dependencies in an isolated environment and register the server with Codex."
    )
    value.add_argument("--codex-bin", help="Path to the Codex CLI when it cannot be discovered automatically")
    value.add_argument("--server-name", default=DEFAULT_SERVER_NAME)
    value.add_argument("--venv", type=Path, help="Override the persistent MCP virtual-environment directory")
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(setup(environment=args.venv, codex_bin=args.codex_bin, server_name=args.server_name), indent=2))
        return 0
    except (OSError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
