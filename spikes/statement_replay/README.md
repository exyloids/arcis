# ICICI statement replay proof

This spike proves the first Arcis data-integrity boundary using a sanitized,
ICICI-style CSV statement:

```text
statement bytes → immutable source artifact → source records
                → canonical transactions → evidence links
```

The same artifact is ingested twice. The second run is identified by the
artifact hash and stable source-record keys, so it adds no source records or
canonical transactions.

The proof repository uses SQLite and Python's standard library so it can run
before the production scaffold exists. It intentionally mirrors the relevant
constraints; the application implementation will use PostgreSQL and Alembic.

Run it from the repository root:

```bash
python3 spikes/statement_replay/statement_replay.py
python3 -m unittest tests.statement_replay.test_statement_replay -v
```

Expected result:

```text
first_import: 3 transactions added
replay: 0 transactions added, 3 duplicates ignored
transaction_count: 3
```
