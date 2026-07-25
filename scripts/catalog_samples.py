"""Create a local-only, content-free catalog of sensitive parser samples.

The catalog reports file formats and structural email characteristics only. It
does not emit message bodies, subjects, addresses, attachment names, or PDF
text. Its default output location is ignored by Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path


@dataclass(frozen=True)
class EmailStructure:
    has_date: bool
    has_from: bool
    has_html: bool
    has_message_id: bool
    has_plain_text: bool
    attachment_count: int
    subject_fingerprint: str


@dataclass(frozen=True)
class PdfStructure:
    byte_size: int
    encrypted_hint: bool


def catalog_samples(sample_root: Path) -> dict[str, object]:
    """Return only structural facts about `.eml` and `.pdf` files below a root."""
    if not sample_root.is_dir():
        raise ValueError(f"sample root does not exist: {sample_root}")

    emails = [_email_structure(path) for path in sorted(sample_root.rglob("*.eml"))]
    pdfs = [_pdf_structure(path) for path in sorted(sample_root.rglob("*.pdf"))]
    return {
        "email_samples": len(emails),
        "pdf_samples": len(pdfs),
        "email_structure_counts": {
            "with_html": sum(item.has_html for item in emails),
            "with_plain_text": sum(item.has_plain_text for item in emails),
            "with_attachments": sum(item.attachment_count > 0 for item in emails),
            "unique_subject_templates": len({item.subject_fingerprint for item in emails}),
        },
        "pdf_structure_counts": {
            "with_encryption_hint": sum(item.encrypted_hint for item in pdfs),
        },
        "file_extensions": dict(sorted(_extension_counts(sample_root).items())),
        "emails": [asdict(item) for item in emails],
        "pdfs": [asdict(item) for item in pdfs],
    }


def _email_structure(path: Path) -> EmailStructure:
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    subject = str(message.get("Subject", ""))
    return EmailStructure(
        has_date=bool(message.get("Date")),
        has_from=bool(message.get("From")),
        has_html=any(part.get_content_type() == "text/html" for part in message.walk()),
        has_message_id=bool(message.get("Message-ID")),
        has_plain_text=any(part.get_content_type() == "text/plain" for part in message.walk()),
        attachment_count=sum(
            part.get_content_disposition() == "attachment" for part in message.walk()
        ),
        subject_fingerprint=hashlib.sha256(subject.encode("utf-8")).hexdigest(),
    )


def _pdf_structure(path: Path) -> PdfStructure:
    # `/Encrypt` is a conservative, password-free signal, not a PDF parser.
    contents = path.read_bytes()
    return PdfStructure(byte_size=len(contents), encrypted_hint=b"/Encrypt" in contents)


def _extension_counts(sample_root: Path) -> Counter[str]:
    return Counter(
        path.suffix.lower() or "<none>" for path in sample_root.rglob("*") if path.is_file()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("tmp/sample-catalog.json"))
    args = parser.parse_args()

    catalog = catalog_samples(args.sample_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Catalog written without source content: "
        f"{catalog['email_samples']} email samples, {catalog['pdf_samples']} PDF samples."
    )


if __name__ == "__main__":
    main()
