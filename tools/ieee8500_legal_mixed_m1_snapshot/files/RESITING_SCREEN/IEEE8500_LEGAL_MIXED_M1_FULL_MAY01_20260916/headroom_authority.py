"""Capacity-only resource authority with frozen idle/dynamic IT power law."""
import sys,json,hashlib
from pathlib import Path
from decimal import Decimal
H=Path(__file__).absolute().parent
PHYSICAL=[268,136,268,136,336,268,136,268,136,268,136,268]
OLD=[80,40,80,40,100,80,40,80,40,80,40,80]
NEW=[v//2 for v in PHYSICAL]
SITES=[f'AIDC{i:02}' for i in range(1,13)]
def install_power_binding():
 import dayahead.v39a.power as power
 from dayahead.v39a.contracts import IDLE_W_PER_GPU,CENTER_SWING_W_PER_GPU
 original=power.site_it_power_kw
 if getattr(original,'headroom_binding',False):return
 lookup=dict(zip(NEW,OLD));assert len(lookup)==3
 def frozen_power(site_capacity_gpu,active_gpu):
  n=int(site_capacity_gpu);g=int(active_gpu)
  if n not in lookup:return original(n,g)
  if not 0<=g<=n:raise ValueError('HEADROOM_GPU_RANGE')
  return (Decimal(lookup[n])*IDLE_W_PER_GPU+Decimal(g)*CENTER_SWING_W_PER_GPU)/Decimal(1000)
 frozen_power.headroom_binding=True
 for module in list(sys.modules.values()):
  if getattr(module,'site_it_power_kw',None) is original:setattr(module,'site_it_power_kw',frozen_power)
 power.site_it_power_kw=frozen_power
def capacity_binding(cap,racks):
 from dayahead.v38.authority import CapacityAuthority,RackPool
 nc=dict(zip(SITES,NEW));assert [cap['site_capacity'][s] for s in SITES]==OLD
 pools=racks['logical_Rack_pools'];assert len(pools)==48 and len({p['aidc_id'] for p in pools})==12
 assert racks['logical_Rack_limits_are_additive_capacity'] is False
 assert all(p['compatibility_GPU_limit']==cap['site_capacity'][p['aidc_id']] for p in pools)
 a=json.loads((H/'HEADROOM_AUTHORITY.json').read_text(encoding='utf-8'))
 return CapacityAuthority(nc,nc,tuple(RackPool(p['aidc_id'],p['rack_pool_id'],nc[p['aidc_id']]) for p in pools),hashlib.sha256((H/'HEADROOM_AUTHORITY.json').read_bytes()).hexdigest())

def bind_future_capacity(ctx,original_path):
 """Rebind derived physical capacity fields, keeping all forecasts/formulas frozen."""
 import copy,numpy as np
 from dayahead.v41.reserve import windows,validate_snapshot
 raw=Path(original_path).read_bytes();before=json.loads(raw);after=copy.deepcopy(before)
 sites=before['future_service_eligible_sites'];old=dict(zip(SITES,OLD))
 assert before['future_service_eligibility_authority']['source_variable']=='CapacityAuthority.site_capacity'
 assert np.array_equal(np.asarray(before['future_service_capacity_gpu']),np.tile([old[s] for s in sites],(96,1)))
 newcap=np.tile([ctx.capacity.site_capacity[s] for s in sites],(96,1))
 after['future_service_capacity_gpu']=newcap.tolist()
 after['H4_CAP_PHYS']=windows(newcap.sum(axis=1)).tolist()
 after['H4_ACTIONABLE_RESERVE_GPUh']=np.minimum(np.asarray(before['H4_RAW_R85_B2_GPUh']),np.minimum(before['H4_CAP_HIST'],after['H4_CAP_PHYS'])).tolist()
 reference=dict(path=str(H/'HEADROOM_AUTHORITY.json'),sha256=hashlib.sha256((H/'HEADROOM_AUTHORITY.json').read_bytes()).hexdigest(),bytes=(H/'HEADROOM_AUTHORITY.json').stat().st_size)
 after['capacity_authority']=reference
 after['future_service_eligibility_authority']['files']=[reference]
 changed=[k for k in before if before[k]!=after[k]]
 allowed=['future_service_capacity_gpu','H4_CAP_PHYS','H4_ACTIONABLE_RESERVE_GPUh','capacity_authority','future_service_eligibility_authority']
 assert set(changed)<=set(allowed)
 validate_snapshot(after,ctx.capacity)
 p=H/'HEADROOM_CAPACITY_DERIVED_SNAPSHOT.json';p.write_text(json.dumps(after,indent=2),encoding='utf-8')
 audit=dict(status='PASS',source_snapshot=dict(path=str(original_path),sha256=hashlib.sha256(raw).hexdigest()),derived_snapshot=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()),changed_fields=changed,formulas_unchanged=True,raw_ML_predictions_unchanged=True,job_runtime_scalars_unchanged=True,eligibility_sites_unchanged=True,old_total_normalized_capacity=780,new_total_normalized_capacity=1312,old_H4_physical_cap_GPUh=3120,new_H4_physical_cap_GPUh=5248,changed_actionable_windows=int(np.count_nonzero(np.asarray(before['H4_ACTIONABLE_RESERVE_GPUh'])!=np.asarray(after['H4_ACTIONABLE_RESERVE_GPUh']))),reason='CapacityAuthority.site_capacity derived copy was stale; apply the same physical capacity authority to every existing capacity consumer')
 (H/'FUTURE_CAPACITY_DERIVATION_AUDIT.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
 return p
