from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from enrichment.normalize import incident_type_for, normalize_alertmanager


class NormalizeTests(unittest.TestCase):
    def test_alertmanager_payload(self):
        payload = {
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HighHttp5xxFromLogs",
                        "namespace": "aiops-demo",
                        "severity": "critical",
                    },
                    "startsAt": "2026-09-12T12:00:00Z",
                },
                {
                    "status": "resolved",
                    "labels": {"alertname": "ContainerOOMKilled"},
                },
            ],
        }
        alerts = normalize_alertmanager(payload)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["incident_type"], "http500")
        self.assertEqual(alerts[0]["signal"], "logs")

    def test_crashloop_with_oom_reason_is_classified_as_oom(self):
        self.assertEqual(incident_type_for("ContainerCrashLoopBackOff", "OOMKilled"), "oom")
        self.assertEqual(incident_type_for("ContainerCrashLoopBackOff", None), "crashloop")


if __name__ == "__main__":
    unittest.main()
