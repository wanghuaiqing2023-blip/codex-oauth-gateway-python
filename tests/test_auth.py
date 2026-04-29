import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from gateway import auth


class AuthTests(unittest.TestCase):
    def test_get_valid_tokens_returns_existing_token_when_not_expired(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "openai.json"
            token_file.write_text(
                json.dumps(
                    {
                        "type": "oauth",
                        "access": "a.b.c",
                        "refresh": "refresh_1",
                        "expires": int(time.time() * 1000) + 3600 * 1000,
                    }
                ),
                encoding="utf-8",
            )
            original = auth.TOKEN_FILE
            auth.TOKEN_FILE = token_file
            try:
                token_set = auth.get_valid_tokens()
                self.assertEqual(token_set.refresh, "refresh_1")
            finally:
                auth.TOKEN_FILE = original

    @patch("gateway.auth.requests.post")
    def test_get_valid_tokens_refreshes_and_persists_when_expired(self, mock_post):
        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "access_token": "new_access",
                    "refresh_token": "new_refresh",
                    "expires_in": 3600,
                }

        mock_post.return_value = FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "openai.json"
            token_file.write_text(
                json.dumps(
                    {
                        "type": "oauth",
                        "access": "a.b.c",
                        "refresh": "refresh_1",
                        "expires": int(time.time() * 1000) - 1000,
                    }
                ),
                encoding="utf-8",
            )
            original = auth.TOKEN_FILE
            auth.TOKEN_FILE = token_file
            try:
                token_set = auth.get_valid_tokens()
                self.assertEqual(token_set.access, "new_access")
                persisted = json.loads(token_file.read_text(encoding="utf-8"))
                self.assertEqual(persisted["access"], "new_access")
                self.assertEqual(persisted["refresh"], "new_refresh")
            finally:
                auth.TOKEN_FILE = original


if __name__ == "__main__":
    unittest.main()
