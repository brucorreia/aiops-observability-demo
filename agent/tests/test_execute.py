from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.server import CFG, LAST_EXECUTION_AT, apply_recommendation
from collectors.k8s import patch_json
from recommendations import store
from recommendations.execute import automatic_decision, execute


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

    def test_execute_requires_gitops_config(self):
        with self.assertRaises(RuntimeError):
            execute("approve_rollback", {}, None)

    @patch("api.console.apply_remediation", return_value=(True, "GitOps restore healthy mode"))
    def test_execute_delegates_to_gitops(self, apply):
        executed, detail = execute(
            "approve_rollback",
            {"evidence": {"deployment": "demo-app"}},
            {"github_token": "t", "github_repository": "o/r"},
        )
        self.assertTrue(executed)
        self.assertIn("GitOps", detail)
        apply.assert_called_once()

    def test_cluster_patches_are_disabled(self):
        with self.assertRaises(RuntimeError):
            patch_json("/apis/apps/v1/namespaces/aiops-demo/deployments/demo-app", {})

    def test_webhook_execute_passes_gitops_config(self):
        LAST_EXECUTION_AT.clear()
        store.STORE.clear()
        analysis = store.save(
            {
                "id": "vert-auto",
                "incident_type": "oom",
                "automatic_execution_allowed": True,
                "scoring_source": "llm",
                "recommended_action": "vertical_scale",
            }
        )
        with patch(
            "api.server.execute_mod.execute", return_value=(True, "GitOps memory 32Mi -> 128Mi")
        ) as ex:
            updated = apply_recommendation(analysis)
        ex.assert_called_once()
        self.assertEqual(ex.call_args.args[0], "approve_vertical_scale")
        self.assertIs(ex.call_args.args[2], CFG)
        self.assertTrue(any(item.get("executed") for item in updated.get("approvals") or []))


class QuietServerTests(unittest.TestCase):
    def test_broken_pipe_is_not_raised(self):
        from api.server import Handler, QuietThreadingHTTPServer

        server = QuietThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        try:
            raise BrokenPipeError()
        except BrokenPipeError:
            server.handle_error(None, ("127.0.0.1", 1))


if __name__ == "__main__":
    unittest.main()
