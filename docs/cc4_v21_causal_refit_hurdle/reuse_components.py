"""Exact cache reuse for identical hurdle/burst pooled components, never outcomes.

Atomic directory publication avoids touching a fit already started by the driver.
This reduces duplicate computation; architectures and predictions are unchanged.
"""
from common import *
import shutil,time

def main():
 ledger=[]
 while not (ROOT/'EVALUATION_COMPLETE.json').exists():
  for source in (ROOT/'fits').glob('HURDLE_*/*/MEMBERSHIP.json'):
   parent=source.parent
   if not list(parent.glob('PREDICTION_*.json')):continue
   target=parent.parent.parent/parent.parent.name.replace('HURDLE_','BURST_EXPERT_',1)/parent.name
   if target.exists():continue
   staging=target.with_name(target.name+'.reuse-staging');staging.mkdir(parents=True,exist_ok=True)
   files=[source,*parent.glob('positive_*.txt.gz'),parent/'occurrence.txt.gz']
   require(len(files)==12 and all(p.exists() for p in files),'INCOMPLETE_SOURCE_COMPONENTS')
   for p in files:shutil.copyfile(p,staging/p.name)
   try:staging.rename(target)
   except FileExistsError:continue
   ledger.append(dict(source=str(parent.relative_to(ROOT)),target=str(target.relative_to(ROOT)),time=now(),
    files={p.name:sha(p) for p in files},same_training_policy_seed=True))
   dump('IDENTICAL_COMPONENT_CACHE_REUSE.json',ledger)
  time.sleep(5)

if __name__=='__main__':main()
