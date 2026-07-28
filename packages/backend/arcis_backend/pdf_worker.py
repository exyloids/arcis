"""Isolated PDF parser entry point. It emits structured data only to its parent process."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

from arcis_backend.ledger import LedgerError
from arcis_backend.statements import ParsedStatement, parse_pdf_statement_in_process


def _serialize(parsed: ParsedStatement) -> dict[str, object]:
    return {
        "parser_name": parsed.parser_name,
        "metadata": {key: _value(value) for key, value in parsed.metadata.items()},
        "rows": [{key: _value(value) for key, value in row.items()} for row in parsed.rows],
    }


def _value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    try:
        password = sys.stdin.buffer.read().decode() or None
        parsed = parse_pdf_statement_in_process(sys.argv[2], Path(sys.argv[1]).read_bytes(), password)
    except LedgerError as error:
        message = str(error).lower()
        if "password" in message:
            code = "password"
        elif "no extractable text" in message:
            code = "no_text"
        elif "no transaction rows" in message:
            code = "unsupported_layout"
        else:
            code = "invalid_pdf"
        print(json.dumps({"error": code}, separators=(",", ":")))
        return 1
    except (OSError, UnicodeDecodeError):
        print(json.dumps({"error": "invalid_pdf"}, separators=(",", ":")))
        return 1
    print(json.dumps(_serialize(parsed), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
