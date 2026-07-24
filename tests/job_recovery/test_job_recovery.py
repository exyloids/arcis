import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

from spikes.job_recovery.job_recovery import (
    DurableJobRepository,
    SimulatedWorkerCrash,
    run_job,
)

ROOT = Path(__file__).parents[2]


class JobRecoveryTests(unittest.TestCase):
    def test_interrupted_job_resumes_without_reprocessing_committed_items(self):
        connection = sqlite3.connect(":memory:")
        repository = DurableJobRepository(connection)
        items = ["artifact-1", "artifact-2", "artifact-3"]
        with self.assertRaises(SimulatedWorkerCrash):
            run_job(repository, "job-1", items, crash_after=1)

        result = run_job(repository, "job-1", items)

        self.assertEqual(result.processed, 2)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.state, "succeeded")
        self.assertEqual(repository.item_count("job-1"), 3)
        self.assertEqual(repository.state("job-1"), "succeeded")
        connection.close()

    def test_openapi_client_is_generated_without_drift(self):
        generator = ROOT / "scripts/generate_client.py"
        subprocess.run([sys.executable, str(generator)], check=True, cwd=ROOT)
        subprocess.run([sys.executable, str(generator), "--check"], check=True, cwd=ROOT)
        generated = (ROOT / "apps/web/lib/generated/api-client.ts").read_text()
        self.assertIn("export interface HealthResponse", generated)
        self.assertIn("export async function getHealth", generated)


if __name__ == "__main__":
    unittest.main()
