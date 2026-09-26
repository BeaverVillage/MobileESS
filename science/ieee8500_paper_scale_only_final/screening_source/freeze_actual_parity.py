"""Freeze the one paper-scale B0 Actual parity result by content hash."""
import json
from pathlib import Path
from forensic import sha, read

HERE = Path(__file__).resolve().parent
OUT = HERE / "actual_b0_regression_paper_2x_retry1_20260920"
TARGET = HERE / "ACTUAL_PIPELINE_PARITY_FREEZE.json"
assert not TARGET.exists()
parity = read(OUT / "PARITY.json")
assert parity["status"] == "PASS"
assert parity["DA"]["status"] == parity["Actual"]["status"] == "PASS"
assert parity["actual_campaign_runs"] == 1 and parity["screening_candidate_Actual_runs"] == 0
files = [OUT / "PARITY.json", OUT / "B0/FINAL_ACTUAL/AC_SUMMARY.json",
         OUT / "B0/CONTINUOUS_VERIFICATION.json",
         OUT / "HISTORICAL_READ_ALIASES.json",
         HERE / "stage_a_strong/BG_0.50000_AIDC_2.00/RESULT.json"]
record = dict(status="FROZEN_PASS", date="2025-05-01", AIDC_absolute_scale=2.,
              BG_scale=.5, PV_scale=.5,
              DA_exact_rho=parity["DA"]["observed_rho"],
              Actual_exact_rho=parity["Actual"]["observed_rho"],
              independent_scopes=True, repeat_Actual_in_screening=False,
              source_files=[dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size) for p in files])
TARGET.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print("ACTUAL_PIPELINE_PARITY_FROZEN", sha(TARGET))
