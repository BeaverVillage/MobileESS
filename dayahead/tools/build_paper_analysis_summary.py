"""Read-only paper postprocessor; outputs derived tables without importing optimizers."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dayahead.paper_analysis.summary import build

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    default = Path(__file__).resolve().parents[2] / "dayahead/artifacts/v40a_bounded_iterative_aidc_mess_coopt"
    p.add_argument("--root", type=Path, default=default)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    build(a.root, a.output or a.root / "paper_summary")
    if "gurobipy" in sys.modules:
        raise RuntimeError("PAPER_ANALYSIS_OPTIMIZER_IMPORTED")
