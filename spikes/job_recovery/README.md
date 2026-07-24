# Job recovery and contract generation proof

The job proof commits each item checkpoint before processing continues. A
worker crash can therefore be retried safely: committed items are skipped and
remaining items are processed once.

The OpenAPI proof uses the checked-in contract at
`packages/contracts/spec/openapi.json` and generates the TypeScript client at
`apps/web/lib/generated/api-client.ts`.

```bash
python3 scripts/generate_client.py
python3 scripts/generate_client.py --check
python3 -m unittest tests.job_recovery.test_job_recovery -v
```
