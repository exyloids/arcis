"""Protected-document processing proof.

The worker receives bytes and a password through stdin only. The password is
not part of argv, environment variables, files, Redis/Celery payloads, or
telemetry. Production PDF extraction will use PyMuPDF inside this same
isolated-subprocess boundary.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from spikes.credential_security.credential_security import require_cryptography


@dataclass(frozen=True)
class ProtectedDocument:
    nonce_b64: str
    ciphertext_b64: str


def _password_key(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).digest()


def create_protected_document(content: bytes, password: str) -> ProtectedDocument:
    aes_gcm = require_cryptography()
    nonce = os.urandom(12)
    ciphertext = aes_gcm(_password_key(password)).encrypt(nonce, content, b"arcis-document-proof")
    return ProtectedDocument(
        nonce_b64=base64.b64encode(nonce).decode("ascii"),
        ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
    )


def _worker_decrypt(request: dict[str, str]) -> None:
    aes_gcm = require_cryptography()
    document = ProtectedDocument(request["nonce"], request["ciphertext"])
    plaintext = aes_gcm(_password_key(request["password"])).decrypt(
        base64.b64decode(document.nonce_b64),
        base64.b64decode(document.ciphertext_b64),
        b"arcis-document-proof",
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "content_sha256": hashlib.sha256(plaintext).hexdigest(),
                "bytes_extracted": len(plaintext),
            },
            sort_keys=True,
        ),
        flush=True,
    )


def process_protected_document(document: ProtectedDocument, password: str) -> dict[str, object]:
    request = {
        "nonce": document.nonce_b64,
        "ciphertext": document.ciphertext_b64,
        "password": password,
    }
    process = subprocess.run(
        [sys.executable, __file__, "--worker"],
        input=json.dumps(request).encode("utf-8"),
        capture_output=True,
        timeout=10,
        check=False,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(Path(__file__).parents[2]),
        },
    )
    if process.returncode != 0:
        raise ValueError("protected document processing failed")
    return json.loads(process.stdout.decode("utf-8"))


if __name__ == "__main__" and len(sys.argv) == 2 and sys.argv[1] == "--worker":
    _worker_decrypt(json.load(sys.stdin))
