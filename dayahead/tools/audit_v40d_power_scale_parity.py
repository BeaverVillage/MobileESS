from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from dayahead.v40d_actual.power_scale_audit import run
if __name__ == "__main__":
    run(REPO)
