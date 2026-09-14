from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import console
from collectors.http import HttpError
from recommendations import store


class ConsoleApiTests(unittest.TestCase):
    def setUp(self) -> None:
        store.STORE.clear()
        store.EVENTS.clear()
        store.LATEST = None
        store.ROLLOUT = None

    def test_mode_files_update_deployed_at(self):
        yaml_text = 'aiops.demo/deployed-at: "1970-01-01T00:00:00Z"\n'
        files = console._mode_files("crashloop", "2026-09-14T19:00:00Z", yaml_text)
        self.assertEqual(files[console.MODE_FILE], "crashloop\n")
        self.assertIn("2026-09-14T19:00:00Z", files[console.APP_YAML])

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            console.start_incident({"github_token": "x", "github_repository": "o/r"}, "nope")

    def test_missing_token_conflict(self):
        with self.assertRaises(HttpError) as ctx:
            console.start_incident(
                {"github_token": "", "github_repository": "o/r"},
                "crashloop",
            )
        self.assertEqual(ctx.exception.status, 409)

    def test_timeline_marks_commit_then_build(self):
        steps = console.build_timeline(
            {"sha": "abc1234", "short_sha": "abc1234", "workflow": {"status": "in_progress"}},
            None,
            "Degraded",
            False,
            False,
        )
        by_id = {item["id"]: item for item in steps}
        self.assertTrue(by_id["commit"]["done"])
        self.assertTrue(by_id["build"]["active"])

    def test_recommendation_view_executable_only_for_llm_actions(self):
        view = console.recommendation_view(
            {
                "id": "1",
                "incident_type": "crashloop",
                "recommended_action": "rollback",
                "scoring_source": "llm",
                "recommendations": [{"action": "rollback", "recommendation_score": 80}],
                "evidence": {},
            }
        )
        self.assertTrue(view["executable"])
        skipped = console.recommendation_view(
            {
                "id": "2",
                "incident_type": "crashloop",
                "recommended_action": "investigate",
                "scoring_source": "llm",
                "recommendations": [],
                "evidence": {},
            }
        )
        self.assertFalse(skipped["executable"])

    def test_static_missing_dir_returns_none(self):
        with patch.object(console, "CONSOLE_DIR", Path("/tmp/missing-console-ui")):
            self.assertIsNone(console.static_file("/"))


if __name__ == "__main__":
    unittest.main()
