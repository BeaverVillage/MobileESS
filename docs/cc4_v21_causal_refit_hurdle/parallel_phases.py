"""Independent cached model fits, four CPU workers and exactly one GPU worker."""
from experiment import *
from concurrent.futures import ProcessPoolExecutor
import time

def worker(arg):
 run,through=arg
 tag,q=forecast(run['family'],run['policy'],run['cadence'],through,run['seed'])
 return tag

def main():
 while not (ROOT/'STAGE_B_FREEZE.json').exists():time.sleep(5)
 runs=read('STAGE_B_FREEZE.json')['runs'];runs=sorted(runs,key=lambda r:r['family'] in ['TFT','DEEPAR'])
 with ProcessPoolExecutor(max_workers=4) as pool:
  for tag in pool.map(worker,[(r,'2024-11-29') for r in runs]):print('CALIBRATION_READY',tag,flush=True)
 while not (ROOT/'FINAL_SELECTION_FREEZE.json').exists():time.sleep(5)
 for r in read('STAGE_A_FREEZE.json')['policy_cadences']:
  if r['tag'] not in [a['tag'] for a in runs]:runs.append(dict(family='LGBM',seed=20260924,tag=r['tag'],policy=r['policy'],cadence=r['cadence']))
 runs=sorted(runs,key=lambda r:r['family'] in ['TFT','DEEPAR'])
 with ProcessPoolExecutor(max_workers=4) as pool:
  for tag in pool.map(worker,[(r,'2025-05-31') for r in runs]):print('EVALUATION_CACHE_READY',tag,flush=True)
 evaluate()
 import report,verify
 report.main();verify.main()

if __name__=='__main__':main()
