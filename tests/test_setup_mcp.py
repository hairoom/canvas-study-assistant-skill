import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import setup_mcp


class SetupMCPTests(unittest.TestCase):
    def test_registration_matches_stdio_command_and_argument(self):
        python = Path("/tmp/example environment/bin/python")
        server = Path("/tmp/example skill/mcp_server/server.py")
        value = {
            "transport": {
                "type": "stdio",
                "command": str(python.resolve()),
                "args": [str(server.resolve())],
            }
        }
        self.assertTrue(setup_mcp.registration_matches(value, python, server))
        value["transport"]["args"] = ["different.py"]
        self.assertFalse(setup_mcp.registration_matches(value, python, server))

    def test_register_is_idempotent(self):
        python = Path("/tmp/environment/bin/python")
        server = Path("/tmp/skill/server.py")
        existing = {
            "transport": {
                "type": "stdio",
                "command": str(python.resolve()),
                "args": [str(server.resolve())],
            }
        }
        with patch.object(setup_mcp, "current_registration", return_value=existing), patch.object(
            setup_mcp, "run"
        ) as mocked_run:
            self.assertEqual(setup_mcp.register("codex", "canvas-study-assistant", python, server), "unchanged")
            mocked_run.assert_not_called()

    def test_register_replaces_stale_registration_without_a_shell(self):
        python = Path("/tmp/example environment/bin/python")
        server = Path("/tmp/example skill/server.py")
        stale = {"transport": {"type": "stdio", "command": "old-python", "args": ["old-server"]}}
        fresh = {
            "transport": {
                "type": "stdio",
                "command": str(python.resolve()),
                "args": [str(server.resolve())],
            }
        }
        with patch.object(setup_mcp, "current_registration", side_effect=[stale, fresh]), patch.object(
            setup_mcp, "run"
        ) as mocked_run:
            result = setup_mcp.register("codex", "canvas-study-assistant", python, server)
        self.assertEqual(result, "updated")
        self.assertEqual(mocked_run.call_args_list[0].args[0], ["codex", "mcp", "remove", "canvas-study-assistant"])
        self.assertEqual(
            mocked_run.call_args_list[1].args[0],
            ["codex", "mcp", "add", "canvas-study-assistant", "--", str(python.resolve()), str(server.resolve())],
        )

    def test_current_registration_reads_json(self):
        completed = setup_mcp.subprocess.CompletedProcess([], 0, json.dumps({"transport": {"type": "stdio"}}), "")
        with patch.object(setup_mcp, "run", return_value=completed):
            self.assertEqual(setup_mcp.current_registration("codex", "canvas"), {"transport": {"type": "stdio"}})


if __name__ == "__main__":
    unittest.main()
