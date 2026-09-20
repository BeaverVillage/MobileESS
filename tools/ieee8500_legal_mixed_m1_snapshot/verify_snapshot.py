"""Read-only archive verification; does not import runtime adapters or start solvers."""
import ast, hashlib, json
from pathlib import Path
ROOT = Path(__file__).absolute().parent

def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def main():
    manifest = read(ROOT / "MANIFEST.json")
    expected = set()
    for row in manifest["files"]:
        p = ROOT / row["path"]
        assert p.resolve().is_relative_to(ROOT.resolve())
        assert row["path"] not in expected
        expected.add(row["path"])
        body = p.read_bytes()
        assert len(body) == row["bytes"], p
        assert hashlib.sha256(body).hexdigest() == row["sha256"], p
        if p.suffix == ".json": read(p)
        if p.suffix == ".py": ast.parse(body.decode("utf-8-sig"), filename=str(p))
    actual = {p.relative_to(ROOT).as_posix() for p in (ROOT / "files").rglob("*") if p.is_file()}
    assert actual == expected, actual ^ expected
    run = ROOT / "files/RESITING_SCREEN/IEEE8500_LEGAL_MIXED_M1_FULL_MAY01_20260916"
    for policy, rho in [("B0", .9815501233047021), ("B1", .9800703763390655)]:
        report = read(run / "Actual_B012" / policy / "COMPLETE.json")
        assert report["AC_feasible"] and report["independent_replay_PASS"]
        assert abs(report["summary"]["max_phase_line_loading_pu"] - rho) < 1e-12
    assert read(run / "B2/Fresh/AC_VALIDATION.json")["status"] == "PASS"
    assert not (run / "Actual_B012/B2/COMPLETE.json").exists()
    assert not (run / "B3/COMPLETE.json").exists()
    assert read(run / "Actual_B012/STATUS.json")["status"] == "PAUSED_USER"
    checkpoint = read(run / "Actual_B012/B2/Q_ACCEPTED_CHECKPOINT.json")
    events = read(run / "Actual_B012/B2/Q_CONTROL_EVENTS.json")
    assert checkpoint["slots"] == len(events) == 32
    assert checkpoint["Q"] == [event["Q_accepted"] for event in events]
    proof = read(run / "diagnostics/K200_PERFORMANCE/PROPAGATED_SEED_PROOF.json")
    assert proof["status"] == "PASS"
    assert all(sample["closed_certificate"] for sample in proof["samples"])
    print(f"PASS: {len(expected)} files; hashes, syntax, JSON, partial-result labels and 32-slot checkpoint")

if __name__ == "__main__":
    main()
