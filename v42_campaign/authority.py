import hashlib,json,math
from datetime import date,timedelta
MAX_B3_LOOPS=4
EARLY_STOP_ON_CONVERGENCE=False
MAIN=('B0','B1','B2','B3_L1')
CONVERGENCE=('B3_L2','B3_L3','B3_L4')
GROUPS=MAIN+CONVERGENCE
STATES=('PENDING','RUNNING','ACCEPTED','FAILED')
INPUT_KINDS=('D1_SOURCE','FORECAST','RUNTIME_CC4','PREVIOUS_PLANNING_FREEZE','PREVIOUS_PLANNING_STATE','CURRENT_PLANNING_FREEZE')
FORBIDDEN_KINDS=('ACTUAL','FRESH_AC','REALIZED_DDAY','ACTUAL_TAP','ACTUAL_RESIDUAL')
ARM_SEMANTICS={name:dict(workload_present=True,AIDC_grid_aware_flexibility=name in ('B1','B3'),MESS_ON=name in ('B2','B3'),Runtime_CC4_common=True,physical_queue_capacity_active=True,ML_OFF=False) for name in ('B0','B1','B2','B3')}
SCIENTIFIC=dict(voltage_band=[.95,1.05],voltage_margin_pu=0,transformer_current='source-backed OpenDSS NormalAmps',transformer_kVA='source-backed kVA rating',line_thermal='source-backed unchanged line rating',autonomous_RegControls=7,fixed_ON_capacitors=4,CapControls=0,Actual_P_repair=False,Actual_Q_repair=False,Actual_global_reoptimization=False,Planning_tap_replay=False,Runtime_CC4_capacity='PR135 accepted frozen authority',solver_FeasibilityTol=1e-8,solver_IntFeasTol=1e-8,solver_OptimalityTol=1e-8,postsolve_numerical_tol=1e-6,MAX_HEAVY_WORKERS=1,Gurobi_Threads=1)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def file_sha(path):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def may_days(year=2025):return tuple((date(year,5,1)+timedelta(days=i)).isoformat() for i in range(31))
def contract():return dict(main_order=list(MAIN),convergence_order=list(CONVERGENCE),MAX_B3_LOOPS=4,EARLY_STOP_ON_CONVERGENCE=False,scientific=SCIENTIFIC,arm_semantics=ARM_SEMANTICS,production_execution_enabled=False,main_comparison=list(MAIN),convergence_analysis=['B3_L1',*CONVERGENCE],Actual_completion_status_sequence_gate_only=True,Actual_values_for_Planning=False)
def authority_sha():return digest(contract())
