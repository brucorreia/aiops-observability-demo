from __future__ import annotations

import tempfile
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
        store._HYDRATED = True
        console._PIPELINE_CACHE = None

    def test_ready_agent_is_not_crashloop_from_last_oom(self):
        pod = {
            "metadata": {"name": "ai-agent-x", "namespace": "monitoring", "labels": {"app": "ai-agent"}},
            "spec": {"nodeName": "n1"},
            "status": {
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "True"}],
                "containerStatuses": [
                    {
                        "name": "webhook",
                        "restartCount": 2,
                        "image": "ghcr.io/x/aiops-agent:abc",
                        "state": {"running": {"startedAt": "2026-09-14T23:04:29Z"}},
                        "lastState": {"terminated": {"reason": "OOMKilled", "exitCode": 137}},
                    }
                ],
            },
        }
        summary = console._pod_status(pod)
        self.assertEqual(summary["status"], "Running")
        self.assertTrue(summary["ready"])

    def test_failing_demo_app_hides_oom_as_crashloop(self):
        pod = {
            "metadata": {"name": "demo-app-x", "namespace": "aiops-demo", "labels": {"app": "demo-app"}},
            "spec": {"nodeName": "n1"},
            "status": {
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "False"}],
                "containerStatuses": [
                    {
                        "name": "demo-app",
                        "restartCount": 4,
                        "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                        "lastState": {"terminated": {"reason": "OOMKilled", "exitCode": 137}},
                    }
                ],
            },
        }
        summary = console._pod_status(pod)
        self.assertEqual(summary["status"], "CrashLoopBackOff")
        self.assertFalse(summary["ready"])

    def test_mode_files_update_deployed_at(self):
        yaml_text = 'aiops.demo/deployed-at: "1970-01-01T00:00:00Z"\n'
        files = console._mode_files("crashloop", "2026-09-14T19:00:00Z", yaml_text)
        self.assertEqual(files[console.MODE_FILE], "crashloop\n")
        self.assertIn("2026-09-14T19:00:00Z", files[console.APP_YAML])

    def test_console_crashloop_hides_oom_cause(self):
        with patch("api.console.random.choice", return_value="oom"):
            file_mode, deployed_at, message = console.resolve_console_incident("crashloop")
        self.assertEqual(file_mode, "oom")
        self.assertNotEqual(deployed_at, "2026-01-01T00:00:00Z")
        self.assertEqual(message, "fix(demo-app): induce CrashLoopBackOff")
        self.assertNotIn("OOM", message)

    def test_console_crashloop_hides_startup_cause(self):
        with patch("api.console.random.choice", return_value="crashloop"):
            file_mode, _, message = console.resolve_console_incident("crashloop")
        self.assertEqual(file_mode, "crashloop")
        self.assertEqual(message, "fix(demo-app): induce CrashLoopBackOff")

    @patch("api.console.github.active_workflow_runs", return_value=[])
    @patch("api.console.github.commit_files", return_value={"sha": "abc", "short_sha": "abc"})
    @patch(
        "api.console.github.read_file",
        return_value='aiops.demo/deployed-at: "1970-01-01T00:00:00Z"\n',
    )
    @patch("api.console.random.choice", return_value="oom")
    def test_start_incident_returns_public_crashloop(self, _choice, _read, commit, _runs):
        result = console.start_incident(
            {"github_token": "t", "github_repository": "o/r"},
            "crashloop",
        )
        self.assertEqual(result["mode"], "crashloop")
        files, message = commit.call_args.args[1], commit.call_args.args[2]
        self.assertEqual(files[console.MODE_FILE], "oom\n")
        self.assertEqual(message, "fix(demo-app): induce CrashLoopBackOff")

    @patch("api.console.github.commit_files")
    @patch("api.console.github.read_file")
    @patch(
        "api.console.github.active_workflow_runs",
        return_value=[{"name": "demo-app", "status": "in_progress", "html_url": "http://run/1"}],
    )
    def test_start_incident_blocked_when_pipeline_running(self, _runs, read_file, commit):
        with self.assertRaises(HttpError) as ctx:
            console.start_incident(
                {"github_token": "t", "github_repository": "o/r"},
                "crashloop",
            )
        self.assertEqual(ctx.exception.status, 409)
        self.assertIn("Pipeline demo-app em andamento", str(ctx.exception))
        self.assertIn("depois do término", str(ctx.exception))
        read_file.assert_not_called()
        commit.assert_not_called()

    def test_pipeline_status_idle_without_runs(self):
        with patch("api.console.github.active_workflow_runs", return_value=[]):
            result = console.pipeline_status({"github_token": "t", "github_repository": "o/r"})
        self.assertFalse(result["busy"])
        self.assertIsNone(result["message"])

    def test_pipeline_status_blocks_recent_image_rollout(self):
        store.set_rollout(
            {
                "sha": "abc",
                "started_at": console.utc_now(),
                "wait_for_image": True,
                "image_synced": False,
                "workflow": {"status": "queued", "conclusion": None},
            }
        )
        with patch("api.console.github.active_workflow_runs", return_value=[]):
            result = console.pipeline_status({"github_token": "t", "github_repository": "o/r"})
        self.assertTrue(result["busy"])
        self.assertIn("depois do término", result["message"])
        self.assertNotIn("demo-app.yaml", result["message"])

    def test_pipeline_status_idle_for_scale_without_actions(self):
        store.set_rollout(
            {
                "sha": "def",
                "started_at": console.utc_now(),
                "wait_for_image": False,
                "image_synced": True,
                "workflow": {"status": "queued", "conclusion": None},
            }
        )
        with patch("api.console.github.active_workflow_runs", return_value=[]):
            result = console.pipeline_status({"github_token": "t", "github_repository": "o/r"})
        self.assertFalse(result["busy"])
        self.assertIsNone(result["message"])

    def test_pipeline_status_ignores_fake_queued_without_recent_start(self):
        store.set_rollout(
            {
                "sha": "abc",
                "started_at": "2020-01-01T00:00:00Z",
                "workflow": {"status": "queued", "conclusion": None},
            }
        )
        with patch("api.console.github.active_workflow_runs", return_value=[]):
            result = console.pipeline_status({"github_token": "t", "github_repository": "o/r"})
        self.assertFalse(result["busy"])

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

    def test_execute_rollback_restores_demo_app_via_gitops(self):
        analysis = store.save(
            {
                "id": "roll-1",
                "incident_type": "oom",
                "recommended_action": "rollback",
                "scoring_source": "llm",
                "evidence": {"deployment": "demo-app", "namespace": "aiops-demo"},
            }
        )
        with patch("api.console.start_incident") as start, patch(
            "api.console.k8s.patch_json"
        ) as patch_json:
            updated = console.execute_latest(
                analysis, {"github_token": "t", "github_repository": "o/r"}
            )
        start.assert_called_once_with({"github_token": "t", "github_repository": "o/r"}, "good")
        patch_json.assert_not_called()
        self.assertTrue(any(item.get("executed") for item in updated.get("approvals") or []))

    def test_bump_memory_and_replicas_from_kustomize(self):
        text = Path(__file__).resolve().parents[2].joinpath(
            "infra/apps/demo-app/kustomization.yaml"
        ).read_text()
        scaled, detail = console.bump_memory_patches(text)
        self.assertIn("128Mi", detail)
        self.assertIn("value: 128Mi", scaled)
        self.assertIn("value: 32Mi", scaled)
        replicas, replica_detail = console.bump_replica_patch(text)
        self.assertIn("1 -> 2", replica_detail)
        self.assertIn("path: /spec/replicas\n        value: 2", replicas)

    def test_memory_cap_is_gitops_conflict(self):
        text = (
            "path: /spec/template/spec/containers/0/resources/limits/memory\n"
            "        value: 256Mi\n"
        )
        with self.assertRaises(HttpError) as ctx:
            console.bump_memory_patches(text)
        self.assertEqual(ctx.exception.status, 409)

    @patch("api.console.github.active_workflow_runs", return_value=[])
    @patch("api.console.github.commit_files", return_value={"sha": "def", "short_sha": "def"})
    @patch("api.console.k8s.patch_json")
    def test_vertical_scale_commits_kustomize_not_cluster_patch(self, patch_json, commit, _runs):
        kustomize = Path(__file__).resolve().parents[2].joinpath(
            "infra/apps/demo-app/kustomization.yaml"
        ).read_text()
        with patch("api.console.github.read_file", return_value=kustomize):
            executed, detail = console.apply_remediation(
                {"github_token": "t", "github_repository": "o/r"},
                "approve_vertical_scale",
                {"evidence": {"deployment": "demo-app"}},
            )
        self.assertTrue(executed)
        self.assertIn("128Mi", detail)
        patch_json.assert_not_called()
        files, message = commit.call_args.args[1], commit.call_args.args[2]
        self.assertIn("value: 128Mi", files[console.KUSTOMIZE_FILE])
        self.assertEqual(message, "fix(demo-app): raise memory limit via GitOps")
        rollout = store.rollout() or {}
        self.assertEqual(rollout.get("workflow"), {"status": "completed", "conclusion": "success"})
        self.assertTrue(rollout.get("image_synced"))
        self.assertFalse(rollout.get("wait_for_image"))

    @patch("api.console.github.active_workflow_runs", return_value=[])
    @patch("api.console.github.commit_files", return_value={"sha": "ghi", "short_sha": "ghi"})
    @patch("api.console.k8s.patch_json")
    def test_horizontal_scale_commits_replica_patch(self, patch_json, commit, _runs):
        kustomize = Path(__file__).resolve().parents[2].joinpath(
            "infra/apps/demo-app/kustomization.yaml"
        ).read_text()
        with patch("api.console.github.read_file", return_value=kustomize):
            executed, detail = console.apply_remediation(
                {"github_token": "t", "github_repository": "o/r"},
                "approve_horizontal_scale",
                {"evidence": {"deployment": "demo-app"}},
            )
        self.assertTrue(executed)
        self.assertIn("2", detail)
        patch_json.assert_not_called()
        files = commit.call_args.args[1]
        self.assertIn("path: /spec/replicas\n        value: 2", files[console.KUSTOMIZE_FILE])

    def test_execute_latest_scale_does_not_call_kubectl_patch(self):
        analysis = store.save(
            {
                "id": "scale-1",
                "incident_type": "oom",
                "recommended_action": "vertical_scale",
                "scoring_source": "llm",
                "evidence": {"deployment": "demo-app"},
            }
        )
        with patch(
            "api.console.apply_remediation", return_value=(True, "GitOps memory 32Mi -> 128Mi")
        ) as apply, patch("api.console.k8s.patch_json") as patch_json:
            updated = console.execute_latest(
                analysis, {"github_token": "t", "github_repository": "o/r"}
            )
        apply.assert_called_once()
        patch_json.assert_not_called()
        self.assertTrue(any(item.get("executed") for item in updated.get("approvals") or []))

    def test_recommendation_view_executable_when_llm_scored(self):
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
        self.assertTrue(view["recommendations"][0]["executable"])
        investigate = console.recommendation_view(
            {
                "id": "2",
                "incident_type": "crashloop",
                "recommended_action": "investigate",
                "scoring_source": "llm",
                "recommendations": [{"action": "investigate", "recommendation_score": 70}],
                "evidence": {},
            }
        )
        self.assertTrue(investigate["executable"])
        self.assertFalse(investigate["recommendations"][0]["executable"])
        skipped = console.recommendation_view(
            {
                "id": "3",
                "incident_type": "crashloop",
                "recommended_action": "investigate",
                "scoring_source": "llm_unavailable",
                "recommendations": [],
                "evidence": {},
            }
        )
        self.assertFalse(skipped["executable"])

    def test_execute_latest_honors_operator_action(self):
        analysis = store.save(
            {
                "id": "pick-1",
                "incident_type": "oom",
                "recommended_action": "rollback",
                "scoring_source": "llm",
                "evidence": {"deployment": "demo-app"},
            }
        )
        with patch(
            "api.console.apply_remediation", return_value=(True, "GitOps memory 32Mi -> 128Mi")
        ) as apply:
            updated = console.execute_latest(
                analysis,
                {"github_token": "t", "github_repository": "o/r"},
                "vertical_scale",
            )
        apply.assert_called_once()
        self.assertEqual(apply.call_args.args[1], "approve_vertical_scale")
        self.assertTrue(any(item.get("executed") for item in updated.get("approvals") or []))

    def test_execute_latest_rejects_investigate(self):
        analysis = store.save(
            {
                "id": "pick-2",
                "incident_type": "oom",
                "recommended_action": "rollback",
                "scoring_source": "llm",
                "evidence": {"deployment": "demo-app"},
            }
        )
        with self.assertRaises(PermissionError):
            console.execute_latest(
                analysis,
                {"github_token": "t", "github_repository": "o/r"},
                "investigate",
            )

    def test_latest_reloads_scores_from_disk(self):
        data_dir = Path(tempfile.mkdtemp())
        payload = {
            "id": "disk-1",
            "recommended_action": "vertical_scale",
            "scoring_source": "llm",
            "recommendations": [
                {"action": "rollback", "recommendation_score": 40},
                {"action": "vertical_scale", "recommendation_score": 40},
            ],
        }
        (data_dir / "disk-1.json").write_text(
            __import__("json").dumps(payload),
            encoding="utf-8",
        )
        store.STORE.clear()
        store.LATEST = None
        store._HYDRATED = False
        with patch.object(store, "DATA_DIR", data_dir):
            loaded = store.latest()
        self.assertEqual(loaded["id"], "disk-1")
        self.assertEqual(loaded["recommendations"][1]["recommendation_score"], 40)
        view = console.recommendation_view(loaded)
        self.assertEqual(view["recommendations"][1]["recommendation_score"], 40)
        self.assertTrue(view["executable"])

    def test_static_missing_dir_returns_none(self):
        with patch.object(console, "CONSOLE_DIR", Path("/tmp/missing-console-ui")):
            self.assertIsNone(console.static_file("/"))


if __name__ == "__main__":
    unittest.main()
