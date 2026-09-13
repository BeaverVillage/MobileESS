"""Freeze the robust Actual rules before any further May evaluation."""
import os,sys,time,json,hashlib,shutil,psutil
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
OLD=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_v1'
NEW=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
assert not (NEW/'METHOD_FREEZE.json').exists()
prior=read(OLD/'METHOD_FREEZE.json');now=time.time();files=[]
for name in ('common.py','worker.py','qsafe.py'):
    src=OLD/'frozen_code'/name;dst=NEW/'frozen_code'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    files.append(dict(name=name,path=str(dst),source=str(src),sha256=sha(dst)))
for name in ('BATTERY_EFFICIENCY_AUTHORITY.json','input_adapter.py','actual_worker.py','binding.py','dispatcher.py','report_candidate.py'):
    shutil.copy2(OLD/name,NEW/name)
rules=dict(domain='Full Cartesian product of connected-MESS Q intervals from |P|<=300, exact 400-kVA circle, and all 16 inner polygon faces; disconnected Q=0',coarse_grid=dict(levels=5,unit_coordinates=[0,.25,.5,.75,1],order='Cartesian lexicographic in sorted MESS ID order; all endpoints and corners included'),screening_prepoints=['frozen physical DA Q','maximum absorption','maximum injection','zero clipped to domain'],Sobol=dict(points=256,scramble=True,seed=120530,same_rule_every_slot=True),multistart=dict(max_starts=8,initial_seeds=['frozen physical DA Q','maximum absorption','zero clipped to domain'],remaining_seeds='Candidate ranking by (sum positive constraint deficits squared, sum squared deviation from DA Q, lexicographic Q); first distinct native final-tap signatures, skipping duplicate Q starts',solver='Powell in [0,1]^d',objective='sum(max(-g_i(Q),0)^2)',maxiter=20,maxfev=140,xtol=1e-5,ftol=1e-12),progressive_refinement=dict(unit_radii=[.125,.03125,.0078125],max_centers=4,center_rule='Same feasibility-penalty/deviation/lexicographic ranking; Euclidean separation >0.15 in unit coordinates',trials='At each center, +/- axis points in variable order, then all +/- radius corners in lexicographic order; clip to full box'),local_refinement=dict(max_starts=4,start_rule='Best exact-feasible candidates by squared DA-Q deviation, or lowest-penalty points if none feasible; unit-coordinate separation >0.025',solver='SLSQP',objective='0.5*sum(((Q-Q_DA)/400)^2)',maxiter=75,ftol=1e-10,finite_difference_step_kvar=.25,derivative='Bound-aware central difference of exact AC constraints; analytic objective gradient'),constraints_vector='20*(V-.95), 20*(1.05-V), 1-all phase-current loadings, 1-finite transformer kVA loadings',stopping=dict(unique_exact_Q_trial_cap=5000,wall_time_stop=False,run_all_prescribed_stages_unless_cap_reached=True,cached_identical_Q_points_do_not_consume_budget=True,one_uncached_final_validation_outside_search_cap=True),selection='Among all exact AC-feasible tested candidates, minimum sum((Q-Q_DA)^2), with lexicographic Q tie-break; validate selected Q in one additional clean-prefix exact OpenDSS replay',failure='ROBUST_Q_ONLY_UNRESOLVED; retain original physically executable Q, fixed P; propagate only that final native state',no_global_optimality_claim=True)
save(NEW/'METHOD_FREEZE.json',dict(status='FROZEN_FINAL_ACTUAL_ROBUST_SEARCH',version='V41R4_ACTUAL_ETA95_QSAFE_ROBUST_V2',frozen_at=now,description='Day-Ahead discrete decisions and active-power schedules are frozen. D-day operation permits causal Q-only corrective AC-feasibility control using a deterministic robust search and exact OpenDSS validation.',paper_facing_wording='minimum-deviation feasible correction found by the prescribed deterministic search.',eta_charge=.95,eta_discharge=.95,alpha_BG=1.15,active_power_limit_kw=300,pcs_kva=400,pcs_inner_polygon_faces=16,objective='sum_m (Q_m-Q_m_DA)^2',hard_limits=dict(Vmin=.95,Vmax=1.05,line=1,transformer_phase_current=1,transformer_kVA=1),inherited_hard_comparison_tolerance=1e-9,PCS_audit_tolerance=1e-9,preventive_threshold=None,P_fallback=False,failure='ROBUST_Q_ONLY_UNRESOLVED',search=rules,development_days=prior['development_days'],holdout_days=prior['holdout_days'],all_days=prior['all_days'],pre_freeze_Actual_holdout_results_are_final_evidence=False,all_Actual_policy_days_require_new_post_freeze_execution=True,holdout_tuning_allowed=False,method_basis='May12 B3 slot30 forensic Q_ONLY_SEARCH_FAILURE_FEASIBLE_POINT_FOUND only; no later May results used to select these rules',numerical_method_files=files,efficiency_authority_SHA=sha(NEW/'BATTERY_EFFICIENCY_AUTHORITY.json'),common_maximum_concurrent_day_workers=4,dispatch_priority=['eligible new robust Actual-only replay','next missing DA/Fresh work'],DA_Fresh_reruns_allowed=False,trials='Every trial reconstructs the exact approved causal prefix; identical slot-start native state; failed trial states discarded',no_future_Actual_information=True))
save(NEW/'COHORTS.json',dict(development=prior['development_days'],holdout=prior['holdout_days'],full_May=prior['all_days'],frozen_at=now))
state=read(OLD/'DISPATCHER_STATE.json');parent=psutil.Process(state['supervisor_pid']);assert any(str(x).endswith('dispatcher.py') for x in parent.cmdline());parent.suspend()
state=read(OLD/'DISPATCHER_STATE.json');workers=[]
for r in state['active']:
    try:
        p=psutil.Process(r['worker_pid']);assert p.create_time()==r['created_at'];workers.append(dict(**r,command=p.cmdline(),CPU_seconds=sum(p.cpu_times()[:2])))
    except psutil.NoSuchProcess:pass
save(NEW/'HANDOFF_SNAPSHOT.json',dict(at=time.time(),legacy_campaign_progress=state,live_workers=workers,old_dispatcher_pid=parent.pid,old_namespace=str(OLD),worker_preemptions=0,old_coordinator_suspended_for_handoff=True))
save(NEW/'SWITCH_STATUS.json',dict(status='ROBUST_METHOD_FROZEN_PREPARING_EXECUTION',legacy_coordinator_suspended_pid=parent.pid,existing_campaign_workers=workers,common_worker_cap=4))
forensic=OLD/'diagnostics/may12_b3_slot30_v1';dest=NEW/'historical_evidence/MAY12_B3_SLOT30_FORENSIC'
shutil.copytree(forensic,dest)
evidence={str(p.relative_to(dest)):sha(p) for p in dest.rglob('*') if p.is_file()}
assert all(sha(forensic/k)==h for k,h in evidence.items())
save(NEW/'historical_evidence/FORENSIC_PRESERVATION.json',dict(classification='Q_ONLY_SEARCH_FAILURE_FEASIBLE_POINT_FOUND',source=str(forensic),files=evidence,byte_identical=True))
save(NEW/'historical_evidence/V1_REFERENCE.json',dict(namespace=str(OLD),method_SHA=sha(OLD/'METHOD_FREEZE.json'),pre_freeze_results_are_historical_only=True,overwrite_allowed=False))
print(json.dumps(dict(namespace=str(NEW),rules_frozen_at=now,preserved_workers=[dict(pid=r['worker_pid'],day=r['day'],phase=r['phase']) for r in workers]),indent=2))
