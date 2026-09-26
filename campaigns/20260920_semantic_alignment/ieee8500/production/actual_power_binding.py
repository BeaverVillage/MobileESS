"""Same frozen 2x IT/C1 law, with separate authorized scheduling capacity."""
import inspect,hashlib,json
from decimal import Decimal
from pathlib import Path
import numpy as np
from headroom_authority import OLD,NEW,SITES,install_power_binding

def power_from_execution(repo,replay,capacity,weather):
 from dayahead.v40d_actual import power_replay as original
 from dayahead.v41.actual import compare_occupancy
 from dayahead.v39a.contracts import IDLE_W_PER_GPU,CENTER_SWING_W_PER_GPU,POWER_TOLERANCE_KW
 install_power_binding()
 assert dict(capacity)==dict(zip(SITES,NEW))
 old=dict(zip(SITES,OLD))
 def aggregate(active):
  assert 0<=active<=sum(NEW)
  return (Decimal(sum(OLD))*IDLE_W_PER_GPU+Decimal(active)*CENTER_SWING_W_PER_GPU)/1000
 def check(cap,occ,it):
  assert np.asarray(occ).shape==(96,12) and np.all(occ>=0) and np.all(occ<=np.array(NEW)) and np.array_equal(occ,np.floor(occ))
  expected=np.array([[float((Decimal(OLD[i])*IDLE_W_PER_GPU+Decimal(int(occ[t,i]))*CENTER_SWING_W_PER_GPU)/1000) for i in range(12)] for t in range(96)])
  error=float(np.max(np.abs(it-expected)));total_error=float(np.max(np.abs(it.sum(axis=1)-np.array([float(aggregate(int(n))) for n in occ.sum(axis=1)]))))
  assert max(error,total_error)<=float(POWER_TOLERANCE_KW)
  return dict(status='PASS',GPU_TO_IT_POWER_MAX_ERROR_KW=error,aggregate_analytic_max_error_kW=total_error,preregistered_tolerance_kW=str(POWER_TOLERANCE_KW),physical_capacity=sum(NEW)*4.2,power_installed_capacity_normalized=sum(OLD),idle_intercept_unchanged=True,identity='old installed GPU * idle + actual occupied GPU * original dynamic slope')
 source=inspect.getsource(original.power_from_execution)
 adapted=source.replace('Decimal(capacity[s])*IDLE_W_PER_GPU','Decimal(old_power_capacity[s])*IDLE_W_PER_GPU').replace('aggregate_it_power_kw(int(occupancy[t].sum()))','frozen_aggregate(int(occupancy[t].sum()))').replace('check_it_power(capacity,occupancy,it)','check_frozen_it_power(capacity,occupancy,it)')
 assert adapted!=source
 ns=dict(vars(original),compare_occupancy=compare_occupancy,old_power_capacity=old,frozen_aggregate=aggregate,check_frozen_it_power=check)
 exec(compile(adapted,str(Path(__file__).absolute())+'::capacity_only_power_binding','exec'),ns)
 result=ns['power_from_execution'](repo,replay,capacity,weather)
 result['power_audit'].update(original_function_SHA256=hashlib.sha256(source.encode()).hexdigest(),capacity_only_bound_function_SHA256=hashlib.sha256(adapted.encode()).hexdigest(),mobility_or_dispatch_changes=False)
 return result
