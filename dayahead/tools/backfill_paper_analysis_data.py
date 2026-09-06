"""Export accepted raw results; requires exact numeric snapshots first."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dayahead.paper_analysis.backfill import run

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--day", action="append")
    a = p.parse_args()
    run(Path(__file__).resolve().parents[2], days=a.day)
