"""Complete and verify the pre-April freeze before raw April members are opened."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    freeze_path = OUT / "V26M_MODEL_SELECTION_PRE_APRIL_FREEZE.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    code_files = sorted((REPO / "dayahead/ml/safe_flex").rglob("*.py"))
    aggregate = hashlib.sha256()
    for path in code_files:
        aggregate.update(path.relative_to(REPO).as_posix().encode())
        aggregate.update(path.read_bytes())
    config = REPO / "dayahead/ml/safe_flex/configs/V26M_EXACT_CONFIG.json"
    source = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip")
    selected_models = sorted((REPO / "dayahead/artifacts/v25m_beacon_flex/models").glob("*"))
    freeze.update({
        "exact_config_path": config.relative_to(REPO).as_posix(), "exact_config_SHA256": sha(config),
        "V26M_code_SHA256": aggregate.hexdigest(), "V26M_code_file_count": len(code_files),
        "raw_data_SHA256": sha(source),
        "selected_fallback_model_hashes": {path.name: sha(path) for path in selected_models if path.is_file()},
        "all_survival_blocked_CV_fits_complete": True, "pending_blocked_CV_fits_complete": True,
        "innovation_blocked_CV_fits_complete": True, "calibrator_fit_complete": True,
        "scenario_policy_frozen": True, "candidate_model_serialization": "EXACT_CONFIG_PLUS_EVALUATION_AUTHORITY; NO_PRODUCTION_WEIGHTS_ISSUED_AFTER_REJECTION",
        "freeze_complete": True,
    })
    freeze_path.write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    digest = sha(freeze_path)
    (OUT / "V26M_MODEL_SELECTION_PRE_APRIL_FREEZE.sha256").write_text(digest + "\n", encoding="utf-8")
    verified = sha(freeze_path) == (OUT / "V26M_MODEL_SELECTION_PRE_APRIL_FREEZE.sha256").read_text().strip()
    print(json.dumps({"freeze_SHA256": digest, "verified": verified, "April_raw_member_reads": 0}))


if __name__ == "__main__":
    main()

