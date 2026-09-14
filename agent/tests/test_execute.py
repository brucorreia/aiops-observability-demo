from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.server import apply_recommendation
from recommendations import store
from recommendations.execute import automatic_decision


class AutomaticExecutionTests(unittest.TestCase):
    def test_rollback_is_executed_when_llm_scored(self):
        decision = automatic_decision(
            {
                "automatic_execution_allowed": True,
                "scoring_source": "llm",
                "recommended_action": "rollback",
            }
        )
        self.assertEqual(decision, "approve_rollback")

    def test_skips_when_llm_unavailable(self):
        self.assertIsNone(
            automatic_decision(
                {
                    "automatic_execution_allowed": True,
                    "scoring_source": "llm_unavailable",
                    "recommended_action": "investigate",
                }
            )
        )

    def test_skips_investigate_and_none(self):
        self.assertIsNone(
            automatic_decision(
                {
                    "automatic_execution_allowed": True,
                    "scoring_source": "llm",
                    "recommended_action": "investigate",
                }
            )
        )
        self.assertIsNone(
            automatic_decision(
                {
                    "automatic_execution_allowed": True,
                    "scoring_source": "llm",
                    "recommended_action": "none",
                }
            )
        )

    def test_skips_when_flag_disabled(self):
        self.assertIsNone(
            automatic_decision(
                {
                    "automatic_execution_allowed": False,
                    "scoring_source": "llm",
                    "recommended_action": "rollback",
                }
            )
        )

    def test_webhook_skips_execute_when_flag_disabled(self):
        store.EVENTS.clear()
        analysis = {
            "id": "oom-demo",
            "incident_type": "oom",
            "automatic_execution_allowed": False,
            "scoring_source": "llm",
            "recommended_action": "rollback",
        }
        updated = apply_recommendation(analysis)
        self.assertEqual(updated["recommended_action"], "rollback")
        self.assertFalse(updated.get("executed"))
        self.assertTrue(
            any(item.get("reason") == "automatic_execution_disabled" for item in store.EVENTS)
        )


if __name__ == "__main__":
    unittest.main()
