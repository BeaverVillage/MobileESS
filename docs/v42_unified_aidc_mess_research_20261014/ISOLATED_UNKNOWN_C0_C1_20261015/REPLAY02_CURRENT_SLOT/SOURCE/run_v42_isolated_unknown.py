"""Run only the explicit fixed-PR223-MESS C0/C1 16-slot diagnostic."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.isolated_unknown import run_comparison

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015')
    parser.add_argument('--skip-first-event',action='store_true')
    args=parser.parse_args()
    result=run_comparison(args.output,first_event=not args.skip_first_event)
    print(json.dumps({key:result[key] for key in ('status','scope','Native_calls','changed_site_UIDs')},indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
