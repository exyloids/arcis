import hashlib
import unittest

from spikes.credential_security.credential_security import require_cryptography
from spikes.document_security.document_security import (
    create_protected_document,
    process_protected_document,
)


class ProtectedDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            require_cryptography()
        except RuntimeError as exc:
            raise unittest.SkipTest(str(exc)) from exc

    def test_password_is_used_only_for_private_subprocess_transport(self):
        content = b"synthetic statement content"
        password = "temporary-password-not-for-persistence"
        document = create_protected_document(content, password)
        result = process_protected_document(document, password)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["bytes_extracted"], len(content))
        self.assertEqual(result["content_sha256"], hashlib.sha256(content).hexdigest())
        self.assertNotIn(password, repr(result))

    def test_wrong_password_fails_closed(self):
        document = create_protected_document(b"content", "correct-password")
        with self.assertRaises(ValueError):
            process_protected_document(document, "wrong-password")


if __name__ == "__main__":
    unittest.main()
