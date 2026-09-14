from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_scoring_config, settings
from hypotheses.generate import generate
from recommendations.format import ordered_recommendations, recommended_action
from scoring.engine import apply_weights, clip_and_normalize, score_quality
from scoring.signals import derive_signals


def cfg():
    return settings(load_scoring_config(str(Path(__file__).resolve().parents[2] / "config" / "scoring.yaml")))


def context(**overrides):
    base = {
        "deployment": "demo-app",
        "recent_deployment": True,
        "minutes_since_deployment": 4,
        "previous_revision_healthy": True,
        "failures_started_after_deployment": True,
        "last_termination_reason": None,
        "memory_usage_ratio": None,
        "sustained_memory_growth": None,
        "traffic_growth": False,
        "affected_pods": 1,
        "replicas": 1,
        "external_dependency_errors": False,
        "pods_ready": 1,
        "cpu_saturation": False,
        "http_500_count": 0,
        "missing_evidence": [],
    }
    base.update(overrides)
    return base


def scores_for(incident_type: str, **overrides):
    conf = cfg()
    ctx = context(**overrides)
    signals = derive_signals(incident_type, ctx)
    raw = apply_weights(signals, conf["weights"])
    scores = clip_and_normalize(raw)
    return scores, signals, ctx


class ScoringTests(unittest.TestCase):
    def test_scores_sum_to_100_and_are_non_negative(self):
        for incident in ("oom", "crashloop", "http500"):
            scores, _, _ = scores_for(incident)
            self.assertEqual(sum(scores.values()), 100)
            self.assertTrue(all(value >= 0 for value in scores.values()))

    def test_oom_recent_deploy_prefers_rollback(self):
        scores, _, _ = scores_for(
            "oom",
            last_termination_reason="OOMKilled",
            memory_usage_ratio=0.99,
            sustained_memory_growth=True,
        )
        self.assertGreater(scores["rollback"], scores["vertical_scale"])
        self.assertGreater(scores["rollback"], scores["horizontal_scale"])
        self.assertEqual(recommended_action(scores, True), "rollback")

    def test_oom_without_recent_deploy_prefers_vertical_scale(self):
        scores, _, _ = scores_for(
            "oom",
            recent_deployment=False,
            minutes_since_deployment=90,
            previous_revision_healthy=False,
            failures_started_after_deployment=False,
            last_termination_reason="OOMKilled",
            memory_usage_ratio=0.99,
            sustained_memory_growth=False,
        )
        self.assertGreater(scores["vertical_scale"], scores["rollback"])
        self.assertEqual(recommended_action(scores, False), "vertical_scale")

    def test_horizontal_scale_is_low_for_single_process_oom(self):
        scores, _, _ = scores_for(
            "oom",
            last_termination_reason="OOMKilled",
            sustained_memory_growth=True,
            replicas=1,
        )
        self.assertLess(scores["horizontal_scale"], 15)

    def test_crashloop_after_deploy_has_very_high_rollback(self):
        scores, _, _ = scores_for("crashloop", last_termination_reason="Error", pods_ready=0)
        self.assertGreaterEqual(scores["rollback"], 80)

    def test_crashloop_without_deploy_prefers_investigation(self):
        scores, _, _ = scores_for(
            "crashloop",
            recent_deployment=False,
            minutes_since_deployment=90,
            previous_revision_healthy=False,
            failures_started_after_deployment=False,
            last_termination_reason="Error",
            pods_ready=0,
        )
        self.assertGreater(scores["investigate"], scores["rollback"])

    def test_http500_after_deploy_with_ready_pods_prefers_rollback(self):
        scores, _, _ = scores_for(
            "http500",
            pods_ready=1,
            http_500_count=20,
        )
        self.assertGreater(scores["rollback"], scores["investigate"])
        self.assertGreater(scores["rollback"], scores["vertical_scale"])

    def test_http500_without_deploy_and_timeouts_prefers_investigate(self):
        scores, _, _ = scores_for(
            "http500",
            recent_deployment=False,
            minutes_since_deployment=90,
            previous_revision_healthy=False,
            failures_started_after_deployment=False,
            pods_ready=1,
            external_dependency_errors=True,
            http_500_count=20,
        )
        self.assertGreater(scores["investigate"], scores["rollback"])

    def test_missing_evidence_does_not_invent_deploy(self):
        ctx = context(recent_deployment=None, missing_evidence=[{"evidence": "last_deployment_at", "status": "unavailable"}])
        signals = derive_signals("oom", ctx)
        self.assertFalse(signals["recent_deployment"])
        self.assertFalse(signals["no_recent_deployment"])
        self.assertTrue(signals["weak_evidence"])
        quality = score_quality(ctx["missing_evidence"], [])
        self.assertEqual(quality, "medium")

    def test_unavailable_metrics_are_propagated(self):
        scores, signals, ctx = scores_for(
            "oom",
            recent_deployment=None,
            previous_revision_healthy=None,
            failures_started_after_deployment=None,
            last_termination_reason="OOMKilled",
            memory_usage_ratio=None,
            missing_evidence=[
                {"evidence": "last_deployment_at", "status": "unavailable"},
                {"evidence": "memory_peak_bytes", "status": "unavailable"},
                {"evidence": "previous_version_memory", "status": "unavailable"},
            ],
        )
        self.assertEqual(sum(scores.values()), 100)
        self.assertTrue(signals["weak_evidence"])
        self.assertGreater(scores["none"] + scores["investigate"], scores["rollback"])
        for rec in ordered_recommendations(scores, signals):
            joined = " ".join(rec["reasons"]).lower()
            self.assertNotIn("invented", joined)
            self.assertNotIn("definitely", joined)

    def test_hypotheses_require_supporting_signals(self):
        ctx = context(recent_deployment=False, failures_started_after_deployment=False)
        hyps = generate("oom", ctx, derive_signals("oom", ctx))
        regression = next(item for item in hyps if item["id"] == "regression_current_version")
        self.assertFalse(regression["supported"])

    def test_kustomize_scoring_file_matches_config(self):
        import yaml

        root = Path(__file__).resolve().parents[2]
        config_file = yaml.safe_load((root / "config" / "scoring.yaml").read_text())
        deploy_file = yaml.safe_load((root / "deploy" / "base" / "scoring.yaml").read_text())
        self.assertEqual(config_file, deploy_file)


if __name__ == "__main__":
    unittest.main()
