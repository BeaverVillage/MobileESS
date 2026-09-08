"""Portable, standard-library-only validation of the frozen screening evidence."""
from pathlib import Path
import gzip
import hashlib
import json
import math

DAYS = {f"2025-05-{i:02}" for i in range(1, 32)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def day_pass(slots):
    require(len(slots) == 96, "missing slot")
    require(all(len(s) == 6 and all(math.isfinite(v) for v in s) for s in slots), "invalid slot")
    return all(s[0] == 1 and s[1] >= .95 and s[2] <= 1.05
               and all(v < 1 for v in s[3:]) for s in slots)


def select(rows, alphas):
    pairs = [(r["day"], r["alpha_BG"]) for r in rows]
    require(len(pairs) == len(set(pairs)), "duplicate day/alpha")
    require(set(pairs) == {(d, a) for d in DAYS for a in alphas}, "incomplete candidate coverage")
    eligible = [a for a in alphas if all(r["PASS"] for r in rows if r["alpha_BG"] == a)]
    return max(eligible) if eligible else None


def validate(root):
    root = Path(root).resolve()
    read = lambda p: json.loads((root / p).read_text(encoding="utf-8"))
    manifest = read("BUNDLE_MANIFEST.json")
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        require(path.is_relative_to(root), "manifest path escapes bundle")
        data = path.read_bytes()
        require(len(data) == expected["bytes"] and hashlib.sha256(data).hexdigest() == expected["sha256"],
                "file hash mismatch: " + name)
    ledger = read("DAILY_RESULTS.json")
    projection = json.loads(gzip.decompress((root / "SLOT_EXTREMA.json.gz").read_bytes()))
    witnesses = {(r["day"], r["alpha_BG"]): r for r in projection["trajectories"]}
    require(len(witnesses) == len(projection["trajectories"]) == len(ledger) == 279, "trajectory count")
    for row in ledger:
        evidence = witnesses[(row["day"], row["alpha_BG"])]
        slots = evidence["slots"]
        require(evidence["source_array_sha256"] == row["source_array_sha256"], "array lineage")
        require(day_pass(slots) == row["PASS"], "strict eligibility mismatch")
        require(sum(s[0] for s in slots) == row["convergence_count"] == 96, "convergence mismatch")
        for col, key in enumerate(("Vmin", "Vmax", "rho_max", "transformer_current", "transformer_kVA"), 1):
            value = (min if col == 1 else max)(s[col] for s in slots)
            require(value == row[key], "daily extreme mismatch: " + key)
        require(len(evidence["regulator_taps"]) == 96 and all(len(t) == 7 for t in evidence["regulator_taps"]), "tap axis")
        require(len(evidence["capacitor_states"]) == 96 and all(c == [1, 1, 1, 1] for c in evidence["capacitor_states"]), "fixed shunt state")
    for stage in manifest["rounds"]:
        rows = [r for r in ledger if r["round"] == stage["round"]]
        chosen = select(rows, stage["candidate_alphas"])
        require(chosen == stage["selected_alpha_BG"], "round selection mismatch")
        report = read(stage["report"])
        require(report["selected_alpha_BG"] == chosen, "report selection mismatch")
        for group in report["groups"]:
            rr = sorted((r for r in rows if r["alpha_BG"] == group["alpha_BG"]), key=lambda r: r["day"])
            failed = [r for r in rr if not r["PASS"]]
            require(group["PASS_days"] == 31 - len(failed) and group["FAIL_days"] == len(failed), "day counts")
            require(group["first_failing_day"] == (failed[0]["day"] if failed else None), "first failing day")
            require(group["first_failing_constraints"] == (failed[0]["limiting_constraints"] if failed else []), "limiting constraint")
        protocol = read(f'rounds/{stage["round"]}/PREDECLARED_PROTOCOL.json')
        original = protocol["runner"]
        archived = next(r for r in manifest["original_copies"] if r["original"] == original["path"])
        require(archived["sha256"] == original["sha256"], "runner source seal")
    selected = select(ledger, manifest["tested_alphas"])
    require(selected == manifest["selected_alpha_BG"] == 1.15, "global selection mismatch")
    return {"status": "PASS", "trajectories": 279, "converged_slots": 26784,
            "selected_alpha_BG": selected, "additional_OpenDSS_calls": 0}


if __name__ == "__main__":
    print(json.dumps(validate(Path(__file__).parent), indent=2))
