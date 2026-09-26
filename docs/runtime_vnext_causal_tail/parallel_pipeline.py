"""Compute independent issue fits concurrently; selection/calibration stay sequential."""
from experiment import *
from concurrent.futures import ProcessPoolExecutor
import time

def worker(args):
 t,evaluation=args;a=read('STAGE_A_FREEZE.json')
 forecast('MOE',a['window'],a['rate'],a['decay'],t)
 forecast('LGBM',a['window'],a['rate'],a['decay'],t)
 if evaluation:forecast('MOE','120',.05,'current_decay',t)
 return str(t)

def main():
 while not (ROOT/'STAGE_A_FREEZE.json').exists():time.sleep(5)
 issues=pd.read_csv(ROOT/'ISSUES.csv');issues.issue_time=pd.to_datetime(issues.issue_time,utc=True)
 selected=issues[issues.role.isin(['TRAIN','DEVELOPMENT','CALIBRATION'])]
 with ProcessPoolExecutor(max_workers=2) as pool:
  for t in pool.map(worker,[(t,False) for t in selected.issue_time]):print('SELECTION_FITS_READY',t,flush=True)
 stage_b()
 with ProcessPoolExecutor(max_workers=2) as pool:
  for t in pool.map(worker,[(t,True) for t in issues.issue_time]):print('FROZEN_FITS_READY',t,flush=True)
 evaluate()
 import report,verify
 report.main();verify.main()

if __name__=='__main__':main()
