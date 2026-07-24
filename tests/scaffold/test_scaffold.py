import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]


class ScaffoldTests(unittest.TestCase):
    def test_required_scaffold_paths_exist(self):
        required = (
            "pyproject.toml",
            "alembic.ini",
            "migrations/env.py",
            "migrations/versions/0001_initial.py",
            "apps/api/main.py",
            "apps/api/Dockerfile",
            "apps/web/package.json",
            "apps/web/app/page.tsx",
            "deploy/compose/docker-compose.yml",
            ".github/workflows/ci.yml",
        )
        for relative_path in required:
            with self.subTest(relative_path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())

    def test_web_package_has_required_scripts(self):
        package = json.loads((ROOT / "apps/web/package.json").read_text())
        self.assertEqual(set(package["scripts"]), {"dev", "build", "start", "lint"})
        self.assertIn("next", package["dependencies"])

    def test_initial_migration_contains_authoritative_tables(self):
        migration = (ROOT / "migrations/versions/0001_initial.py").read_text()
        for table in (
            "users",
            "financial_accounts",
            "source_artifacts",
            "source_records",
            "transactions",
            "transaction_evidence",
            "jobs",
            "audit_events",
        ):
            with self.subTest(table=table):
                self.assertIn(f"CREATE TABLE {table}", migration)


if __name__ == "__main__":
    unittest.main()
