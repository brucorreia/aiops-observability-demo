from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors import github
from collectors.http import HttpError


class GithubCommitTests(unittest.TestCase):
    def test_commit_files_uses_graphql_create_commit(self):
        calls = []

        def fake_get(url, **_kwargs):
            calls.append(("GET", url))
            return {"sha": "aaa1111"}

        def fake_json(url, method="POST", payload=None, **_kwargs):
            calls.append((method, url, payload))
            return {
                "data": {
                    "createCommitOnBranch": {
                        "commit": {
                            "oid": "ccc1234abcdef",
                            "commitUrl": "http://commit/ccc1234",
                        }
                    }
                }
            }

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
        self.assertTrue(any(item[1].endswith("/graphql") for item in calls if item[0] == "POST"))
        payload = next(item[2] for item in calls if item[0] == "POST")
        additions = payload["variables"]["input"]["fileChanges"]["additions"]
        self.assertEqual(additions[0]["path"], "apps/demo-app/demo_mode")
        self.assertNotIn("/git/blobs", "".join(str(item[1]) for item in calls))

    def test_blob_forbidden_becomes_write_denied(self):
        def fake_get(*_args, **_kwargs):
            raise HttpError(
                'HTTP 403 for https://api.github.com/repos/o/r/commits/main: '
                'b\'{"message":"Resource not accessible by personal access token"}\'',
                status=403,
            )

        with patch("collectors.github.get_json", fake_get), self.assertRaises(HttpError) as ctx:
            github.commit_files("o/r", {"a": "b"}, "msg", "token")
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn("Contents deve ser Read and write", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
