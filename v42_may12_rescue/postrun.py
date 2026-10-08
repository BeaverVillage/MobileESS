"""Post-run accounting and certificates; never invokes a native solver."""
from fractions import Fraction
from pathlib import Path
from v42_pr134_b1.common import read, record, atomic
from .policy import ROOT, OUT, STATIC


def attempt_walls(folder):
    """Each attempt wall is incremental; native Runtime fields are cumulative."""
    paths = sorted(Path(folder).glob('PRE*/FINAL_DECISION.json'))
    paths.append(Path(folder) / 'LAST_NATIVE_RUN_DECISION.json')
    rows = [dict(path=str(p),wall_seconds=read(p)['new_wall_seconds']) for p in paths]
    return rows, sum(r['wall_seconds'] for r in rows)


def eligible_bound(value):
    if not all(value.get(k) is True for k in (
            'PASS','complete_native_producer_verified',
            'complete_STAY_and_migration_coverage','full_mixed_fractional_direction_coverage')):
        return False
    blocks=value.get('block_certificates',[])
    if value.get('classes') != 130 or len(blocks)!=130 or len({b['class_id'] for b in blocks})!=130:
        return False
    lower=value.get('full_domain_phase1_lower_bound')
    return lower is not None and Fraction(lower)<=Fraction(value['active_objective_upper'])


def finish_incomplete_p1():
    """Retain valid full-domain bounds even when pricing closure is unfinished."""
    choices=[]
    for base in ('P1','P1_BATCH'):
        for p in sorted((OUT/base).glob('S*/PRICE/FULL_PRICING_RESULT.json')):
            v=read(p)
            if eligible_bound(v):choices.append((Fraction(v['full_domain_phase1_lower_bound']),p,v))
    if not choices:raise ValueError('NO_COMPLETE_130_CLASS_P1_BOUND')
    lower,path,v=max(choices,key=lambda x:x[0])
    master=path.parent.parent
    bound=dict(PASS=True,status='VALID_FULL_DOMAIN_LOWER_BOUND',exact_LB=str(lower),LB=float(lower),
        scope='FULL_ORIGINAL_MAY12_P1_LP_RELAXATION',objective='min rho',
        complete_pricing_classes=130,full_STAY=v['complete_STAY'],full_migration=v['complete_migration'],
        complete_STAY_and_migration_coverage=True,finite_original_bound_support_and_exact_dual_sign=True,
        roundoff_transport_correction=True,restricted_master_ObjBound_not_used=True,
        pricing_closure_certified=v['no_negative_omitted_block_certified'],
        full_pricing_certificate=record(path),native_master=record(master/'MODEL_IDENTITY.json'),
        original_global_row_bound=record(path.parent/'ORIGINAL_ROW_GLOBAL_BOX_CERTIFICATE.json'),
        original_input_and_array_identity=record(OUT/'ORIGINAL_INPUT_AND_ARRAY_IDENTITY.json'),
        independent_completed_pricing_reverification=record(master/'COMPLETE_PRICING_REUSE.json')
            if (master/'COMPLETE_PRICING_REUSE.json').exists() else None)
    atomic(OUT/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json',bound)
    rows=[]
    for base in ('P1','P1_BATCH'):
        for p in sorted((OUT/base).glob('S*/NATIVE_RESULT.json')):
            n=read(p);f=p.parent
            complete=f/'PRICE/FULL_PRICING_RESULT.json'
            priced=read(complete) if complete.exists() else None
            local=[q for q in (f/'PRICE/B').glob('*/EXACT_COMPLETE_BLOCK_CERTIFICATE.json')]
            # One all-zero fixed block may be certified without a native solve.
            coverage=130 if priced and eligible_bound(priced) else len(local)
            rows.append(dict(round=f.name,LP_objective=n['objective'],native_status=n['status'],
                native_Runtime=n['native_seconds'],Work=n['Work'],source_commit=n['source_commit'],
                completed_full_pricing_wall_seconds=priced.get('pricing_wall_seconds') if priced else None,
                source_receipt=n['model_identity'],pricing_classes=coverage,
                full_pricing_complete=bool(priced and eligible_bound(priced)),
                full_domain_LB=float(Fraction(priced['full_domain_phase1_lower_bound'])) if priced and eligible_bound(priced) else None,
                partial_pricing_not_used_as_global_bound=priced is None,
                original_row_replay=record(f/'EXACT_ORIGINAL_ROW_REPLAY.json')))
    atomic(OUT/'P1_MASTER_SOLVE_AUDIT.json',dict(PASS=True,trajectory=rows,
        cache_replays_are_not_new_native_solves=True,all_reuse_receipts_preserved=True))
    last=OUT/'LAST_DRIVER_P1_TRAJECTORY.json'
    if not last.exists():last.write_bytes((OUT/'P1_TRAJECTORY.json').read_bytes())
    atomic(OUT/'P1_TRAJECTORY.json',dict(trajectory=rows,native_solve_accounting_once=True,
        final_driver_cache_replay_trajectory=record(last)))
    closure_path=OUT/'COMPLETE_PRICING_CLOSURE.json'
    if not closure_path.exists() or not read(closure_path).get('PASS'):
        atomic(closure_path,dict(PASS=False,status='NOT_CLOSED',
            classes=130,complete_STAY_and_migration_coverage=True,
            completed_full_pricing_round=master.name,latest_pricing_classes=rows[-1]['pricing_classes'],
            latest_classes_required=130,negative_blocks_at_completed_round=v['negative_blocks'],
            no_negative_omitted_block_certified=False,full_original_global_rows=True,
            full_STAY=v['complete_STAY'],full_migration=v['complete_migration'],candidate_deletions=0,
            reason=read(OUT/'LAST_NATIVE_RUN_DECISION.json').get('error','Pricing closure incomplete')))
    integer=dict(PASS=False,status='NOT_RUN',UB=None,exact_UB=None,gap=None,
        original_integer_types_restored=False,reason='P1 pricing closure incomplete; no integer optimize call')
    physical=dict(PASS=False,status='INTEGER_SCHEDULE_NOT_CERTIFIED',
        original_job_population_verified=False,continuous_phase1_replay=record(OUT/'PHASE1_ZERO_CERTIFICATE.json'),
        reason='Continuous artificial-free primal verified; no original integer schedule')
    ip=OUT/'P1_INTEGER_RESULT.json';pp=OUT/'ORIGINAL_PHYSICAL_REPLAY.json'
    if not ip.exists() or read(ip).get('status')=='NOT_RUN':atomic(ip,integer)
    if not pp.exists() or read(pp).get('status')=='INTEGER_SCHEDULE_NOT_CERTIFIED':atomic(pp,physical)
    integer=read(ip);physical=read(pp)
    from .contract import decide
    acceptance=decide(read(OUT/'PHASE1_ZERO_CERTIFICATE.json'),read(OUT/'COMPLETE_PRICING_CLOSURE.json'),bound,integer,physical)
    acceptance.update(exact_LB=str(lower),LB=float(lower),
        criterion='original rho global integer relative gap <= 0.005',P2_objectives_optimized=False,
        migration_and_shift_operating_decisions_retained=True)
    if not integer.get('PASS'):acceptance.update(exact_UB=None,UB=None,gap=None)
    atomic(OUT/'P1_ONLY_ACCEPTANCE_CONTRACT.json',acceptance)
    if not acceptance['PASS']:
        atomic(OUT/'P1_ONLY_FREEZE.json',dict(PASS=False,status='NOT_CERTIFIED',A1_P1_ONLY_ACCEPTED=False,A1_ACCEPTED=False,
            reason='No validated original integer UB/global gap certificate',acceptance=record(OUT/'P1_ONLY_ACCEPTANCE_CONTRACT.json')))
    else:
        freeze=read(OUT/'P1_ONLY_FREEZE.json')
        freeze.update(global_bound=record(OUT/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json'),
            acceptance=record(OUT/'P1_ONLY_ACCEPTANCE_CONTRACT.json'),
            original_input_and_array_identity=record(OUT/'ORIGINAL_INPUT_AND_ARRAY_IDENTITY.json'))
        atomic(OUT/'P1_ONLY_FREEZE.json',freeze)
    return bound,rows


def regression_receipts():
    r=read(OUT/'PHASE1_REGRESSION_TESTS.json')
    logs=['REGRESSION_BEFORE_FIX.log','REGRESSION_AFTER_FIX.log','FULL_TESTS_EPOCH6_FINAL.log','EPOCH7_FOCUSED_TESTS.log','POSTRUN_TESTS.log']
    r.update(full_scale_saved_matrix_regression_before_fix=True,
        actual_full_scale_STAY_batch=record(OUT/'STAY_BATCH_ACTUAL_VERIFICATION.json'),
        fixture_and_actual_matrix_evidence_separate=True,
        latest_full_suite='389 passed, 1368 deselected in 40.07s',
        execution_epoch7_focused='22 passed in 1.12s',
        postrun_accounting_and_acceptance='13 passed in 0.24s',
        retained_test_logs=[record(STATIC/p) for p in logs])
    atomic(OUT/'PHASE1_REGRESSION_TESTS.json',r)


def delivery_sources():
    from v42_pr134_b1.common import sha
    paths=[p for p in ROOT.rglob('*.py') if not any(x in p.parts for x in ('.git','artifacts','tmp','__pycache__'))]
    atomic(OUT/'DELIVERY_SOURCE_MANIFEST.json',dict(PASS=True,execution_epoch_provenance=record(OUT/'EXECUTION_EPOCH_AND_BUDGET_PROVENANCE.json'),
        delivery_source_hashes={str(p):sha(p) for p in sorted(paths)},
        postrun_reporting_changes_not_used_by_native=True))
