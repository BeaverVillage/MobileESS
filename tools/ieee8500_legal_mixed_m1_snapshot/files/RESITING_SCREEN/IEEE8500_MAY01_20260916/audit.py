from engine import *
import proxy as pr
from types import SimpleNamespace
import pandas as pd
from dayahead.v38.authority import load_wan_authority
from dayahead.v41r1.migration import FrozenWanView
from headroom_authority import capacity_binding,install_power_binding
from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
from dayahead.v41r1.feasible_seed import job_audit
install_power_binding()
from dayahead.v39a.power import site_it_power_kw

def main():
 source=read(H/'SOURCE_MANIFEST.json');checks=[dict(**r,unchanged=original.sha(Path(r['path']))==r['sha256']) for r in source];assert all(r['unchanged'] for r in checks);save(H/'SOURCE_CONSERVATION.json',checks)
 layout=read(H/'placements/legal_mixed_M1/LAYOUT.json');old=Engine(H/'audit_old_runtime');new=ResiteEngine(layout,H/'audit_new_runtime');a=s.old.configs(old.d);b=s.old.configs(new.d)
 def native(n):return not any(x in n for x in ['pcc8500','resite_','op8500','fast_mess'])
 a={k:v for k,v in a.items() if native(k)};b={k:v for k,v in b.items() if native(k)}
 diff=[k for k in set(a)|set(b) if a.get(k)!=b.get(k)];assert not diff,diff
 assert old.loads==new.loads
 save(H/'NATIVE_PHYSICAL_AUTHORITY_AUDIT.json',dict(status='PASS',native_element_count=len(a),old_hash=s.frozen.digest(a),new_hash=s.frozen.digest(b),native_load_count=len(new.loads),native_load_allocation_identical=True,unchanged=['native topology','native load P/Q/phase/model','native line/transformer impedance and ratings','native regulator/capacitor controls'],allowed_change='12 AIDC PCC host mapping; 6 MESS station mapping; authorized MESS interface voltage and phase adaptation; identical P/S/E'))
 old.close();new.close()
 # Refine candidate eligibility before final reporting. Extra excluded probes
 # remain diagnostic measurements, never selected physical candidates.
 candidates=read(H/'SENSITIVITY_CANDIDATES.json');rejected=[c for c in candidates if 'hvmv' in c['bus'] or '_cap' in c['bus']];good=[c for c in candidates if c not in rejected]
 save(H/'ADMISSIBLE_SENSITIVITY_CANDIDATES.json',good);save(H/'INTERNAL_PROBE_REJECTIONS.json',rejected)
 inventory=read(H/'NATIVE_BUS_INVENTORY.json')
 for row in inventory:
  if 'hvmv' in row['bus'] or '_cap' in row['bus']:
   row.update(AIDC_candidate=False,MESS_original_interface_candidate=False,MESS_phase_adapted_candidate=False,exclusion='source / transformer / capacitor internal; excluded from final candidate pool')
 save(H/'FINAL_NATIVE_CANDIDATE_INVENTORY.json',inventory)
 for path in (H/'placements').glob('*/LAYOUT.json'):
  ll=read(path);assert len(ll['aidc'])==len(set(ll['aidc']))==12;assert len(ll['mess'])==len({c['bus'] for c in ll['mess']})==6
  assert not any('hvmv' in x or '_cap' in x or '_int' in x or x.startswith('_') for x in ll['aidc']+[c['bus'] for c in ll['mess']])
 dom=read(pr.REPO/'frozen_artifacts/v41r4_may/audit/2025-05-01/domain/DAILY_DOMAIN_AUTHORITY.json');cap=capacity_binding(read(dom['capacity']['path']),read(dom['rack']['path']));wan=FrozenWanView(load_wan_authority(pr.REPO))
 weather=pd.read_parquet(ROOT/'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/may_2025/days/2025-05-01/gfs_d1_weather.parquet');params=load_c1(pr.REPO/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json');tables={}
 for site,n in cap.site_capacity.items():
  it=np.array([float(site_it_power_kw(n,g)) for g in range(n+1)]);tables[site]=2*np.array([exact_c1_pcc_kw(it,float(w.t_wb_c),float(w.rh_pct),params) for w in weather.itertuples()])
 rows=[];paths=[ROOT/'independent_screening/IEEE8500_FAST_SCALE_20260916/B_DC_1',H/'placements/legal_mixed_M1/B1_R2/B_DC_1',H/'placements/legal_mixed_M1/B3/B_DC_1']
 for path in paths:
  jobs=read(path/'JOBS.json');check,power=job_audit(jobs,SimpleNamespace(capacity=cap,wan=wan,tables=tables))
  with np.load(path/'POWER.npz') as z:diff=float(np.max(abs(power['pcc']-z['pcc'])))
  assert check['status']=='PASS' and diff<1e-8
  rows.append(dict(path=str(path),status='PASS',PCC_reconstruction_max_abs_kw=diff,per_GPU_power_law_unchanged=True,job_audit=check,migration_jobs=sum(j.get('migration_selected',False) for j in jobs)))
 save(H/'INDEPENDENT_WORKLOAD_AUDIT.json',rows);print('NATIVE AUTHORITY / ORIGINAL SOURCE HASHES / JOB-WAN-RESOURCE-POWER PASS',flush=True)
if __name__=='__main__':main()
