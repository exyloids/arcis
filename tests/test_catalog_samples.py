import json
import tempfile
import unittest
from pathlib import Path

from scripts.catalog_samples import catalog_samples, main


class SampleCatalogTests(unittest.TestCase):
    def test_catalog_contains_only_structural_email_and_pdf_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret_subject = "Private merchant payment 12345"
            secret_address = "person@example.com"
            (root / "sample.eml").write_text(
                "From: " + secret_address + "\n"
                "Subject: " + secret_subject + "\n"
                "Content-Type: text/plain\n\nSensitive message body",
                encoding="utf-8",
            )
            (root / "statement.pdf").write_bytes(b"%PDF-1.7\n/Encrypt 1 0 R\n")

            catalog = catalog_samples(root)
            serialized = json.dumps(catalog)

            self.assertEqual(catalog["email_samples"], 1)
            self.assertEqual(catalog["pdf_samples"], 1)
            self.assertEqual(catalog["pdf_structure_counts"]["with_encryption_hint"], 1)
            self.assertNotIn(secret_subject, serialized)
            self.assertNotIn(secret_address, serialized)
            self.assertNotIn("Sensitive message body", serialized)

    def test_main_writes_catalog_to_requested_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "catalog.json"
            (root / "sample.eml").write_text("Subject: Generic alert\n\nBody", encoding="utf-8")

            import sys
            from unittest.mock import patch

            with patch.object(sys, "argv", ["catalog_samples", str(root), "--output", str(output)]):
                main()

            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["email_samples"], 1)
