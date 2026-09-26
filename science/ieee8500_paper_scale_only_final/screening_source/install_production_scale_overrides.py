"""Apply only authorized P/S/E and solver-budget changes to paper modules."""
import json
import shutil
from pathlib import Path

from stage_a_strong import PAPER, HERE, sha

DEST = HERE / "full_production_paper_BG054688_AIDC240_MESS150"
PREFLIGHT = PAPER.parent / "IEEE8500_MAY01_MESS6_PREFLIGHT_20260913"


def replace_exact(path, old, new):
    s = path.read_text(encoding="utf-8")
    assert s.count(old) == 1, (path, old, s.count(old))
    path.write_text(s.replace(old, new), encoding="utf-8")


def main():
    base = DEST / "PAPER_FLEET_BASE_AUTHORITY.json"
    assert not base.exists()
    shutil.copy2(DEST / "FLEET_AUTHORITY.json", base)
    fleet = json.loads(base.read_text(encoding="utf-8"))
    assert fleet["physical"] == dict(active_power_limit_kw=300., pcs_kva=400.,
        capacity_kwh=1200., energy_min_kwh=440., energy_max_kwh=1080.,
        initial_energy_kwh=760., terminal_energy_kwh=760.,
        charge_efficiency=.95, discharge_efficiency=.95)
    for key in ("active_power_limit_kw", "pcs_kva", "capacity_kwh", "energy_min_kwh",
                "energy_max_kwh", "initial_energy_kwh", "terminal_energy_kwh"):
        fleet["physical"][key] *= 1.5
    fleet["initial_total_energy_kwh"] *= 1.5
    fleet["production_optimization_authorized"] = True
    fleet["only_scientific_change"] = "P/S/E ratings scaled uniformly 1.50 from the six-unit paper fleet"
    fleet["paper_base_authority_sha256"] = sha(base)
    (DEST / "FLEET_AUTHORITY.json").write_text(json.dumps(fleet, indent=2)+"\n", encoding="utf-8")

    rows = json.loads((DEST / "CODE_DIFF.json").read_text(encoding="utf-8"))
    for row in rows:
        rel = Path(*row["module"].split(".")).with_suffix(".py")
        source_override = PREFLIGHT / "overrides" / rel
        assert source_override.is_file() and sha(source_override) == row["override_sha256"]
        dest = DEST / "overrides" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_override, dest)
        row["paper_override_sha256"] = row["override_sha256"]
        row["override"] = str(dest)
    physics = DEST / "overrides/dayahead/mess_physics.py"
    for old, new in (("CAPACITY_KWH = 1200.0", "CAPACITY_KWH = 1800.0"),
                     ("E_MIN_KWH = 440.0", "E_MIN_KWH = 660.0"),
                     ("E_MAX_KWH = 1080.0", "E_MAX_KWH = 1620.0"),
                     ("E_INITIAL_KWH = 760.0", "E_INITIAL_KWH = 1140.0"),
                     ("E_TERMINAL_KWH = 760.0", "E_TERMINAL_KWH = 1140.0"),
                     ("P_LIMIT_KW = 300.0", "P_LIMIT_KW = 450.0"),
                     ("PCS_KVA = 400.0", "PCS_KVA = 600.0")):
        replace_exact(physics, old, new)
    # This is an error label only; its value must match the scaled terminal E.
    replace_exact(physics, "MESS_TERMINAL_ENERGY_MUST_EQUAL_760_KWH",
                  "MESS_TERMINAL_ENERGY_MUST_EQUAL_1140_KWH")
    execution = DEST / "overrides/dayahead/v35/execution.py"
    replace_exact(execution, "energy = np.full((SLOTS, 4), 760.0, dtype=float)",
                  "energy = np.full((SLOTS, 4), 1140.0, dtype=float)")
    # Gurobi's default infinity is 1e100; these are not finite work cutoffs.
    contracts = DEST / "overrides/dayahead/v35/contracts.py"
    replace_exact(contracts, "WORK_LIMIT_TIERS = (60.0, 180.0, 300.0)",
                  "WORK_LIMIT_TIERS = (1.0e100,)")
    for row in rows:
        row["override_sha256"] = sha(row["override"])
        assert sha(row["source"]) == row["source_sha256"]
    (DEST / "CODE_DIFF.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    manifest = dict(status="SCALE_OVERRIDES_STAGED_NOT_PRODUCTION_READY",
                    paper_base_fleet_sha256=sha(base), scaled_fleet_sha256=sha(DEST / "FLEET_AUTHORITY.json"),
                    overrides=[dict(module=r["module"], source_sha256=r["source_sha256"],
                                    paper_override_sha256=r["paper_override_sha256"],
                                    scaled_override_sha256=r["override_sha256"]) for r in rows],
                    unchanged_efficiency=True, unchanged_mobility_energy=True,
                    unchanged_station_identities=True, MESS_rating_scale=1.5)
    (DEST / "SCALE_OVERRIDES_STAGE.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print("SCALE_OVERRIDES_STAGED", len(rows))


if __name__ == "__main__":
    main()
