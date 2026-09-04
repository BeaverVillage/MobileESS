"""Generate read-only V26 failure-localization evidence for V27M."""

from pathlib import Path

from dayahead.ml.safe_flex_r1.v26_forensic import write_forensics


if __name__ == "__main__":
    write_forensics(Path(__file__).resolve().parents[2])
