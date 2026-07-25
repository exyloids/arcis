# Sanitized parser fixtures

Only synthetic or fully sanitized fixtures may be committed here. A fixture
must preserve the source format features needed by the parser—headers, column
names, date layouts, money formatting, line ordering, and representative
transaction types—while replacing all personal and financial identifiers.

Do not commit raw `.eml`, PDF, CSV, XLSX, OAuth, password, or account data.
Keep source documents in the ignored `example_transactions/` directory.

For every committed fixture, add an expected normalized result in a sibling
test or expectation file that covers at least:

- transaction date and posted date when available;
- amount, currency, and debit/credit direction;
- source reference or a synthetic equivalent;
- narration/merchant normalization expectation; and
- expected parser outcome or explicit review reason.

Create a local structural catalog without exposing content:

```bash
.venv/bin/python scripts/catalog_samples.py example_transactions
```

The output defaults to `tmp/sample-catalog.json`, which is ignored by Git.

## Initial corpus

The initial corpus deliberately covers ICICI credit-card/account/iMobile alerts,
HDFC UPI alerts, and ICICI/HDFC structured statement rows. These are synthetic
baseline fixtures, not raw copies of the local samples. Their expected
normalized records are stored in `expected/` and validated by the test suite.
