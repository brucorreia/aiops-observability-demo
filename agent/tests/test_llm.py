from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.github import collect_commit_evidence, sha_from_image
from scoring.llm import _extract_json, interpret


class GitHubCollectorTests(unittest.TestCase):
    def test_sha_from_image(self):
        self.assertEqual(sha_from_image("ghcr.io/brucorreia/aiops-demo-app:ee21f58"), "ee21f58")
        self.assertIsNone(sha_from_image("aiops-demo-app:dev"))
        self.assertIsNone(sha_from_image("aiops-demo-app:latest"))
        self.assertIsNone(sha_from_image(None))

    def test_collect_commits_and_compare(self):
        commits = [
            {
                "sha": "aaaaaaaaaaaaaaaa",
                "html_url": "https://github.com/example/repo/commit/aaaaaaaaaaaaaaaa",
                "commit": {"message": "fix: crash on startup\n\nbody", "author": {"name": "Ada", "date": "2026-09-14T12:00:00Z"}},
            }
        ]
        compare = {
            "ahead_by": 1,
            "behind_by": 0,
            "total_commits": 1,
            "commits": commits,
            "files": [{"filename": "apps/demo-app/app.py", "status": "modified", "additions": 3, "deletions": 1}],
        }

        def fake_get_json(url, **_kwargs):
            if "/compare/" in url:
                return compare
            return commits

        with patch("collectors.github.get_json", side_effect=fake_get_json):
            evidence = collect_commit_evidence("brucorreia/aiops-observability-demo", "aaaaaaa", "bbbbbbb")
        self.assertEqual(evidence["status"], "ok")
        self.assertEqual(evidence["recent_commits"][0]["sha"], "aaaaaaa")
        self.assertEqual(evidence["recent_commits"][0]["message"], "fix: crash on startup")
        self.assertTrue(evidence["touches_demo_app"])
        self.assertFalse(evidence["touches_agent"])
        self.assertEqual(evidence["compare"]["files"][0]["filename"], "apps/demo-app/app.py")


class LlmScoringTests(unittest.TestCase):
    def test_skips_without_api_key(self):
        result = interpret({"recommendations": []}, {"openai_api_key": ""})
        self.assertFalse(result["used"])
        self.assertIn("no API key", result["notes"][0])

    def test_extracts_fenced_json(self):
        parsed = _extract_json('```json\n{"scores": {"rollback": 80}}\n```')
        self.assertEqual(parsed["scores"]["rollback"], 80)

    def test_primary_scores_from_model_json(self):
        payload = {
            "summary": "Crash depois do commit na demo-app",
            "scores": {"rollback": 70, "vertical_scale": 5, "horizontal_scale": 0, "investigate": 20, "none": 5},
            "reasons": {"rollback": ["commit aaaaaaa alterou apps/demo-app/app.py", "log startup_failed"]},
            "cited_commits": ["aaaaaaa"],
            "cited_logs": ["startup_failed"],
            "notes": [],
        }
        raw = json.dumps({"choices": [{"message": {"content": json.dumps(payload)}}]}).encode()
        settings = {
            "openai_api_key": "sk-test",
            "openai_base_url": "https://api.openai.com/v1",
            "openai_model": "gpt-4o-mini",
            "llm_timeout_seconds": 5,
        }
        analysis = {
            "incident_type": "crashloop",
            "recommendations": [{"action": "rollback", "recommendation_score": 90}],
            "evidence": {
                "log_entries": [{"event": "startup_failed", "message": "simulated crash", "level": "error"}],
                "recent_commits": [{"sha": "aaaaaaa", "message": "fix: crash on startup"}],
                "commit_compare": {"files": [{"filename": "apps/demo-app/app.py"}]},
                "code_changed_in_demo_app": True,
            },
        }
        with patch("scoring.llm.request", return_value=(200, raw)):
            result = interpret(analysis, settings)
        self.assertTrue(result["used"])
        self.assertEqual(result["source"], "primary")
        self.assertEqual(sum(result["scores"].values()), 100)
        self.assertGreater(result["scores"]["rollback"], result["scores"]["investigate"])
        self.assertIn("startup_failed", result["reasons"]["rollback"][1])


if __name__ == "__main__":
    unittest.main()
