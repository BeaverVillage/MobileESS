"""Search frozen site lineage. Never launches an Actual campaign or placement."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dayahead.v40d_actual.site_audit import run
if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[2]
    print(run(repo, repo / "dayahead/artifacts/v40d_actual_realized_replay/site_authority_audit"))
