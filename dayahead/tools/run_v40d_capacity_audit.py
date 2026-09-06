"""Static 124-case binding audit. Does not execute Actual cases."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40d_actual.capacity_audit import static_audit

if __name__ == "__main__":
    repo=Path(__file__).resolve().parents[2]
    print(static_audit(repo,repo/"dayahead/artifacts/v40d_actual_realized_replay/capacity_audit"))
