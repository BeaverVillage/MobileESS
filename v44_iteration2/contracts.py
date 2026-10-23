"""Pure contracts used before any original-engine import or Native call."""
import math
from .config import DAYS,STAGES,FLEET
from .io import digest

def full_m(result,day):
 if result.get('day')!=day or result.get('arm')!='B3' or result.get('error') or result.get('implementation_errors'):raise ValueError('M_PARENT_IDENTITY_OR_EXECUTION_FAILURE')
 if not (result.get('FULL_feasible') is True and result.get('upper',{}).get('FULL_validated') is True and result.get('M_stage_execution_PASS') is True and result.get('allow_downstream') is True):raise ValueError('M_ORIGINAL_FULL_REQUIRED')
 p=result['MESS_plan']
 if p['plan_sha']!=digest({k:v for k,v in p.items() if k!='plan_sha'}) or p['case_sha']!=result['case_sha']:raise ValueError('M_PLAN_SHA_DRIFT')
 if tuple(sorted(p['P_kW']))!=FLEET or p['time_axis']!=list(range(96)):raise ValueError('FOUR_MESS_96_AXIS_REQUIRED')
 return p

def full_a(result,day):
 if result.get('day')!=day or result.get('arm')!='B3' or result.get('error'):raise ValueError('A_STAGE_IDENTITY_OR_EXECUTION_FAILURE')
 gap=result.get('certified_gap')
 if not (result.get('PASS') is True and result.get('FULL_feasible') is True and result.get('independent_Global_LB_validated') is True and isinstance(gap,(float,int)) and math.isfinite(gap) and 0<=gap<=.005):raise ValueError('A_NEW_INDEPENDENT_FULL_GAP_REQUIRED')
 native=result.get('Native_seconds',0)
 if not isinstance(native,(int,float)) or not math.isfinite(native) or native<=0:raise ValueError('NEW_A_SOLVER_CALLS_REQUIRED')
 if result.get('old_point_bound_clock_loaded'):raise ValueError('A_OLD_OPTIMUM_OR_CLOCK_REUSE_FORBIDDEN')
 return result

def actual_barrier(rows):
 if len(rows)!=31 or {r['day'] for r in rows}!=set(DAYS):return False
 return all(r.get('status') in ('PLANNING_FAILED','PLANNING_BLOCKED') or
  r.get('status')=='PLANNING_PASS' and r.get('M4_freeze') and r.get('stages',{}).get('M4',{}).get('PASS') is True for r in rows)

def actual_ready(rows):
 return [r for r in rows if r.get('status')=='PLANNING_PASS' and r.get('M4_freeze') and r.get('stages',{}).get('M4',{}).get('PASS') is True]

def ready_barrier(barrier,rows):
 ready=actual_ready(rows)
 return bool(actual_barrier(rows) and barrier.get('PASS') is True and barrier.get('all_31_Planning_terminal') is True
  and barrier.get('days')==list(DAYS) and barrier.get('ready_days')==[j['day'] for j in ready]
  and barrier.get('freezes')==[j['M4_freeze'] for j in ready])

def b2_terminal(state,live,unreconciled):
 expected={f'2025-05-{n:02d}' for n in range(22,32)}
 jobs=state.get('jobs',[])
 terminal={'PASS','FAILED','ACTUAL_FAILED','EXCLUDED'}
 return (state.get('phase')=='COMPLETE' and len(jobs)==10 and {j.get('day') for j in jobs}==expected
  and all(j.get('arm')=='B2' and j.get('status') in terminal and j.get('result') for j in jobs)
  and not state.get('pending_retries') and not state.get('resume_pending') and not live and not unreconciled)
