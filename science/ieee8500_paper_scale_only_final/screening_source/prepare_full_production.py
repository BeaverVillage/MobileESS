"""Create a separate paper-authority production workspace, without running it."""
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from stage_a_strong import PAPER, HERE, authority_guard, sha

DEST = HERE / "full_production_paper_BG054688_AIDC240_MESS150"
CONFIG = (
    "ADAPTER_DIFF.json", "AIDC_2X_AUTHORITY.json", "AXES.json", "CODE_DIFF.json",
    "D1_AEMO_VIC1_FORECAST.json", "FLEET_AUTHORITY.json", "HEADROOM_AUTHORITY.json",
    "IEEE8500_V41R4_AIDC_BINDING_PASS.json", "IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json",
    "INHERITED_SOURCE_FREEZE.json", "MAPPING_FREEZE.json",
    "MESS_24_SERVICE_PCC_COLUMN_BINDING.json", "PCC_OVERLAY_INVENTORY.json",
    "REFERENCE_JOBS.json", "SCREENING_RULE.json",
)


def copy_once(src, dest):
    assert not dest.exists(), ("PRODUCTION_NAMESPACE_ALREADY_EXISTS", dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    assert sha(src) == sha(dest)
    return {"source": str(src), "destination": str(dest), "sha256": sha(dest)}


def main():
    authority_guard()
    assert not DEST.exists()
    DEST.mkdir()
    files = []
    for src in sorted(PAPER.glob("*.py")):
        files.append(copy_once(src, DEST / src.name))
    for name in CONFIG + ("PCC_Master.dss", "IEEE8500_PCC_Overlay.dss"):
        files.append(copy_once(PAPER / name, DEST / name))
    assert sha(DEST / "IEEE8500_PCC_Overlay.dss") == "843e9ef83ab200f23ef17d51b3820fb1b504380be419ac0f2519d0ab49104243"
    with np.load(PAPER / "MAY01_B0_AIDC_POWER.npz") as z:
        data = {k: z[k].copy() for k in z.files}
    assert "pcc" in data and "qcc" in data
    for key in ("pcc", "qcc"):
        data[key] *= 2.4 / 2.0
    np.savez_compressed(DEST / "MAY01_B0_AIDC_POWER.npz", **data)
    (DEST / "PRODUCTION_AUTHORIZATION.json").write_text(json.dumps(dict(
        authorized=True, date="2025-05-01", policy_order=["B0", "B1", "B2", "B3_A1", "B3_M1", "B3_MF"],
        workers=1, threads=4, AIDC_search_budget_seconds=14400,
        MESS_no_artificial_work_or_wall_cutoff=True,
        BG_scale=.54688, AIDC_absolute_scale=2.4, MESS_rating_scale=1.5,
        paper_overlay_sha256=sha(DEST / "IEEE8500_PCC_Overlay.dss"),
        screening_freeze_sha256=sha(HERE / "FINAL_SCALE_CANDIDATE_FREEZE.json"),
    ), indent=2)+"\n", encoding="utf-8")
    (DEST / "CLONE_INPUT_MANIFEST.json").write_text(json.dumps(dict(
        status="SOURCE_CLONE_ONLY_NOT_PRODUCTION_READY", source_paper=str(PAPER),
        files=files, scaled_aidc_power_sha256=sha(DEST / "MAY01_B0_AIDC_POWER.npz")), indent=2)+"\n", encoding="utf-8")
    print(DEST)


if __name__ == "__main__":
    main()
