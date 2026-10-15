"""Table V prepare/serial arm command. No automatic retry or overwrite."""
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.table_v_run import DEFAULT,prepare,run_arm

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('operation',choices=['prepare','B0','B1','B2','B3'])
    p.add_argument('--output',type=Path,default=DEFAULT)
    a=p.parse_args()
    result=prepare(a.output) if a.operation=='prepare' else run_arm(a.operation,a.output)
    print('PREPARED' if a.operation=='prepare' else {k:result.get(k) for k in ('arm','status','failed_stage','error','wall_seconds')},flush=True)
