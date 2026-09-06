from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO))
from dayahead.v40e.smoke import prepare,b0_b1
if __name__=='__main__':
    prepare(REPO)
    b0_b1(REPO)
