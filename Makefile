.PHONY: api web test test-integration lint compose-up compose-down

api:
	python3 -m uvicorn apps.api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

test-integration:
	ARCIS_INTEGRATION_DATABASE_URL=postgresql+psycopg://arcis:arcis@localhost:5432/arcis \
		.venv/bin/python -m unittest tests.integration.test_manual_ledger_postgres tests.integration.test_mailboxes_postgres tests.integration.test_sync_jobs_postgres -v

lint:
	python3 -m ruff check apps packages migrations tests spikes

compose-up:
	docker compose -f deploy/compose/docker-compose.yml up -d

compose-down:
	docker compose -f deploy/compose/docker-compose.yml down
