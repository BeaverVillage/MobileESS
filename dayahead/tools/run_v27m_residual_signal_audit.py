"""Build V27M state features and evaluate the mandatory residual signal gate."""

from pathlib import Path

from dayahead.ml.safe_flex_r1.residual_gate import evaluate_residual_signal


if __name__ == "__main__":
    evaluate_residual_signal(Path(__file__).resolve().parents[2])
