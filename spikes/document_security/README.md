# Protected-document processing proof

This proof sends a synthetic encrypted document and its temporary password to
an isolated subprocess through stdin. The password is not placed in command
arguments, environment variables, files, or returned telemetry.

```bash
python3 -m unittest tests.document_security.test_document_security -v
```

The production parser will use PyMuPDF/PDF-specific extraction in the same
boundary, with resource limits and no outbound network access.
