"""Portable read-only check of the committed six-candidate evidence.

Requires numpy and pandas only. No source repo, optimizer, Gurobi, Actual,
OpenDSS, model, private raw archive or network access is used.
"""
from pathlib import Path
import gzip,hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent

def main():
 report=json.loads((ROOT/'V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.json').read_text(encoding='utf-8'))
 with np.load(ROOT/'MAY_31DAY_Q90_OFFERED_GPU_DEMAND.npz') as d,np.load(ROOT/'B0_RESOURCE_REMATERIALIZATION_STUDY.npz') as z:
  total=d['D_GPU_offered_total'];assert total.shape==(31,96)
  assert np.array_equal(total,d['D_GPU_offered_known_site'].sum(2)+d['D_GPU_offered_UNASSIGNED'])
  assert total.sum()/4==report['offered']['aggregate']['GPU_hours']
  assert total.mean()==report['offered']['aggregate']['mean']
  assert set(report['candidates'])=={'A75','A80','A85','B75','B80','B85'}
  weights=np.array([r['capacity_weight'] for r in report['historical']['rows']]);weights/=weights.sum()
  current=np.array(report['current']['vector'])
  for key,c in report['candidates'].items():
   cap=np.array(c['vector']);n=cap.sum();assert n==c['total'] and np.all(cap>=32) and np.all(cap%4==0)
   assert n==4*int(np.floor(total.mean()/c['target']/4+.5))
   if key.startswith('B'):
    quota=(n-384)/4*weights;base=np.floor(quota).astype(int);res=int((n-384)/4-base.sum())
    for i in sorted(range(12),key=lambda i:(-(quota[i]-base[i]),i))[:res]:base[i]+=1
    assert np.array_equal(cap,32+4*base)
   else:
    quota=n/4*current/current.sum();base=np.floor(quota).astype(int);res=int(n/4-base.sum())
    for i in sorted(range(12),key=lambda i:(-(quota[i]-base[i]),i))[:res]:base[i]+=1
    assert np.array_equal(cap,4*base)
   used=z[key];assert used.shape==(31,96,12) and np.all(used>=0) and np.all(used<=cap)
   h=c['materialized_headroom'];assert np.isclose(h['system']['mean'],(used.sum(2)/n).mean(),atol=1e-14)
   assert h['all12_FULL_fraction']==(used>=cap).all(2).mean()
   for i,site in enumerate(report['current']['rows']):
    v=h['sites'][site['site']];u=used[:,:,i]/cap[i]
    assert np.isclose(v['mean'],u.mean(),atol=1e-14)
    for q in (95,99):assert np.isclose(v['P'+str(q)],np.percentile(u,q),atol=1e-14)
    assert v['FULL_fraction']==(used[:,:,i]>=cap[i]).mean()
   for gang,v in h['whole_job_feasibility'].items():
    destinations=((cap-used)>=int(gang)).sum(2)
    for k in (1,2,3):assert v[f'fraction_at_least_{k}']==(destinations>=k).mean()
   offered=total/n
   for q in (50,90,95,99):assert np.isclose(c['system_offered_occupancy']['P'+str(q)],np.percentile(offered,q),atol=1e-14)
  frame=pd.read_csv(ROOT/'UNASSIGNED_AND_DDAY_COHORT_CLASSIFICATION.csv.gz')
  offered=frame[frame.cohort!='PRE_D00_COMPLETE']
  duration=np.maximum(0,np.minimum(120,offered.nominal_start+offered.duration_slots)-np.maximum(24,offered.nominal_start))
  assert (duration*offered.GPU/4).sum()==total.sum()/4
 assert report['recommendation']['safe_to_apply'] is False
 assert report['production_capacity_applied'] is False and report['Full_May']=='HOLD'
 checks=0
 manifest=ROOT/'PACKAGE_SHA256.json'
 if manifest.exists():
  for row in json.loads(manifest.read_text())['files']:
   p=ROOT/row['path'];assert p.is_file(),p
   assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],p;checks+=1
 result=dict(status='PASS',candidate_count=6,slots_per_candidate=2976,site_slots_per_candidate=35712,
   total_conservation=True,minimum_and_node_rules=True,independent_apportionment=True,
   offered_GPU_hour_conservation=True,per_site_occupancy_and_full_recomputed=True,
   destination_metrics_recomputed=True,artifact_hashes_checked=checks,solver_calls=0,production_writes=0)
 print(json.dumps(result,indent=2))

if __name__=='__main__':main()
