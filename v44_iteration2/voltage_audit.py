"""Audit actual M rows before optimize and original affine voltages afterwards."""
import numpy as np
from . import config as c
from .io import atomic,record,now,read,verify


def check_rows(case,stage):
 lower,upper=c.band(stage);d=case.original_d
 names=np.asarray(d['row_names']).astype(str)
 lo=np.flatnonzero(np.char.startswith(names,'voltage_lower['))
 hi=np.flatnonzero(np.char.startswith(names,'voltage_upper['))
 if len(case.coefficients)!=96:raise ValueError('VOLTAGE_AUDIT_REQUIRES_ALL96')
 controls=np.asarray(case.anchor['controls'],float)
 offsets=np.concatenate([x.voltage_constant+x.voltage_matrix.T@u for x,u in zip(case.coefficients,controls)])
 if len(lo)!=len(offsets) or len(hi)!=len(offsets):raise ValueError('ACTUAL_FULL_VOLTAGE_ROW_AXIS')
 if not np.array_equal(np.char.replace(names[lo],'voltage_lower','voltage'),np.char.replace(names[hi],'voltage_upper','voltage')):raise ValueError('ACTUAL_FULL_VOLTAGE_ROW_PAIRING')
 rhs=np.asarray(d['rhs'],float);senses=np.asarray(d['sense']).astype(str)
 if not np.all(senses[lo]=='>') or not np.all(senses[hi]=='<'):raise ValueError('ACTUAL_FULL_VOLTAGE_ROW_SENSE')
 errors=[float(np.max(abs(rhs[lo]-(lower**2-offsets)))),float(np.max(abs(rhs[hi]-(upper**2-offsets))))]
 if max(errors)>1e-12:raise ValueError('ITERATION2_ACTUAL_VOLTAGE_RHS_DRIFT:'+repr(errors))
 saved=getattr(case,'checkpoint_source_output',case.output)/'FULL_DATA.npz'
 with np.load(saved,allow_pickle=False) as z:
  if not np.array_equal(z['row_names'],d['row_names']) or not np.array_equal(z['rhs'],d['rhs']):raise ValueError('SAVED_FULL_VOLTAGE_MATRIX_DRIFT')
 value=dict(PASS=True,UTC=now(),stage=stage,day=case.identity['day'],case_sha=case.case_sha,
  voltage_band=[lower,upper],squared_band=[lower**2,upper**2],lower_rows=len(lo),upper_rows=len(hi),
  max_lower_rhs_error=errors[0],max_upper_rhs_error=errors[1],all96_slots_checked=True,
  actual_saved_matrix=record(saved),before_any_stage_Native_optimize=True)
 atomic(case.output/'ITERATION2_FULL_VOLTAGE_ROWS.json',value);return value


def check_plan(case,payload,plan,stage):
 lower,upper=c.band(stage);sites=list(map(str,payload['planning']['sites']));pcc=payload['planning']['PCC_P_kw']
 low=float('inf');high=-float('inf');count=0
 for t,coefficient in enumerate(case.coefficients):
  controls=[]
  for name in coefficient.control_names:
   site=name.split('[',1)[1][:-1]
   if name.startswith('aidc_load_kw'):controls.append(float(pcc[t,sites.index(site)]))
   elif name.startswith('mess_p_kw'):controls.append(float(plan['P_by_site'][site][t]))
   elif name.startswith('mess_q_kvar'):controls.append(float(plan['Q_by_site'][site][t]))
   else:raise ValueError('VOLTAGE_PLAN_UNKNOWN_CONTROL')
  squared=np.asarray(coefficient.voltage_constant+coefficient.voltage_matrix.T@np.asarray(controls),float)
  if not np.isfinite(squared).all() or np.any(squared<0):raise ValueError('VOLTAGE_PLAN_NONFINITE')
  low=min(low,float(np.sqrt(squared).min()));high=max(high,float(np.sqrt(squared).max()));count+=len(squared)
 value=dict(PASS=low>=lower-1e-7 and high<=upper+1e-7,UTC=now(),stage=stage,case_sha=case.case_sha,
  voltage_band=[lower,upper],min_voltage_pu=low,max_voltage_pu=high,evaluated_node_phase_slots=count,
  plan_sha=plan['plan_sha'],commands_clipped=False)
 atomic(case.output/'ITERATION2_PLAN_VOLTAGE.json',value)
 if not value['PASS']:raise ValueError('ITERATION2_TIGHT_M_PLAN_VOLTAGE_FAILED')
 return value


def verify_result(result,stage):
 """A public PASS or downstream parent must retain the actual matrix proof."""
 refs=[result['iteration2_voltage_rows'],result['iteration2_voltage_plan']];verify(refs)
 rows,plan=map(lambda r:read(r['path']),refs);band=list(c.band(stage))
 for proof in (rows,plan):
  if proof.get('PASS') is not True or proof.get('stage')!=stage or proof.get('case_sha')!=result['case_sha'] or proof.get('voltage_band')!=band:raise ValueError('ITERATION2_VOLTAGE_CERTIFICATE_DRIFT')
 if not rows.get('all96_slots_checked') or not rows.get('before_any_stage_Native_optimize') or rows['lower_rows']!=rows['upper_rows'] or rows['lower_rows']<=0:raise ValueError('ITERATION2_FULL_VOLTAGE_CERTIFICATE_REQUIRED')
 if plan['plan_sha']!=result['MESS_plan']['plan_sha'] or plan.get('commands_clipped') is not False:raise ValueError('ITERATION2_PLAN_VOLTAGE_CERTIFICATE_DRIFT')
 verify([rows['actual_saved_matrix']]);return dict(rows=refs[0],plan=refs[1])
