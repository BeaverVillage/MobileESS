"""Conjunction of original Actual execution, ALL120 independent AC and MESS checks."""
from pathlib import Path
from types import FunctionType
import math
import numpy as np
from .io import read,record,verify,atomic
from .contracts import full_m,full_a
from . import config as c

def trajectory(raw):
 rows=raw['physical_steps']
 if len(rows)!=120 or [r['slot'] for r in rows]!=list(range(120)):raise ValueError('EXACT_ACTUAL120_AXIS_REQUIRED')
 evaluated=rows[24:];loads=[float(r['maximum_phase_line_loading']) for r in evaluated]
 if not all(math.isfinite(v) for v in loads):raise ValueError('NONFINITE_LINE_MEASUREMENT')
 return dict(evaluation_slots=96,maximum_line_loading_pu=max(loads),mean_slot_maximum_line_loading_pu=sum(loads)/96,
  voltage_min_pu=min(r['voltage_min_pu'] for r in evaluated),voltage_max_pu=max(r['voltage_max_pu'] for r in evaluated),
  voltage_violation_slots=[r['slot'] for r in evaluated if r['voltage_min_pu']<.95-1e-6 or r['voltage_max_pu']>1.05+1e-6],
  maximum_transformer_kVA_loading_pu=max(t['loading_pu'] for r in evaluated for t in r['full_physical']['transformers']),
  measurement='Executed Actual trajectory evaluated in independent Fresh AC; 6h prefix excluded from evaluation96')

def validate_actual(root,request,freeze,driver):
 from .bootstrap import equipment
 from final_audit import physical,mess_check
 root=Path(root);rawpath=root/'ACTUAL/C1/FRESH_SVR12_TIME_AC.json';raw=read(rawpath)
 fp=physical(raw);mroot=Path(freeze['M4_core']['path']).parent
 def selected(p):
  p=Path(p)
  if p==root/'M2/RESULT.json':return read(mroot/'RESULT.json')
  if p==root/'M2/request.json':return read(mroot/'request.json')
  return read(p)
 mp=FunctionType(mess_check.__code__,dict(mess_check.__globals__,read=selected))(root)
 original=read(root/'ACTUAL/RESULT.json');variant=original.get('variants',{}).get('C1',{})
 full_m(read(freeze['M4_core']['path']),request['day']);full_a(read(freeze['A4_core']['path']),request['day'])
 verify(freeze['evidence'])
 with np.load(root/'ACTUAL/C1/ACTUAL_PHYSICAL.npz',allow_pickle=False) as z:
  actual120=z['GPU'].shape[0]==120 and z['PCC_P_kw'].shape[0]==120 and z['PCC_Q_kvar'].shape[0]==120
 receipt=variant.get('receipt',{})
 events=read(root/'ACTUAL/C1/ACTUAL_EVENT_LEDGERS.json');qos=[]
 for row in events['qos_ledger']:
  values=[row[k] for k in ('budget_seconds','intentional_start_delay_seconds','migration_interruption_seconds','total_intentional_burden_seconds')]
  if not all(isinstance(v,(float,int)) and math.isfinite(v) and v>=-1e-6 for v in values) or abs(values[1]+values[2]-values[3])>1e-6 or values[3]>values[0]+1e-6:qos.append(row['uid'])
 execution=bool(actual120 and original.get('Actual96_PASS') and variant.get('Actual96_execution_PASS') and variant.get('Known_commands_unchanged') and receipt.get('capacity_violations')==0 and receipt.get('dropped_jobs')==0 and receipt.get('optimizer_calls')==0 and variant.get('Native_calls')==0 and variant.get('Native_seconds')==0)
 verdict=dict(PASS=bool(driver.get('PASS') and not driver.get('error') and original.get('Fresh96_PASS') and execution and fp['PASS'] and mp['PASS'] and not qos),
  day=request['day'],arm='B3',equipment_version=c.EQUIPMENT,Actual120_original_execution_PASS=execution,
  Actual120_input_and_output_axis_checked=bool(actual120),independent_Fresh120=fp,evaluation96=trajectory(raw),MESS_SOC_PCS_routes=mp,
  original_execution_receipt=receipt,Known_commands_unchanged=variant.get('Known_commands_unchanged'),
  QoS_intentional_delay_and_migration_budget=dict(PASS=not qos,checked_jobs=len(events['qos_ledger']),violating_uids=qos),
  Native_calls_in_Actual=variant.get('Native_calls'),Native_seconds_in_Actual=variant.get('Native_seconds'),
  raw=record(rawpath),actual=record(root/'ACTUAL/RESULT.json'),Actual_current_AC=record(root/'ACTUAL/C1/CURRENT_AC_RECEIPTS.json'),
  M4=freeze['M4_core'],A4=freeze['A4_core'],Fresh_from_independent_original_driver=True)
 atomic(root/'INDEPENDENT_FINAL_AUDIT.json',verdict);return verdict
