"""Interactively validate Gmail OAuth and incremental History API access.

Run with a local ignored `.env` loaded into the shell. The program neither
persists nor prints authorization codes, access tokens, or refresh tokens.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

from spikes.gmail_provider_validation.gmail_provider_validation import (
    GmailHistoryClient,
    GoogleOAuthClient,
    OAuthClientConfig,
    ProviderRequestError,
    UrllibTransport,
)


def main() -> None:
    config = OAuthClientConfig(
        client_id=_required_environment("ARCIS_GMAIL_OAUTH_CLIENT_ID"),
        client_secret=os.getenv("ARCIS_GMAIL_OAUTH_CLIENT_SECRET"),
        redirect_uri=_required_environment("ARCIS_GMAIL_OAUTH_REDIRECT_URI"),
    )
    oauth = GoogleOAuthClient(config, UrllibTransport())
    authorization = oauth.create_authorization_request()
    print("Open this local authorization URL in a browser:")
    print(authorization.url)
    callback_url = input("Paste the complete callback URL here: ").strip()
    code = _validated_callback_code(callback_url, authorization.state)
    token_set = oauth.exchange_code(code, authorization.code_verifier)
    if token_set.refresh_token is None:  # Defensive: exchange_code requires it.
        raise ProviderRequestError("Google did not issue a refresh token")

    history = GmailHistoryClient(UrllibTransport(), token_set.access_token)
    profile = history.profile()
    refreshed = oauth.refresh(token_set.refresh_token)
    print(
        "OAuth and refresh succeeded for "
        f"{_mask_email(profile.email_address)}; "
        f"current Gmail history cursor is {profile.history_id}."
    )
    print(
        "No tokens were printed or persisted. Send a synthetic test email, then press Enter "
        "to validate incremental discovery."
    )
    input()
    incremental = GmailHistoryClient(UrllibTransport(), refreshed.access_token)
    message_ids, next_cursor = incremental.all_history_message_ids(profile.history_id)
    print(
        "Incremental History API validation succeeded: "
        f"{len(message_ids)} message IDs discovered; next cursor is {next_cursor}."
    )


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} must be set in local environment configuration")
    return value


def _validated_callback_code(callback_url: str, expected_state: str) -> str:
    query = parse_qs(urlparse(callback_url).query)
    if query.get("state") != [expected_state]:
        raise SystemExit("OAuth callback state did not match the initiated request")
    code = query.get("code", [None])[0]
    if not isinstance(code, str) or not code:
        raise SystemExit("OAuth callback did not include an authorization code")
    return code


def _mask_email(email: str) -> str:
    local_part, separator, domain = email.partition("@")
    if not separator:
        return "<invalid-email>"
    return f"{local_part[:1]}***@{domain}"


if __name__ == "__main__":
    main()
