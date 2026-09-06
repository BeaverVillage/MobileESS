"""Offline exact cache reconstruction; forbidden to solve any optimization model."""
from pathlib import Path
import sys
import argparse
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dayahead.paper_analysis.numeric_snapshot import recover

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--day", action="append")
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    recover(repo, a.day or [f"2025-05-{i:02d}" for i in range(1, 32)],
            repo / "dayahead/artifacts/v40a_bounded_iterative_aidc_mess_coopt")
