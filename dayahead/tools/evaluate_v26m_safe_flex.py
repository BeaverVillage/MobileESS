"""Run pre-April comparison, ablation, bootstrap, and freeze serialization."""

from pathlib import Path
import json

from dayahead.ml.safe_flex.evaluate import build_evaluation_artifacts


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    result = build_evaluation_artifacts(repo)
    print(json.dumps({"classification": result["acceptance"]["classification"], "accepted": result["acceptance"]["SAFE_FLEX_PROPOSED_MODEL_ACCEPTED"], "bootstrap": result["comparison"]["seven_day_block_bootstrap_10000"]}, indent=2))


if __name__ == "__main__":
    main()

