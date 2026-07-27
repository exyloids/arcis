"""Server-side Gmail OAuth authorization-code flow with PKCE."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from arcis_backend.mailboxes import MailboxService

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
HISTORY_URL = "https://gmail.googleapis.com/gmail/v1/users/me/history"
READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailOAuthError(ValueError):
    """A safe OAuth error suitable for a browser response."""


class GmailOAuthService:
    def __init__(self, engine: Engine, user_id: UUID, mailboxes: MailboxService, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self.engine, self.user_id, self.mailboxes = engine, user_id, mailboxes
        self.client_id, self.client_secret, self.redirect_uri = client_id, client_secret, redirect_uri

    def start(self) -> str:
        if not self.client_id or not self.client_secret:
            raise GmailOAuthError("Gmail OAuth is not configured")
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        with Session(self.engine) as session, session.begin():
            session.execute(text("""INSERT INTO oauth_authorizations (id, user_id, provider, state_sha256, code_verifier, redirect_uri, expires_at)
                VALUES (:id, :user_id, 'gmail', :state, :verifier, :redirect_uri, :expires_at)"""),
                {"id": uuid4(), "user_id": self.user_id, "state": _hash(state), "verifier": verifier,
                 "redirect_uri": self.redirect_uri, "expires_at": datetime.now(UTC) + timedelta(minutes=10)})
        return f"{AUTHORIZE_URL}?{urlencode({'access_type':'offline','client_id':self.client_id,'code_challenge':challenge,'code_challenge_method':'S256','prompt':'consent','redirect_uri':self.redirect_uri,'response_type':'code','scope':READONLY_SCOPE,'state':state})}"

    def complete(self, code: str, state: str) -> dict[str, object]:
        with Session(self.engine) as session, session.begin():
            authorization = session.execute(text("""SELECT * FROM oauth_authorizations WHERE state_sha256 = :state AND user_id = :user_id
                AND provider = 'gmail' AND consumed_at IS NULL AND expires_at > now() FOR UPDATE"""),
                {"state": _hash(state), "user_id": self.user_id}).mappings().one_or_none()
            if authorization is None:
                raise GmailOAuthError("Gmail authorization is invalid or expired")
            session.execute(text("UPDATE oauth_authorizations SET consumed_at = now() WHERE id = :id"), {"id": authorization["id"]})
        token = self._json_post(TOKEN_URL, {"client_id": self.client_id, "client_secret": self.client_secret, "code": code,
            "code_verifier": authorization["code_verifier"], "grant_type": "authorization_code", "redirect_uri": authorization["redirect_uri"]})
        refresh_token = token.get("refresh_token")
        access_token = token.get("access_token")
        if not isinstance(refresh_token, str) or not isinstance(access_token, str):
            raise GmailOAuthError("Google did not return the required OAuth tokens")
        profile = self._json_get(PROFILE_URL, access_token)
        subject, email = profile.get("emailAddress"), profile.get("emailAddress")
        if not isinstance(subject, str) or not isinstance(email, str):
            raise GmailOAuthError("Google did not return a Gmail profile")
        return self.mailboxes.save_gmail_connection(subject, email, [READONLY_SCOPE], refresh_token)

    def refresh_access_token(self, refresh_token: str) -> str:
        token = self._json_post(TOKEN_URL, {"client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": refresh_token, "grant_type": "refresh_token"})
        access_token = token.get("access_token")
        if not isinstance(access_token, str):
            raise GmailOAuthError("Google did not return an access token")
        return access_token

    def current_history_id(self, access_token: str) -> str:
        history_id = self._json_get(PROFILE_URL, access_token).get("historyId")
        if not isinstance(history_id, str):
            raise GmailOAuthError("Google did not return a Gmail history cursor")
        return history_id

    def history_message_ids(self, access_token: str, start_history_id: str) -> tuple[tuple[str, ...], str]:
        page_token: str | None = None
        message_ids: list[str] = []
        final_history_id = start_history_id
        while True:
            query = {"startHistoryId": start_history_id, "historyTypes": "messageAdded"}
            if page_token:
                query["pageToken"] = page_token
            payload = self._json_get(f"{HISTORY_URL}?{urlencode(query)}", access_token)
            history = payload.get("history", [])
            if not isinstance(history, list):
                raise GmailOAuthError("Google returned invalid Gmail history")
            for event in history:
                if not isinstance(event, dict):
                    continue
                for item in event.get("messagesAdded", []):
                    message = item.get("message", {}) if isinstance(item, dict) else {}
                    message_id = message.get("id") if isinstance(message, dict) else None
                    if isinstance(message_id, str):
                        message_ids.append(message_id)
            next_page = payload.get("nextPageToken")
            final = payload.get("historyId")
            if not isinstance(final, str):
                raise GmailOAuthError("Google did not return a Gmail history cursor")
            final_history_id = final
            if not isinstance(next_page, str) or not next_page:
                return tuple(dict.fromkeys(message_ids)), final_history_id
            page_token = next_page

    def _json_post(self, url: str, values: dict[str, str]) -> dict[str, object]:
        return self._request(Request(url, data=urlencode(values).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST"))

    def _json_get(self, url: str, access_token: str) -> dict[str, object]:
        return self._request(Request(url, headers={"Authorization": f"Bearer {access_token}"}))

    def _request(self, request: Request) -> dict[str, object]:
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed Google endpoints
                value = json.loads(response.read().decode())
        except Exception as error:
            raise GmailOAuthError("Google OAuth request failed") from error
        if not isinstance(value, dict):
            raise GmailOAuthError("Google OAuth response was invalid")
        return value


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
