"""Build the frozen V27M aggregate temporal reference envelope."""

from pathlib import Path

from dayahead.ml.safe_flex_r1.aggregate_reference import build_reference_authority


if __name__ == "__main__":
    _, validation = build_reference_authority(Path(__file__).resolve().parents[2])
    if not validation["PASS"]:
        raise SystemExit("V27M_AGGREGATE_REFERENCE_VALIDATION_FAIL")
