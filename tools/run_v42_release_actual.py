"""RC01 diagnostic entry; never starts a Planning/native optimization."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.release_actual import run_comparison

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/AIDC')
    p.add_argument('--skip-first-event',action='store_true');a=p.parse_args()
    result=run_comparison(a.output,first_event=not a.skip_first_event)
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
