from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import analyze_alert


def _settings(**overrides):
    base = {
        "openai_api_key": "",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-4o-mini",
        "weights": {},
        "recent_deployment_window_minutes": 15,
        "automatic_execution_allowed": False,
        "victoriametrics_url": "http://vm",
        "victorialogs_url": "http://logs",
        "demo_namespace": "aiops-demo",
        "github_repository": "brucorreia/aiops-observability-demo",
        "github_api_url": "https://api.github.com",
        "github_token": "",
        "llm_timeout_seconds": 5,
    }
    base.update(overrides)
    return base


def _context():
    return {
        "deployment": "demo-app",
        "recent_deployment": True,
        "minutes_since_deployment": 4,
        "last_termination_reason": "Error",
        "missing_evidence": [],
        "related_log_messages": ["startup_failed"],
        "log_entries": [{"event": "startup_failed", "level": "error", "message": "simulated crash"}],
        "recent_commits": [{"sha": "aaaaaaa", "message": "fix: crash on startup"}],
        "pods_ready": 0,
        "replicas": 1,
        "restarts": 3,
        "affected_pods": 1,
        "http_500_count": 0,
        "external_dependency_errors": False,
        "sustained_memory_growth": None,
        "traffic_growth": False,
        "cpu_saturation": False,
        "memory_usage_ratio": None,
        "previous_revision_healthy": True,
        "failures_started_after_deployment": True,
    }


class PipelineLlmOnlyTests(unittest.TestCase):
    @patch("pipeline.save", side_effect=lambda analysis: analysis)
    @patch("pipeline.enrich")
    @patch("pipeline.interpret")
    def test_live_scores_come_from_llm(self, interpret, enrich, _save):
        enrich.return_value = _context()
        interpret.return_value = {
            "used": True,
            "source": "primary",
            "scores": {
                "rollback": 80,
                "vertical_scale": 5,
                "horizontal_scale": 0,
                "investigate": 10,
                "none": 5,
            },
            "reasons": {"rollback": ["commit aaaaaaa mudou a demo-app"]},
            "summary": "Crash após commit na demo-app",
            "notes": [],
        }
        result = analyze_alert({"alert_name": "ContainerCrashLoopBackOff"}, _settings(openai_api_key="sk-test"))
        self.assertEqual(result["scoring_source"], "llm")
        self.assertEqual(result["recommended_action"], "rollback")
        self.assertEqual(result["recommendations"][0]["recommendation_score"], 80)
        self.assertIn("aaaaaaa", result["recommendations"][0]["reasons"][0])

    @patch("pipeline.save", side_effect=lambda analysis: analysis)
    @patch("pipeline.enrich")
    def test_without_api_key_does_not_use_yaml_weights(self, enrich, _save):
        enrich.return_value = _context()
        result = analyze_alert({"alert_name": "ContainerCrashLoopBackOff"}, _settings())
        self.assertEqual(result["scoring_source"], "llm_unavailable")
        self.assertEqual(result["recommended_action"], "investigate")
        scores = {item["action"]: item["recommendation_score"] for item in result["recommendations"]}
        self.assertGreater(scores["investigate"], scores["rollback"])
        self.assertEqual(scores["rollback"], 0)
        self.assertEqual(scores["vertical_scale"], 0)
        self.assertEqual(scores["horizontal_scale"], 0)

    @patch("pipeline.save", side_effect=lambda analysis: analysis)
    @patch("pipeline.enrich")
    def test_score_is_printed_to_stdout(self, enrich, _save):
        enrich.return_value = _context()
        from io import StringIO
        from contextlib import redirect_stdout

        buf = StringIO()
        with redirect_stdout(buf):
            analyze_alert({"alert_name": "ContainerCrashLoopBackOff"}, _settings())
        output = buf.getvalue()
        self.assertIn('"event": "recommendation_score"', output)
        self.assertIn('"investigate": 70', output)
        self.assertIn("AÇÃO RECOMENDADA: investigate", output)


if __name__ == "__main__":
    unittest.main()
