"""Only explicitly requested smoke is enabled; no full-campaign switch exists."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40d_actual.runner import smoke
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--smoke",action="store_true",required=True)
    p.add_argument("--day",default="2025-05-01")
    p.add_argument("--case",action="append",choices=["B0","B1","B2","B3"])
    a=p.parse_args()
    smoke(Path(__file__).resolve().parents[2],a.day,tuple(a.case or ["B0","B1","B2","B3"]))
