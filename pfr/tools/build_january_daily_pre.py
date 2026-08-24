"""Materialize the v13.2 January daily PRE manifest and identity certificate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from pfr.daily import build_daily_pre_artifacts


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-document-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    manifest, certificate = build_daily_pre_artifacts(args.authority_document_sha256)
    write_json_atomic(args.output_root / "JAN2025_DAILY_CANONICAL_PRE_MANIFEST.json", manifest)
    write_json_atomic(
        args.output_root / "JAN2025_DAILY_INITIAL_STATE_IDENTITY_CERTIFICATE.json", certificate
    )
    print(json.dumps(certificate, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
