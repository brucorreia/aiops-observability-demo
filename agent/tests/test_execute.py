from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


if __name__ == "__main__":
    unittest.main()
