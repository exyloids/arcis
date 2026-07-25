# Gmail OAuth validation

This guide validates the real Gmail-provider boundary using one or more
dedicated Google test accounts. Start with two to demonstrate mailbox
isolation; the application is designed to support more.

## Safety rules

- Do not use a primary personal mailbox for this proof.
- Do not commit OAuth client files, authorization codes, access tokens, or
  refresh tokens.
- Use the read-only Gmail scope only:
  `https://www.googleapis.com/auth/gmail.readonly`.
- Use synthetic test messages. Do not send financial statements or real bank
  alerts through the test accounts.

## Google Cloud setup

1. Create or select a Google Cloud project.
2. Enable **Gmail API**.
3. Configure the OAuth consent screen as **External** and add each dedicated
   Gmail account as a test user while the app is in testing mode.
4. Create a **Desktop app** OAuth client for this foundation validation.
5. Set a loopback redirect URI such as `http://127.0.0.1:8765/callback` if
   your client type requires explicit redirect registration.
6. Put client values in your local ignored `.env`; never copy a downloaded
   Google client JSON file into the repository.

Example local-only `.env` entries:

```dotenv
ARCIS_GMAIL_OAUTH_CLIENT_ID=replace-with-client-id.apps.googleusercontent.com
ARCIS_GMAIL_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/callback
ARCIS_GMAIL_TEST_QUERY=from:(test-sender@example.invalid) newer_than:30d
```

`ARCIS_GMAIL_OAUTH_CLIENT_SECRET` is optional for a public desktop client and
must remain only in local ignored configuration if used.

## Adapter checks

Run the offline contract tests first:

```bash
.venv/bin/python -m unittest tests.gmail_provider_validation.test_gmail_provider_validation -v
```

They verify PKCE, state generation, refresh-token requirements, redacted token
representation, paginated History API discovery, and explicit invalid-cursor
handling without contacting Google.

## Live validation checklist

For each test mailbox, run the interactive validator from the repository root:

```bash
set -a
source .env
set +a
.venv/bin/python -m spikes.gmail_provider_validation.run_live_validation
```

It generates an authorization-code + PKCE request, validates callback state,
exchanges the code, checks the Gmail profile, refreshes the access token in
memory, and pauses while you send a synthetic message for incremental History
API validation. It prints only a masked mailbox identity, message count, and
history cursors; it does not persist or print tokens.

Run it separately for each mailbox. Keep the generated `state` and
`code_verifier` in process memory until the callback is validated.

Record only safe evidence in `docs/STATUS.md`:

1. Provider account identity after OAuth (masked or pseudonymous).
2. Initial history cursor and number of synthetic messages discovered.
3. A newly received synthetic message and the incremental discovery count.
4. A paginated history run, if enough history exists.
5. An invalid-cursor recovery result using an idempotent bounded scan.
6. A forced access-token refresh that succeeds without exposing either token.
7. Independent cursor/result counts for at least two mailboxes.

Do not record message contents, sender display names, authorization URLs,
authorization codes, tokens, or OAuth client secrets.
