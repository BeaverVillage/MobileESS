"""Generate candidate-specific 96-slot IEEE8500 derivatives once."""
import hashlib
import json
import time
from pathlib import Path

from electrical_engine import H, generate_slot


def write(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert json.loads((H / "B0/COMPLETE.json").read_text(encoding="utf-8"))["status"] == "PASS"
    assert json.loads((H / "Actual/B0_GATE.json").read_text(encoding="utf-8"))["status"] == "PASS"
    rows = []
    start = time.perf_counter()
    for slot in range(96):
        folder = H / "coefficients" / f"slot_{slot:02}"
        artifact = folder / "COEFFICIENTS.npz"
        generation = folder / "GENERATION.json"
        if artifact.exists() and generation.exists():
            report = json.loads(generation.read_text(encoding="utf-8"))
            assert report["slot"] == slot and report["artifact"]["sha256"] == sha(artifact)
        else:
            assert not folder.exists(), ("INCOMPLETE_SLOT_REQUIRES_AUDIT", folder)
            report = generate_slot(slot)
        rows.append(dict(slot=slot, artifact=str(artifact), sha256=sha(artifact),
                         wall_seconds=report["wall_seconds"]))
        write(H / "COEFFICIENT_PROGRESS.json", dict(status="RUNNING", slots_complete=slot+1,
            total_slots=96, elapsed_seconds=time.perf_counter()-start,
            latest_slot_seconds=report["wall_seconds"]))
        print("COEFFICIENT_SLOT", slot+1, "/96", round(report["wall_seconds"], 2), flush=True)
    write(H / "COEFFICIENT_GENERATION_FINAL.json", dict(status="PASS", slots=rows,
        count=len(rows), wall_seconds=time.perf_counter()-start,
        B0_DA_exact_sha256=sha(H / "B0/DA_exact/AC_VALIDATION.json"),
        paper_overlay_sha256=sha(H / "IEEE8500_PCC_Overlay.dss")))


if __name__ == "__main__":
    main()
