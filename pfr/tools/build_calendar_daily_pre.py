"""Build a canonical independent-daily PRE manifest for a frozen date range."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path

from pfr.daily import build_calendar_daily_pre_artifacts


def atomic_write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--authority-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.days <= 31:
        parser.error("--days must be in [1, 31]")
    dates = tuple(
        (args.start_date + timedelta(days=offset)).isoformat()
        for offset in range(args.days)
    )
    manifest, certificate = build_calendar_daily_pre_artifacts(
        args.authority_sha256,
        calendar_dates=dates,
        campaign_id=args.campaign_id,
        schema_prefix=args.campaign_id.replace("-", "_").upper(),
    )
    args.output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_root / "DAILY_CANONICAL_PRE_MANIFEST.json"
    certificate_path = args.output_root / "DAILY_INITIAL_STATE_IDENTITY_CERTIFICATE.json"
    atomic_write_json(manifest_path, manifest)
    atomic_write_json(certificate_path, certificate)
    print(
        json.dumps(
            {
                "status": "PASS",
                "dates": len(dates),
                "manifest": str(manifest_path),
                "certificate": str(certificate_path),
            }
        )
    )


if __name__ == "__main__":
    main()
