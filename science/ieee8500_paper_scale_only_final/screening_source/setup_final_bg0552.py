"""Create a fresh paper-PCC production tree for the user-frozen scales."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "full_production_paper_BG054688_AIDC240_MESS150"
DEST = HERE / "full_production_paper_BG055200_AIDC240_MESS200"
PAPER = HERE.parent / "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913"
OVERLAY_SHA = "843e9ef83ab200f23ef17d51b3820fb1b504380be419ac0f2519d0ab49104243"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_one(path: Path, old: str, new: str) -> None:
    value = path.read_text(encoding="utf-8")
    assert value.count(old) == 1, (path, old, value.count(old))
    path.write_text(value.replace(old, new), encoding="utf-8")


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    assert not DEST.exists(), DEST
    assert sha(PAPER / "IEEE8500_PCC_Overlay.dss") == OVERLAY_SHA
    DEST.mkdir()
    # Copy code and authority only. Old candidate's outputs stay in SOURCE.
    allowed_suffix = {".py", ".json", ".dss", ".npz"}
    excluded = {
        "PRODUCTION_AUTHORIZATION.json", "PRODUCTION_AUTHORIZATION_PREMATURE.json",
        "PREMATURE_PRODUCTION_DIAGNOSTIC.json", "PRODUCTION_CONTEXT_PREFLIGHT.json",
        "PRODUCTION_CONTEXT_PREFLIGHT_INITIAL.json", "SCALE_OVERRIDES_STAGE.json",
        "MAY01_B0_AIDC_POWER.npz", "NORMALIZED_B0_AIDC_POWER.npz",
        "HEADROOM_CAPACITY_DERIVED_SNAPSHOT.json", "FINAL_SCALE_CANDIDATE_FREEZE.json",
    }
    for src in SOURCE.iterdir():
        if src.is_file() and src.suffix.lower() in allowed_suffix and src.name not in excluded:
            shutil.copy2(src, DEST / src.name)
    shutil.copytree(SOURCE / "overrides", DEST / "overrides")
    shutil.copytree(SOURCE / "authority_read_aliases", DEST / "authority_read_aliases")
    assert sha(DEST / "IEEE8500_PCC_Overlay.dss") == OVERLAY_SHA
    assert sha(DEST / "PCC_Master.dss") == sha(PAPER / "PCC_Master.dss")
    assert sha(DEST / "PCC_OVERLAY_INVENTORY.json") == sha(PAPER / "PCC_OVERLAY_INVENTORY.json")

    with np.load(PAPER / "MAY01_B0_AIDC_POWER.npz") as z:
        power = {key: z[key].copy() for key in z.files}
    for key in ("pcc", "qcc"):
        power[key] *= 2.40 / 2.00
    # IT is a compute schedule, not a physical AIDC power input.
    np.savez_compressed(DEST / "MAY01_B0_AIDC_POWER.npz", **power)

    replace_one(DEST / "electrical_engine.py", "self.ap,self.aq,.54688,self.md", "self.ap,self.aq,.552,self.md")
    replace_one(DEST / "common8500.py", "alpha8500=.54688", "alpha8500=.552")
    replace_one(DEST / "numerical_coefficients.py", "COEFF_HOME=H.parent/'IEEE8500_MAY01_AIDC2X_HOST_REMAP_20260912'", "COEFF_HOME=H")

    base = json.loads((DEST / "PAPER_FLEET_BASE_AUTHORITY.json").read_text(encoding="utf-8"))
    fleet = json.loads((DEST / "FLEET_AUTHORITY.json").read_text(encoding="utf-8"))
    keys = ("active_power_limit_kw", "pcs_kva", "capacity_kwh", "energy_min_kwh",
            "energy_max_kwh", "initial_energy_kwh", "terminal_energy_kwh")
    for key in keys:
        assert abs(fleet["physical"][key] - 1.5 * base["physical"][key]) < 1e-8
        fleet["physical"][key] = 2.0 * base["physical"][key]
    fleet["initial_total_energy_kwh"] = 2.0 * base["initial_total_energy_kwh"]
    fleet["only_scientific_change"] = "P/S/E ratings scaled uniformly 2.00 from the six-unit paper fleet"
    write(DEST / "FLEET_AUTHORITY.json", fleet)

    physics = DEST / "overrides/dayahead/mess_physics.py"
    for old, new in (("CAPACITY_KWH = 1800.0", "CAPACITY_KWH = 2400.0"),
                     ("E_MIN_KWH = 660.0", "E_MIN_KWH = 880.0"),
                     ("E_MAX_KWH = 1620.0", "E_MAX_KWH = 2160.0"),
                     ("E_INITIAL_KWH = 1140.0", "E_INITIAL_KWH = 1520.0"),
                     ("E_TERMINAL_KWH = 1140.0", "E_TERMINAL_KWH = 1520.0"),
                     ("P_LIMIT_KW = 450.0", "P_LIMIT_KW = 600.0"),
                     ("PCS_KVA = 600.0", "PCS_KVA = 800.0"),
                     ("MESS_TERMINAL_ENERGY_MUST_EQUAL_1140_KWH", "MESS_TERMINAL_ENERGY_MUST_EQUAL_1520_KWH")):
        replace_one(physics, old, new)
    replace_one(DEST / "overrides/dayahead/v35/execution.py",
                "energy = np.full((SLOTS, 4), 1140.0, dtype=float)",
                "energy = np.full((SLOTS, 4), 1520.0, dtype=float)")
    code_diff = json.loads((DEST / "CODE_DIFF.json").read_text(encoding="utf-8"))
    for row in code_diff:
        override = DEST / "overrides" / Path(*row["module"].split(".")).with_suffix(".py")
        row["override"] = str(override)
        row["override_sha256"] = sha(override)
        assert sha(Path(row["source"])) == row["source_sha256"]
    write(DEST / "CODE_DIFF.json", code_diff)

    manifest = json.loads((SOURCE / "CLONE_INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    manifest.update(status="FRESH_FINAL_CANDIDATE_CLONE", source_diagnostic=str(SOURCE),
                    target=str(DEST), scaled_aidc_power_sha256=sha(DEST / "MAY01_B0_AIDC_POWER.npz"),
                    source_clone_file_entries_are_historical=True)
    write(DEST / "CLONE_INPUT_MANIFEST.json", manifest)
    freeze = dict(status="FROZEN_FOR_B2_PREFLIGHT", date="2025-05-01", BG_SCALE=.552,
                  AIDC_ABSOLUTE_SCALE=2.40, MESS_SCALE=2.00,
                  MESS_rating=dict(Pmax_kW=600, Smax_kVA=800, capacity_kWh=2400),
                  AIDC_array_multiplier="2.40/2.00", PAPER_PCC_CONFIG_USED=True,
                  RESITING_USED=False, FEEDER_MODIFIED=False, AIDC_DOUBLE_SCALING=False,
                  B2_SEARCH_DOMAIN_CHANGED=False, paper_overlay_sha256=OVERLAY_SHA,
                  prior_diagnostic=str(SOURCE), screening_report_sha256=sha(HERE / "controllability_search_20260920/CONTROLLABILITY_SCREEN_COMPLETE.json"))
    write(DEST / "FINAL_CANDIDATE_FREEZE.json", freeze)
    write(DEST / "PRODUCTION_AUTHORIZATION.json", dict(
        authorized=True, date="2025-05-01", BG_scale=.552, AIDC_absolute_scale=2.40,
        MESS_rating_scale=2.00, workers=1, threads=4, AIDC_search_budget_seconds=14400,
        MESS_no_artificial_work_or_wall_cutoff=True,
        policy_gate="B2 performance preflight before B2; B2 Actual before next policy; B3 only after B2 exact PASS",
        paper_overlay_sha256=OVERLAY_SHA))
    write(DEST / "SETUP_MANIFEST.json", dict(status="READY_FOR_B0_AND_COEFFICIENT_PREFLIGHT",
        source_diagnostic=str(SOURCE), paper_overlay_sha256=OVERLAY_SHA,
        feeder_master_sha256=sha(DEST / "PCC_Master.dss"),
        power_sha256=sha(DEST / "MAY01_B0_AIDC_POWER.npz"),
        fleet_sha256=sha(DEST / "FLEET_AUTHORITY.json"),
        code_diff_sha256=sha(DEST / "CODE_DIFF.json")))
    print(DEST)


if __name__ == "__main__":
    main()
