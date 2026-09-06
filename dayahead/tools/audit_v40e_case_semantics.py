from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO))
from dayahead.v40e.case_semantics import audit
if __name__=='__main__':audit(REPO)
