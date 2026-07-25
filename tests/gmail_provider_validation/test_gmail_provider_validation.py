import base64
import hashlib
import unittest
from collections.abc import Mapping
from urllib.parse import parse_qs, urlparse

from spikes.gmail_provider_validation.gmail_provider_validation import (
    GMAIL_READONLY_SCOPE,
    GOOGLE_TOKEN_URL,
    GmailHistoryClient,
    GoogleOAuthClient,
    HttpTransport,
    InvalidHistoryCursor,
    OAuthClientConfig,
    ProviderRequestError,
)


class RecordingTransport(HttpTransport):
    def __init__(self, responses: list[Mapping[str, object] | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, Mapping[str, str] | None]] = []

    def request(self, method, url, *, headers=None, form=None):
        self.calls.append((method, url, form))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class GmailProviderValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = OAuthClientConfig(
            client_id="client-id.apps.googleusercontent.com",
            client_secret="test-client-secret",
            redirect_uri="http://127.0.0.1:8765/callback",
        )

    def test_authorization_request_uses_pkce_state_and_readonly_scope(self):
        client = GoogleOAuthClient(self.config, RecordingTransport([]))

        request = client.create_authorization_request()

        query = parse_qs(urlparse(request.url).query)
        self.assertEqual(query["scope"], [GMAIL_READONLY_SCOPE])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["state"], [request.state])
        expected_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(request.code_verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        self.assertEqual(query["code_challenge"], [expected_challenge])

    def test_code_exchange_requires_and_redacts_refresh_token(self):
        transport = RecordingTransport(
            [
                {
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "expires_in": 3600,
                }
            ]
        )
        client = GoogleOAuthClient(self.config, transport)

        token_set = client.exchange_code("authorization-code", "verifier")

        self.assertEqual(transport.calls[0][1], GOOGLE_TOKEN_URL)
        self.assertEqual(transport.calls[0][2]["code_verifier"], "verifier")
        self.assertIn("<redacted>", repr(token_set))
        self.assertNotIn("access-secret", repr(token_set))
        self.assertNotIn("refresh-secret", repr(token_set))

    def test_code_exchange_fails_closed_without_refresh_token(self):
        client = GoogleOAuthClient(
            self.config, RecordingTransport([{"access_token": "access-secret", "expires_in": 3600}])
        )

        with self.assertRaisesRegex(ProviderRequestError, "refresh token"):
            client.exchange_code("authorization-code", "verifier")

    def test_token_refresh_allows_omitted_rotated_refresh_token(self):
        transport = RecordingTransport([{"access_token": "new-access-secret", "expires_in": 1800}])
        token_set = GoogleOAuthClient(self.config, transport).refresh("existing-refresh-secret")

        self.assertIsNone(token_set.refresh_token)
        self.assertEqual(transport.calls[0][2]["grant_type"], "refresh_token")

    def test_history_pagination_deduplicates_ids_and_advances_cursor(self):
        transport = RecordingTransport(
            [
                {
                    "historyId": "101",
                    "nextPageToken": "next-page",
                    "history": [
                        {"messagesAdded": [{"message": {"id": "one"}}, {"message": {"id": "two"}}]}
                    ],
                },
                {
                    "historyId": "102",
                    "history": [
                        {
                            "messagesAdded": [
                                {"message": {"id": "two"}},
                                {"message": {"id": "three"}},
                            ]
                        }
                    ],
                },
            ]
        )

        history_client = GmailHistoryClient(transport, "access-secret")
        message_ids, cursor = history_client.all_history_message_ids("100")

        self.assertEqual(message_ids, ("one", "two", "three"))
        self.assertEqual(cursor, "102")
        self.assertIn("pageToken=next-page", transport.calls[1][1])

    def test_invalid_history_cursor_is_not_treated_as_an_empty_sync(self):
        transport = RecordingTransport([InvalidHistoryCursor("expired")])
        client = GmailHistoryClient(transport, "access-secret")

        with self.assertRaises(InvalidHistoryCursor):
            client.all_history_message_ids("100")

    def test_profile_returns_email_and_current_history_cursor(self):
        transport = RecordingTransport([{"emailAddress": "test@example.com", "historyId": "100"}])

        profile = GmailHistoryClient(transport, "access-secret").profile()

        self.assertEqual(profile.email_address, "test@example.com")
        self.assertEqual(profile.history_id, "100")


if __name__ == "__main__":
    unittest.main()
