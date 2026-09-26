"""Read-only paper/re-siting authority comparison for the scale-only campaign."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PAPER = ROOT / "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913"
BASE = ROOT / "independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913"
RESITED = ROOT / "RESITING_SCREEN/IEEE8500_LEGAL_MIXED_M1_FULL_MAY01_20260916"
DOCX = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\논문 작성\AIDC-MESS 공동 최적화_김재원_v18.docx")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def record(path):
    path = Path(path)
    return {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def canonical(inventory):
    return {
        f"{row['PCC_role']}:{row['location_id']}": {
            key: row[key]
            for key in ("host_bus", "PCC_bus", "transformer", "phases", "primary_kv", "secondary_kv", "rating_kva")
        }
        for row in inventory
    }


def main():
    paper = canonical(read(PAPER / "PCC_OVERLAY_INVENTORY.json"))
    resited = canonical(read(RESITED / "PCC_OVERLAY_INVENTORY.json"))
    assert len(paper) == len(resited) == 36 and set(paper) == set(resited)
    assert read(PAPER / "RESULT_WITH_ENERGY_EXCEPTION.json")["date"] == "2025-05-01"
    expected = {"B0": .85375, "B1": .85260, "B2": .84452, "B3": .84207}
    result = read(PAPER / "RESULT_WITH_ENERGY_EXCEPTION.json")
    actual = {name: result["policies"][name]["Actual"]["max_phase_line_loading_pu"] for name in expected}
    assert all(round(actual[name], 5) == expected[name] for name in expected)
    assert read(PAPER / "FLEET_AUTHORITY.json")["fleet_ids"] == [f"MESS{i:02}" for i in range(1, 7)]
    assert read(BASE / "SCREENING_RULE.json")["alpha_BG"] == .5
    assert read(BASE / "SCREENING_RULE.json")["AIDC_scale"] == 2.
    assert read(BASE / "SCREENING_RULE.json")["PV_alpha_fixed"] == .5

    # Check the historical frozen manifest against bytes on this machine.
    checked = []
    unavailable = []
    mismatch = []
    for entry in read(PAPER / "INHERITED_SOURCE_FREEZE.json")["files"]:
        path = Path(entry["path"])
        if not path.is_file():
            unavailable.append(entry)
        else:
            observed = sha(path)
            (checked if observed.lower() == entry["sha256"].lower() else mismatch).append(
                {"path": str(path), "expected": entry["sha256"], "observed": observed}
            )
    assert not mismatch

    core = [
        DOCX, PAPER / "RESULT_WITH_ENERGY_EXCEPTION.json", PAPER / "MAPPING_FREEZE.json",
        PAPER / "PCC_OVERLAY_INVENTORY.json", PAPER / "IEEE8500_PCC_Overlay.dss",
        PAPER / "PCC_Master.dss", PAPER / "FLEET_AUTHORITY.json",
        PAPER / "MESS_TRAFFIC_AUTHORITY.json", PAPER / "REFERENCE_JOBS.json",
        PAPER / "D1_AEMO_VIC1_FORECAST.json", PAPER / "MAY01_B0_AIDC_POWER.npz",
        PAPER / "HEADROOM_AUTHORITY.json", PAPER / "SCREENING_RULE.json",
        PAPER / "electrical_engine.py", PAPER / "actual_binding.py",
        PAPER / "availability_gating.py", PAPER / "actual_worker.py",
        BASE / "PCC_Master.dss", BASE / "PCC_OVERLAY_INVENTORY.json",
        ROOT / "IEEE8500_scalability_20260910/source/Master-unbal.dss",
        ROOT / "IEEE8500_scalability_20260910/source/Loads.dss",
        ROOT / "IEEE8500_scalability_20260910/source/Lines.dss",
        ROOT / "IEEE8500_scalability_20260910/source/Transformers.dss",
        ROOT / "IEEE8500_scalability_20260910/source/Regulators.dss",
        ROOT / "IEEE8500_scalability_20260910/source/Capacitors.dss",
        ROOT / "IEEE8500_scalability_20260910/source/CapControls.DSS",
        ROOT / "IEEE8500_scalability_20260910/source/Generators.dss",
        RESITED / "LAYOUT.json", RESITED / "PCC_OVERLAY_INVENTORY.json",
        RESITED / "PCC_OVERLAY.dss",
    ]
    records = [record(p) for p in core if p.is_file()]
    missing_core = [str(p) for p in core if not p.is_file()]
    changes = []
    for key in sorted(paper):
        a, b = paper[key], resited[key]
        if a != b:
            changes.append({"location": key, "paper": a, "resited": b})
    paper_map = hashlib.sha256(json.dumps(paper, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    resited_map = hashlib.sha256(json.dumps(resited, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert paper_map != resited_map
    output = {
        "PAPER_CONFIG_RESTORED": not unavailable and not missing_core,
        "RESITED_PCC_USED": False,
        "FEEDER_MODIFIED": False,
        "SCALE_ONLY_MODIFICATION": True,
        "paper_result": actual,
        "paper_mapping_canonical_sha256": paper_map,
        "resited_mapping_canonical_sha256": resited_map,
        "paper_mapping": paper,
        "resited_mapping": resited,
        "changes": changes,
        "historical_manifest_checked": len(checked),
        "historical_manifest_unavailable": unavailable,
        "historical_manifest_mismatch": mismatch,
        "core_records": records,
        "missing_core": missing_core,
        "paper_B3_Emin_exception_kWh": .0013131923162177372,
    }
    write(HERE / "FORENSIC_AUTHORITY.json", output)
    if unavailable or missing_core:
        raise RuntimeError(f"Paper authority incomplete: {len(unavailable)} manifest paths, {len(missing_core)} core paths")
    print("FORENSIC_PASS", len(checked), "historical records", len(changes), "mapping changes")


if __name__ == "__main__":
    main()
