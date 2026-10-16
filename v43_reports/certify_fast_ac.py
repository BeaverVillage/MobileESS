"""Certify paired real short events; never turn them into Actual96 evidence."""
from pathlib import Path
import numpy as np

from v43.common import ROOT,DOC,read,record,verify_records,atomic,now


def run(reference,shadow):
    reference,shadow=Path(reference),Path(shadow)
    roots=(reference,shadow)
    results=[read(p/'RESULT.json') for p in roots]
    for p,r in zip(roots,results):
        if not r['PASS'] or r['Native_calls'] or r['inflight'] is not None:
            raise ValueError('PAIRED_CANARY_NOT_COMPLETED_AND_RECONCILED')
        freeze=read(p.with_name(p.name+'.CORRECTIVE_SOURCE_FREEZE.json'))
        verify_records(freeze['sources'])
        if freeze['control_slots']!=25:raise ValueError('EXPLICIT_25_SLOT_CANARY_REQUIRED')
    if read(reference/'CASE/CASE_BINDINGS.json')['case_sha']!=read(shadow/'CASE/CASE_BINDINGS.json')['case_sha']:
        raise ValueError('PAIRED_CASE_DRIFT')
    pa,pb=[read(p/'CORRECTIVE_POLICY_RECEIPTS.json')['policies'] for p in roots]
    for x,y in zip(pa,pb):
        # Reference hashes include the attempt-local initialization file path.
        # The source/case/numeric-response bindings still must match exactly.
        sx={k:v for k,v in x['spec'].items() if k!='reference_target_sha'}
        sy={k:v for k,v in y['spec'].items() if k!='reference_target_sha'}
        if sx!=sy:raise ValueError('PAIRED_POLICY_NUMERIC_OR_AUTHORITY_DRIFT')
    checks=[]
    for variant in ('C0','C1'):
        a,b=reference/variant,shadow/variant
        ea,eb=read(a/'ACTUAL_EVENT_LEDGERS.json'),read(b/'ACTUAL_EVENT_LEDGERS.json')
        keys=('queue_ledger','job_event_ledger','reservation_ledger','cc4_depletion_ledger',
              'migration_receipts','qos_ledger','qos_budget_ledger','receipt')
        for key in keys:
            if ea[key]!=eb[key]:raise ValueError('PAIRED_EVENT_DRIFT:'+variant+':'+key)
        normalize=lambda rows:[{k:v for k,v in r.items() if k not in ('decision_seconds','policy_sha')} for r in rows]
        if normalize(ea['rule_consumption_receipt'])!=normalize(eb['rule_consumption_receipt']):
            raise ValueError('PAIRED_POLICY_ACTION_DRIFT')
        with np.load(a/'ACTUAL_PHYSICAL.npz',allow_pickle=False) as za,np.load(b/'ACTUAL_PHYSICAL.npz',allow_pickle=False) as zb:
            if set(za.files)!=set(zb.files):raise ValueError('PAIRED_PHYSICAL_AXIS_DRIFT')
            for key in za.files:
                same=np.array_equal(za[key],zb[key],equal_nan=True) if za[key].dtype.kind in 'fci' else np.array_equal(za[key],zb[key])
                if not same:raise ValueError('PAIRED_PHYSICAL_DRIFT:'+variant+':'+key)
        aa,ab=read(a/'CURRENT_AC_RECEIPTS.json'),read(b/'CURRENT_AC_RECEIPTS.json')
        if len(aa)!=len(ab):raise ValueError('PAIRED_CANDIDATE_COUNT_DRIFT')
        for x,y in zip(aa,ab):
            for key in ('uid','time_seconds','input_sha','cache_hit','PASS'):
                if x[key]!=y[key]:raise ValueError('PAIRED_CANDIDATE_DRIFT:'+key)
            for key in ('PASS','converged','violations','native_state','voltage_min_pu',
                        'voltage_max_pu','maximum_phase_line_loading'):
                if x['current'][key]!=y['current'][key]:raise ValueError('PAIRED_CURRENT_DRIFT:'+key)
        metrics=read(b/'AC_ALGORITHM_METRICS.json');eq=metrics['equivalence']
        if len(eq)!=results[1]['variants'][variant]['Current_AC_calls'] or not eq:
            raise ValueError('EVERY_SHADOW_CACHE_MISS_REQUIRES_FULL_REFERENCE')
        for item in eq:
            if not all(item[k] is True for k in ('PASS','taps_caps_exact','all_node_voltages_exact',
                    'all_branch_phase_amps_and_loading_exact','all_candidate_PASS_FAIL_exact')):
                raise ValueError('SHADOW_EXACT_PHYSICAL_EQUIVALENCE_FAILED')
        for p in (a,b):
            fresh=read(p/'FRESH_ORIGINAL7_AC.json')['physical_steps']
            if len(fresh)!=25 or not all(s['PASS'] for s in fresh):raise ValueError('SHORT_INDEPENDENT_FRESH_FAILED')
        counts=lambda key:{name:sum(e[key][name] for e in eq) for name in eq[0][key]}
        checks.append(dict(variant=variant,candidate_requests=len(aa),independent_cache_miss_comparisons=len(eq),
            actual_UID_site_time_GPU_exact=True,all_physical_arrays_exact=True,all_event_ledgers_exact=True,
            all_candidate_PASS_FAIL_exact=True,all_taps_voltages_branch_phase_measurements_exact=True,
            optimized_candidate_wall_seconds=sum(e['optimized_wall_seconds'] for e in eq),
            reference_candidate_wall_seconds=sum(e['reference_wall_seconds'] for e in eq),
            optimized_counts=counts('optimized_counts'),reference_counts=counts('reference_counts'),
            measured_reference_event_wall_seconds=results[0]['variants'][variant]['elapsed_wall_seconds'],
            measured_shadow_event_wall_seconds=results[1]['variants'][variant]['elapsed_wall_seconds'],
            shadow_wall_includes_two_AC_paths=True,
            unknown_observed=sum(x['origin_unknown'] for x in eb['queue_ledger']),
            unknown_started=sum(x['origin_unknown'] and x['admitted_time'] is not None for x in eb['queue_ledger']),
            max_reference_tick_seconds=results[0]['variants'][variant]['tick_Max_seconds'],
            max_shadow_tick_seconds=results[1]['variants'][variant]['tick_Max_seconds']))
    real=read(DOC/'V43_CURRENT_AC_REAL_PREFIX_EQUIVALENCE_POINTER.json')['result'];verify_records([real])
    previous=read(real['path']);source=record(ROOT/'v43_corrective/current_ac.py')
    if not previous['PASS'] or previous['optimized_source']!=source:raise ValueError('REAL_PREFIX_SOURCE_DRIFT')
    proof=dict(UTC=now(),production_fast_path_authorized=True,optimized_source=source,
        paired_actual_UID_site_time_GPU_exact=True,checks=checks,real_prefix_evidence=real,
        paired_results=[record(p/'RESULT.json') for p in roots],
        original_physical_bands_unchanged=True,current_candidates_always_fully_measured=True,
        past_SolveSnap_replay_retained=True,engine_state_clone_certified=False,
        source_C1_MESS_and_observed_prefix_hash_required=True,
        new_B0_full_Actual_wall_seconds=None,Actual96_certified=False,Fresh96_certified=False,
        scope='AC_MEASUREMENT_REUSE_MECHANISM_WITH_EXACT_RUNTIME_BINDING; NOT_ARM_SERVICE_OR_FULL_DAY_CERTIFICATE')
    path=DOC/'V43_CURRENT_AC_PRODUCTION_CERTIFICATION.json';atomic(path,proof)
    atomic(DOC/'V43_CURRENT_AC_PRODUCTION_CERTIFICATION_POINTER.json',dict(certificate=record(path)))
    return proof


if __name__=='__main__':
    import sys
    run(*sys.argv[1:])
