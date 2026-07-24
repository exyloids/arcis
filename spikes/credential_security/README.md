# Credential encryption and rotation proof

This proof validates AES-GCM encryption, associated-data binding, ciphertext-
only persistence, key-version rotation, and revocation. It requires the
project's `cryptography` dependency.

```bash
python3 -m unittest tests.credential_security.test_credential_security -v
```

The production adapter will replace the in-memory key map with KMS/Secrets
Manager key wrapping while preserving this interface and its invariants.
