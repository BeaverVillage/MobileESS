from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from dayahead.v40e.audit import seal,reproduce_old_cache
if __name__=='__main__':
    seal(REPO)
    reproduce_old_cache(REPO)
