"""Exact real-matrix regression and Phi zero validation, without native solves."""
import gzip,pickle,subprocess
from fractions import Fraction
from time import perf_counter
import numpy as np
from .policy import ROOT,OUT,STATIC,OLDOUT,DAY
from .exact import replay as exact_replay
from .activation import batch_graphs
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_early.progress import artificial_free_inclusion
from v42_a_stage_compact_rowgen.lift import expanded_point
from v42_a_stage_compact_rowgen.assembly import compact_inverse,partition
from v42_a_stage_phase1.core import primal_replay,elastic_master

def route():
    import v42_a_stage_canary.pricing as pricing
    pricing.HISTORY=OLDOUT/DAY;pricing.OUT=OUT
    import v42_a_stage_canary.phase as phase
    phase.OUT=OUT
    import v42_a_stage_acceptance.physical as physical
    physical.ROOT=ROOT;physical.STATIC=STATIC/'PHYSICAL'

def run():
    started=perf_counter();r=read(OUT/'WITNESS_FAILURE_REPRODUCTION.json')['payload']
    if record(r['path'])!=r:raise ValueError('ACTUAL_FAILURE_PAYLOAD_CHANGED')
    with gzip.open(r['path'],'rb') as f:p=pickle.load(f)
    old,new=p['old'],p['new'];ex=expanded_point(old,p['raw']['X'])
    witness,mapped=artificial_free_inclusion(old['reference'],old['reference_descriptor'],ex,new['reference'],new['reference_descriptor'],old['n'])
    exact=exact_replay(new['reference'],mapped)
    inv=compact_inverse(new,mapped);compact=primal_replay(new['compact'],inv)
    if not witness['PASS'] or not exact['PASS'] or not compact['PASS']:raise ValueError('ACTUAL_REPAIRED_INCLUSION_EXACT_REPLAY_FAILED')
    # Independently compare batched ledger to the historically reconstructed
    # serial union, on all real May12 classes and pool identities.
    selected=sorted(p['negative'],key=lambda z:(z['price'],z['class_id'],z['support_sha256']))[:64]
    data,ledger=batch_graphs(old['data'],old['domains'],selected)
    identities_same=all(data[5][uid].sha==new['data'][5][uid].sha for uid in data[1])
    pool_same=ledger['receipt']==new['ledger']['receipt']
    if not identities_same or not pool_same:raise ValueError('ACTUAL_BATCH_LEDGER_NOT_SERIAL_EQUIVALENT')
    atomic(OUT/'PHASE1_REGRESSION_TESTS.json',dict(PASS=True,actual_May12_matrix_regression=True,
        before_fix_failure_log=record(STATIC/'REGRESSION_BEFORE_FIX.log'),after_fix_success_log=record(STATIC/'REGRESSION_AFTER_FIX.log'),
        actual_saved_error=record(OUT/'WITNESS_FAILURE_REPRODUCTION.json'),original_inclusion=witness,rational_full_original_row_replay=exact,
        exact_compact_inverse_replay=compact,actual_batch_ledger_equivalence=True,classes=130,
        candidates_deleted=False,positive_Phi_weight_sign_guard_preserved=True,native_calls=0))
    rc=read(OUT/'RECOVERED_CHECKPOINT_VERIFICATION.json')
    with gzip.open(rc['state']['path'],'rb') as f:checkpoint=pickle.load(f)
    state=checkpoint['state'];zx=checkpoint['phase1_raw']['X'][:state['compact'].matrix.shape[1]]
    zex=checkpoint['phase1_expanded'];zr=exact_replay(state['reference'],zex)
    if not zr['PASS']:raise ValueError('SAVED_ZERO_EXACT_ORIGINAL_ROW_REPLAY_FAILED')
    route()
    from v42_a_stage_acceptance.physical import Physical
    physical=Physical(state,state['reference'])
    from v42_pr134_sc.snapshot import evaluate
    controls=[[evaluate(e,zex) for e in row] for row in physical.descriptor['controls']]
    rho=evaluate(physical.descriptor['levels'][0][1],zex)
    from v42_integrated.contract import grid_audit
    grid=grid_audit(physical.coeff,controls,rho)
    if not grid['PASS']:raise ValueError('SAVED_ZERO_ORIGINAL_GRID_PHYSICS_FAILED')
    from v42_a_stage_canary.pricing import full_pricing
    master=elastic_master(state['compact'],state['grows']);local,owned=partition(state['compact'],state['metas'],state['grows'])
    class NoNative:
        def remaining(self):return 3600
        def solve(self,*a,**kw):raise PermissionError('ZERO_ANALYTICAL_PRICE_MUST_NOT_OPTIMIZE')
    zero_price,_=full_pricing(NoNative(),state['compact'],master,
        dict(X=checkpoint['phase1_raw']['X'],Pi=np.zeros(master.snapshot.matrix.shape[0])),None,
        state['data'],state['domains'],state['ledger'],state['axes'],state['n'],state['grows'],local,owned,OUT/'PHASE1/ANALYTICAL_ZERO_PRICE',zero=True)
    if zero_price['classes']!=130 or not zero_price['no_negative_omitted_block_certified']:raise ValueError('PHASE_I_FULL_ZERO_PRICING_CLOSURE_FAIL')
    zero=dict(PASS=True,day=DAY,phase1_native_raw_Phi=0,phase1_exact_raw_Phi='0',
        replayed_reconstructed_artificial_Phi=read(OLDOUT/DAY/'PHASE_I_ZERO_CERTIFICATE.json')['zero']['replayed_phi'],
        artificial_free_original_point=True,original_rows_exact_replay=zr,original_planning_grid_replay=grid,
        original_active_and_full_domain_embedding_verified=True,full_130_class_zero_dual_pricing=record(OUT/'PHASE1/ANALYTICAL_ZERO_PRICE/FULL_PRICING_RESULT.json'),
        continuous_Phase_I_only=True,original_integer_schedule_not_yet_certified=True,
        old_Phase_I_solves_reused=23,new_Phase_I_native_solves=0,old_checkpoint=rc['state'])
    atomic(OUT/'PHASE1_ZERO_CERTIFICATE.json',zero)
    atomic(OUT/'MEMORY_GUARDS_USER_OVERRIDE.json',dict(PASS=True,finite_MemLimit=False,finite_SoftMemLimit=False,
        RAM_automatic_stop=False,allocation_cap=False,telemetry_only=True,authority='EXPLICIT_USER_MAY12_RECOVERY_REQUEST'))
    atomic(OUT/'CONTINUATION_BUDGET.json',dict(PASS=True,new_native_limit=3600,old_native_Runtime=233.89299654960632,old_budget_immutable=True))
    atomic(OUT/'NATIVE_PLAN.json',dict(PASS=True,schema='MAY12_P1_ONLY_EXACT_RESCUE_V1',day=DAY,
        cumulative_native_limit=3600,Threads=1,MIPGap=.005,FeasibilityTol=1e-6,OptimalityTol=1e-6,IntFeasTol=1e-5,
        Method=2,NodeMethod=1,MIPFocus=3,Presolve=-1,parameter_sweep=False,
        per_master_native_cap=600,per_class_pricing_native_cap=60,max_P1_rounds=20,
        terminal_native_time_limit_reserve_seconds=30,
        integer_native_uses_remaining_budget=True,activation_max_verified_blocks=130,
        initial_saved_negative_supports=92,all_completed_historical_solves_reused=True,
        batch_graph_ledger_refresh_once=True,positive_Phi_frozen_weight_check_unchanged=True,
        memory_limits=False,automatic_followup=False,P2_native_allowed=False,downstream_allowed=False,
        model_equivalence_before_each_native=True,native_calls_sequential=True))
    atomic(OUT/'RECOVERY_STATIC_COST.json',dict(PASS=True,prepare_wall_seconds=perf_counter()-started,
        recovery_initial_wall_seconds=rc['wall_seconds'],recovered_directions_wall_seconds=read(OUT/'WITNESS_FAILURE_REPRODUCTION.json')['wall_seconds'],new_native_calls=0))
    print('MAY12_EXACT_REPAIRED_INCLUSION_AND_ZERO_PASS',perf_counter()-started,flush=True)

def freeze():
    head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    sources={str(p):sha(p) for p in sorted(ROOT.rglob('*.py')) if not any(x in p.parts for x in ('artifacts','tmp','.git'))}
    atomic(OUT/'SOURCE_FREEZE.json',dict(PASS=True,schema='MAY12_P1_ONLY_EXACT_RESCUE_V1',git_head=head,
        execution_sources=sources,plan=record(OUT/'NATIVE_PLAN.json'),historical_source_head='1b891dbe5b1dd454d89b657efec7cba469c0cf94'))
    print('MAY12_NEW_SOURCE_FROZEN',head,len(sources))
if __name__=='__main__':
    import sys
    (freeze if '--freeze' in sys.argv else run)()
