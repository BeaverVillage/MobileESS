"""Reproduce and cross-fit the V27M direct LightGBM base envelope."""

from pathlib import Path

from dayahead.ml.safe_flex_r1.base_reproduction import reproduce_base


if __name__ == "__main__":
    reproduction, _, audit = reproduce_base(Path(__file__).resolve().parents[2])
    if not reproduction["exact_reproduction_PASS"] or not audit["PASS"]:
        raise SystemExit("V27M_BASELINE_REPRODUCTION_FAIL")
