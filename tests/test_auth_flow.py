import unittest
from unittest.mock import patch

from gateway.auth import (
    create_authorization_flow,
    exchange_authorization_code,
    parse_authorization_input,
)


class AuthFlowTests(unittest.TestCase):
    def test_create_authorization_flow_contains_pkce_and_state(self):
        flow = create_authorization_flow()
        self.assertIn("response_type=code", flow.url)
        self.assertIn("code_challenge_method=S256", flow.url)
        self.assertTrue(flow.verifier)
        self.assertTrue(flow.state)

    def test_parse_authorization_input_variants(self):
        code, state = parse_authorization_input("http://localhost/callback?code=abc&state=xyz")
        self.assertEqual(code, "abc")
        self.assertEqual(state, "xyz")

        code, state = parse_authorization_input("code=abc&state=xyz")
        self.assertEqual(code, "abc")
        self.assertEqual(state, "xyz")

        code, state = parse_authorization_input("abc#xyz")
        self.assertEqual(code, "abc")
        self.assertEqual(state, "xyz")

    @patch("gateway.auth.requests.post")
    def test_exchange_authorization_code_success(self, mock_post):
        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "access_token": "acc",
                    "refresh_token": "ref",
                    "expires_in": 3600,
                }

        mock_post.return_value = FakeResponse()
        token_set = exchange_authorization_code("auth_code", "pkce_verifier")
        self.assertEqual(token_set.access, "acc")
        self.assertEqual(token_set.refresh, "ref")


if __name__ == "__main__":
    unittest.main()
