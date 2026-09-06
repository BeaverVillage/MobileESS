from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40d_actual.smoke_report import build

if __name__=="__main__":
    print(build(Path(__file__).resolve().parents[2]))
