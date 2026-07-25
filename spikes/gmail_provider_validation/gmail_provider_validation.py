"""Small, testable Gmail OAuth and History API adapter for live validation.

This harness intentionally has no persistence layer. Production mailbox and
credential repositories belong to the ledger implementation; this module
proves the external-provider boundary while keeping refresh tokens out of
command output and logs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class ProviderRequestError(RuntimeError):
    """A non-recoverable Gmail or OAuth API request failed."""


class InvalidHistoryCursor(ProviderRequestError):
    """Gmail no longer retains the requested History API cursor."""


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        form: Mapping[str, str] | None = None,
    ) -> Mapping[str, object]: ...


class UrllibTransport:
    """Minimal JSON transport; callers never place secrets in URLs."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        form: Mapping[str, str] | None = None,
    ) -> Mapping[str, object]:
        request_headers = dict(headers or {})
        body = None
        if form is not None:
            body = urlencode(form).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed Google endpoints
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404 and "/history" in url:
                raise InvalidHistoryCursor("Gmail history cursor is no longer available") from exc
            raise ProviderRequestError(f"Google API request failed with HTTP {exc.code}") from exc
        if not isinstance(payload, dict):
            raise ProviderRequestError("Google API response was not a JSON object")
        return payload


@dataclass(frozen=True)
class OAuthClientConfig:
    client_id: str
    redirect_uri: str
    client_secret: str | None = None


@dataclass(frozen=True)
class AuthorizationRequest:
    url: str
    state: str
    code_verifier: str


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scope: str

    def __repr__(self) -> str:
        return (
            "TokenSet(access_token='<redacted>', refresh_token='<redacted>', "
            f"expires_at={self.expires_at!r}, scope={self.scope!r})"
        )


@dataclass(frozen=True)
class HistoryPage:
    message_ids: tuple[str, ...]
    next_page_token: str | None
    history_id: str


@dataclass(frozen=True)
class GmailProfile:
    email_address: str
    history_id: str


class GoogleOAuthClient:
    def __init__(self, config: OAuthClientConfig, transport: HttpTransport) -> None:
        self.config = config
        self.transport = transport

    def create_authorization_request(self) -> AuthorizationRequest:
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        state = secrets.token_urlsafe(32)
        query = urlencode(
            {
                "access_type": "offline",
                "client_id": self.config.client_id,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "redirect_uri": self.config.redirect_uri,
                "response_type": "code",
                "scope": GMAIL_READONLY_SCOPE,
                "state": state,
            }
        )
        return AuthorizationRequest(
            url=f"{GOOGLE_AUTHORIZE_URL}?{query}",
            state=state,
            code_verifier=code_verifier,
        )

    def exchange_code(self, code: str, code_verifier: str) -> TokenSet:
        form = {
            "client_id": self.config.client_id,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": self.config.redirect_uri,
        }
        if self.config.client_secret:
            form["client_secret"] = self.config.client_secret
        return self._token_request(form, require_refresh_token=True)

    def refresh(self, refresh_token: str) -> TokenSet:
        form = {
            "client_id": self.config.client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        if self.config.client_secret:
            form["client_secret"] = self.config.client_secret
        return self._token_request(form, require_refresh_token=False)

    def _token_request(self, form: Mapping[str, str], *, require_refresh_token: bool) -> TokenSet:
        response = self.transport.request("POST", GOOGLE_TOKEN_URL, form=form)
        access_token = _required_string(response, "access_token")
        refresh_token = _optional_string(response, "refresh_token")
        if require_refresh_token and refresh_token is None:
            raise ProviderRequestError("Google did not return a refresh token")
        expires_in = response.get("expires_in", 3600)
        if not isinstance(expires_in, int) or expires_in <= 0:
            raise ProviderRequestError("Google returned an invalid token expiry")
        return TokenSet(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            scope=_optional_string(response, "scope") or GMAIL_READONLY_SCOPE,
        )


class GmailHistoryClient:
    def __init__(self, transport: HttpTransport, access_token: str) -> None:
        self.transport = transport
        self.headers = {"Authorization": f"Bearer {access_token}"}

    def profile(self) -> GmailProfile:
        response = self.transport.request("GET", f"{GMAIL_API_ROOT}/profile", headers=self.headers)
        return GmailProfile(
            email_address=_required_string(response, "emailAddress"),
            history_id=_required_string(response, "historyId"),
        )

    def profile_email(self) -> str:
        return self.profile().email_address

    def history_page(self, start_history_id: str, page_token: str | None = None) -> HistoryPage:
        query = {"startHistoryId": start_history_id, "historyTypes": "messageAdded"}
        if page_token:
            query["pageToken"] = page_token
        response = self.transport.request(
            "GET",
            f"{GMAIL_API_ROOT}/history?{urlencode(query)}",
            headers=self.headers,
        )
        message_ids: list[str] = []
        history = response.get("history", [])
        if not isinstance(history, list):
            raise ProviderRequestError("Gmail returned invalid history data")
        for event in history:
            if not isinstance(event, dict):
                continue
            added = event.get("messagesAdded", [])
            if not isinstance(added, list):
                continue
            for item in added:
                if not isinstance(item, dict) or not isinstance(item.get("message"), dict):
                    continue
                message_id = item["message"].get("id")
                if isinstance(message_id, str):
                    message_ids.append(message_id)
        return HistoryPage(
            message_ids=tuple(dict.fromkeys(message_ids)),
            next_page_token=_optional_string(response, "nextPageToken"),
            history_id=_required_string(response, "historyId"),
        )

    def all_history_message_ids(self, start_history_id: str) -> tuple[tuple[str, ...], str]:
        page_token: str | None = None
        message_ids: list[str] = []
        final_history_id = start_history_id
        while True:
            page = self.history_page(start_history_id, page_token)
            message_ids.extend(page.message_ids)
            final_history_id = page.history_id
            if page.next_page_token is None:
                return tuple(dict.fromkeys(message_ids)), final_history_id
            page_token = page.next_page_token


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ProviderRequestError(f"Google response omitted {key}")
    return value


def _optional_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None
