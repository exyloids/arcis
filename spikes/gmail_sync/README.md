# Gmail synchronization proof

This spike models the Gmail behavior required by Arcis without real OAuth
credentials or network access:

```text
mailbox-local cursor → incremental history → idempotent source artifacts
                    ↘ invalid cursor → bounded overlap recovery
```

It proves that two mailboxes maintain independent cursors and artifacts, new
messages are fetched incrementally, and an invalid cursor triggers a bounded
recent scan where previously persisted messages are ignored by provider ID.

Run from the repository root:

```bash
python3 spikes/gmail_sync/gmail_sync.py
python3 -m unittest tests.gmail_sync.test_gmail_sync -v
```

The production Gmail adapter will replace `FakeGmailProvider` with OAuth,
provider pagination, provider history IDs, token refresh, rate-limit handling,
and the PostgreSQL mailbox/artifact repositories.
