import unittest
from unittest.mock import patch

import auth_cli
from gateway.auth import AuthorizationFlow


class AuthCliTests(unittest.TestCase):
    @patch('auth_cli.save_tokens')
    @patch('auth_cli.exchange_authorization_code')
    @patch('auth_cli._wait_for_callback')
    @patch('auth_cli.webbrowser.open')
    @patch('auth_cli.create_authorization_flow')
    def test_main_rejects_state_mismatch(
        self,
        mock_create_flow,
        _mock_open_browser,
        mock_wait_for_callback,
        mock_exchange,
        mock_save,
    ):
        mock_create_flow.return_value = AuthorizationFlow(
            url='https://example.test/oauth?state=expected_state',
            verifier='verifier',
            state='expected_state',
        )
        mock_wait_for_callback.return_value = ('fake_code', 'wrong_state')

        result = auth_cli.main()

        self.assertEqual(result, 1)
        mock_exchange.assert_not_called()
        mock_save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
