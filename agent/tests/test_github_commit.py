from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors import github


class GithubCommitTests(unittest.TestCase):
    def test_commit_files_creates_one_commit(self):
        calls = []

        def fake_get(url, **_kwargs):
            calls.append(("GET", url))
            if "/git/ref/" in url:
                return {"object": {"sha": "aaa"}}
            return {"tree": {"sha": "tree0"}}

        def fake_json(url, method="POST", payload=None, **_kwargs):
            calls.append((method, url, payload))
            if url.endswith("/git/blobs"):
                return {"sha": "blob1"}
            if url.endswith("/git/trees"):
                return {"sha": "tree1"}
            if url.endswith("/git/commits"):
                return {"sha": "ccc1234", "html_url": "http://commit"}
            return {"sha": "ccc1234"}

        with patch("collectors.github.get_json", fake_get), patch(
            "collectors.github.json_request", fake_json
        ):
            result = github.commit_files(
                "owner/repo",
                {"apps/demo-app/demo_mode": "crashloop\n"},
                "fix(demo-app): fail startup (CrashLoopBackOff)",
                "token",
            )
        self.assertEqual(result["short_sha"], "ccc1234")
        methods = [item[0] for item in calls]
        self.assertIn("PATCH", methods)


if __name__ == "__main__":
    unittest.main()
