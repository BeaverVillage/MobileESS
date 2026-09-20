"""Freeze this new case's source and coefficient authority before optimization."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).absolute().parent
ROOT = HERE.parent.parent


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def rec(path):
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)


def main():
    assert read(HERE / "FINAL_CASE_PREFLIGHT.json")["status"] == "PASS"
    assert read(HERE / "COEFFICIENT_GENERATION.json")["status"] == "PASS"
    assert read(HERE / "COEFFICIENT_VALIDATION.json")["status"] == "PASS"
    assert read(HERE / "B0_REPLAY/AC_VALIDATION.json")["status"] == "PASS"
    assert read(HERE / "B0/Fresh/AC_VALIDATION.json")["status"] == "PASS"
    assert read(HERE / "native_solver_io_preflight/PASS.json")["status"] == "PASS"
    prep = read(HERE.parent / "CASE_PREPARATION.json")
    assert all(sha(row["source"]) == row["source_sha256"] for row in prep["source_files"])
    code = sorted(HERE.glob("*.py")) + sorted(HERE.glob("overrides/**/*.py"))
    static = [HERE / name for name in (
        "PRODUCTION_AUTHORIZATION.json", "LAYOUT.json", "PCC_OVERLAY.dss",
        "PCC_OVERLAY_INVENTORY.json", "D1_AEMO_VIC1_FORECAST.json",
        "NORMALIZED_B0_AIDC_POWER.npz", "MAY01_B0_AIDC_POWER.npz",
        "REFERENCE_JOBS.json", "HEADROOM_AUTHORITY.json", "FLEET_AUTHORITY.json",
        "CODE_DIFF.json", "MESS_24_SERVICE_PCC_COLUMN_BINDING.json",
        "FINAL_CASE_PREFLIGHT.json", "COEFFICIENT_GENERATION.json",
        "COEFFICIENT_VALIDATION.json", "AXES.json", "B0_REPLAY/AC_VALIDATION.json",
        "B0_REPLAY/ANCHORS.npz", "B0/Fresh/AC_VALIDATION.json",
    )]
    coefficients = sorted(HERE.glob("coefficients/slot_*/COEFFICIENTS.npz"))
    assert len(coefficients) == 96
    native = sorted((ROOT / "IEEE8500_scalability_20260910/source").rglob("*.dss"))
    assert native
    files = [rec(p) for p in code + static + coefficients + native]
    assert len({r["path"] for r in files}) == len(files)
    data = dict(status="FROZEN", date="2025-05-01", background_scale=.45,
                AIDC_scale=2.1, MESS_scale=2., source_files=prep["source_files"],
                files=files, screening_B1_B2_B3_solution_import=False,
                objective_or_constraint_changes_beyond_scale=False)
    write(HERE / "RECONSTRUCTION_FREEZE_MANIFEST.json", data)
    write(HERE / "ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json", data)
    (HERE / "ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.sha256").write_text(
        sha(HERE / "ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json"), encoding="utf-8")
    write(HERE / "IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json",
          dict(status="IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS", date="2025-05-01",
               scales=dict(BG=.45, AIDC=2.1, MESS=2.), native_feeder_files=len(native),
               coefficients=96, exact_B0_96=True, Fresh_B0_96=True,
               independent_coefficient_perturbation="PASS", solver_IO="PASS",
               input_authority="PASS", source_manifest_SHA=sha(HERE / "ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json")))
    print("FINAL_FREEZE_PASS", len(files), "files", flush=True)


if __name__ == "__main__":
    main()
