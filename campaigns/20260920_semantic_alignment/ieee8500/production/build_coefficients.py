"""Generate all 96 IEEE8500 coefficients at this final operating point."""
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"

HERE = Path(__file__).absolute().parent


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def one(slot):
    from electrical_engine import generate_slot
    return generate_slot(slot)


def main():
    assert str(HERE).isascii()
    assert (HERE / "B0_REPLAY/AC_VALIDATION.json").exists()
    started = time.perf_counter()
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(one, t): t for t in range(96)}
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            rows.append(row)
            save(HERE / "COEFFICIENT_PROGRESS.json",
                 dict(status="RUNNING" if len(rows) < 96 else "COMPLETE", slots_completed=len(rows),
                      rows=sorted(rows, key=lambda r: r["slot"])))
            if len(rows) % 8 == 0:
                print("COEFFICIENT_PROGRESS", len(rows), flush=True)
    rows.sort(key=lambda r: r["slot"])
    assert [r["slot"] for r in rows] == list(range(96))
    save(HERE / "COEFFICIENT_GENERATION.json", dict(status="PASS", date="2025-05-01",
         background_scale=.45, AIDC_scale=2.1, MESS_scale=2., slots=rows,
         workers=4, wall_seconds=time.perf_counter() - started,
         screening_coefficient_reuse=False, generated_at_selected_operating_point=True))
    print("COEFFICIENT_GENERATION_PASS", len(rows), flush=True)


if __name__ == "__main__":
    main()
