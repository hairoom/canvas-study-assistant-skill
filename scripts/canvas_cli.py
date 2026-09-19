#!/usr/bin/env python3
"""Developer and recovery CLI for Canvas Study Assistant.

The implementation lives in ``canvas_study.runtime`` so the CLI and MCP server
share one runtime instead of making MCP invoke shell commands.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Re-export the established CLI API for compatibility with existing tests and
# local integrations that import this script directly.
from canvas_study.runtime import *  # noqa: F401,F403,E402
from canvas_study.runtime import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
