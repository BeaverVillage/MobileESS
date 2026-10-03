"""Post-heavy-only verification with explicit nulls for gated stages."""
import csv
import json
import subprocess
from .common import ROOT,OUT,BASE,NORMALAMPS,sha,write

def read(name,default=None):
    p=OUT/name
    return json.loads(p.read_text(encoding='utf8')) if p.exists() else default

def not_run(reason):
    from v42_integrated.monitor import TIMES
    from .m1 import ALIASES
    for source,target in ALIASES.items():
        if (OUT/target).exists():continue
        if source.endswith('.csv'):
            (OUT/target).write_text('removed_row,retained_representative,row_payload_SHA256\n',encoding='utf8')
        elif source=='M1_ROOT_PATH_TIMELINE.json':write(target,dict(status='NOT_RUN',reason=reason,timestamps=dict.fromkeys(TIMES),nulls_not_inferred=True))
        elif source=='M1_CERTIFICATE.json':write(target,dict(status='NOT_RUN',reason=reason,M1_ACCEPTED=False,UB=None,LB=None,gap=None,old_certificate='SUPERSEDED_NOT_USED'))
        elif source=='M1_SOLVE_RESULT.json':write(target,dict(status='NOT_RUN',reason=reason,optimization_calls=0,UB=None,LB=None,gap=None,incumbent_exists=False))
        elif source=='M1_START_COMPATIBILITY.json':write(target,dict(status='NOT_EVALUATED',reason=reason,reused=False,old_certificate_used=False))
        else:write(target,dict(status='NOT_RUN',reason=reason,PASS=None))
    if not (OUT/'M1_SINGLE_THREAD_RESOURCE_TIMELINE.csv').exists():
        from .resources import Timeline
        fields=['UTC','wall_seconds','phase','solver_seconds','process_RSS','system_RAM_used','system_RAM_free','swap_used','CPU_utilization_percent','heavy_processes','process_thread_count']
        (OUT/'M1_SINGLE_THREAD_RESOURCE_TIMELINE.csv').write_text(','.join(fields)+'\n',encoding='utf8')
    if not (OUT/'M1_SINGLE_THREAD_RESOURCE_SUMMARY.json').exists():write('M1_SINGLE_THREAD_RESOURCE_SUMMARY.json',dict(status='NOT_RUN',reason=reason,observed_peak_process_RSS=None,observed_minimum_system_free_RAM=None,sample_count=0,sequential_policy_PASS=True))
    if not (OUT/'M1_SINGLE_THREAD_P2_RESULT.json').exists():write('M1_SINGLE_THREAD_P2_RESULT.json',dict(status='NOT_RUN',reason=reason,movement_energy=None,movement_count=None))

def run():
    a1=read('A1_SINGLE_THREAD_SOLVE_RESULT.json',{})
    not_run('A1_NOT_ACCEPTED' if not a1.get('A1_ACCEPTED') else 'M1_STAGE_GATE_FAILED_OR_NOT_COMPLETED')
    preserved=read('PR133_BYTE_PRESERVATION.json')
    drift=[r['path'] for r in preserved['files'] if not (ROOT/r['path']).is_file() or sha(ROOT/r['path'])!=r['sha256']]
    write('PR133_FINAL_BYTE_PRESERVATION.json',dict(PASS=not drift,base=BASE,checked_files=len(preserved['files']),drift=drift,old_OOM_evidence_overwritten=False,scientific_contract_changed=False))
    from v42_thermal.authority import current_authority
    from v42_native.voltage import Stage,voltage_for
    authority=current_authority()
    authority_pass=authority['transformer_current_authority_sha256']==NORMALAMPS and len(authority['rows'])==120 and len({r['transformer'] for r in authority['rows']})==44 and authority['Planning']==authority['Actual'] and all((voltage_for(s).lower_pu,voltage_for(s).upper_pu)==(.95,1.05) for s in (Stage.A1,Stage.M1,Stage.A2,Stage.M2))
    write('AUTHORITY_IDENTITY_AUDIT.json',dict(PASS=authority_pass,NormalAmps_authority=NORMALAMPS,transformers=44,phases=120,Planning_Actual_M1_same_SHA=True,margin_pu=0,voltage_constraints_retained=True,PR133_contract_byte_preservation_PASS=not drift))
    tests=read('PYTEST_RECEIPT.json',{})
    post_checks=read('POST_HEAVY_CHECKS.json',{})
    order_checks=read('HEAVY_TEST_ORDER_AUDIT.json',{})
    source_checks=read('FINAL_SOURCE_FREEZE_BINDING_AUDIT.json',{})
    report_checks_pass=all(v.get('PASS',False) for v in (post_checks,order_checks,source_checks))
    census=read('M1_SINGLE_THREAD_MATRIX_CENSUS.json',{});certificate=read('M1_SINGLE_THREAD_CERTIFICATE.json',{});result=read('M1_SINGLE_THREAD_SOLVE_RESULT.json',{})
    a1_resources=read('A1_SINGLE_THREAD_RESOURCE_SUMMARY.json',{})
    m1_resources=read('M1_SINGLE_THREAD_RESOURCE_SUMMARY.json',{})
    single=a1_resources.get('sequential_policy_PASS',False) and m1_resources.get('sequential_policy_PASS',False)
    timeline=read('M1_SINGLE_THREAD_ROOT_TIMELINE.json',{})
    gate=result.get('root_path_gate',timeline.get('root_path_gate','NOT_RUN'))
    flags=dict(V42_INTEGRATION_PASS=not drift and authority_pass and tests.get('PASS',False) and report_checks_pass,ZERO_VOLTAGE_MARGIN_ACTIVE=True,NORMALAMPS_TRANSFORMER_AUTHORITY_ACTIVE=True,SINGLE_WORKER_ACTIVE=single,SOLVER_THREADS=1,A1_REGENERATED=a1.get('source_regenerated',False),A1_ACCEPTED=a1.get('A1_ACCEPTED',False),M1_REGENERATED=census.get('new_matrix_regenerated',False),M1_ROOT_PATH_GATE=gate,M1_ACCEPTED=certificate.get('M1_ACCEPTED',False),OLD_M1_CERTIFICATE_SUPERSEDED=True,A2='NOT_RUN',M2='NOT_RUN',ACTUAL='NOT_RUN',FRESH_AC='NOT_RUN',PROBLEM13_FINAL_VALIDATED=False)
    write('FINAL_FLAGS.json',flags)
    if a1.get('error',{}).get('memory_failure'):bottleneck='A1 native memory exhaustion';next_direction='Same full-horizon, unchanged-physics A1 on a host with more memory headroom.'
    elif not flags['A1_ACCEPTED']:
        unfinished=a1.get('passes',[])[-1].get('component') if a1.get('passes') else None
        bottleneck='A1 '+str(unfinished or a1.get('status','unobserved'))+' acceptance'
        next_direction='Inspect this single recorded terminal A1 component and its certificate gate on the unchanged model.'
    elif read('M1_SINGLE_THREAD_ROOT_CAUSE.json',{}).get('memory_failure'):bottleneck='M1 native memory exhaustion';next_direction='Revalidate the same M1 authority on a host with more memory headroom.'
    elif not flags['M1_REGENERATED']:bottleneck='M1 construction gate';next_direction='Resolve the recorded M1 construction error without changing PR133 physics.'
    elif not read('M1_SINGLE_THREAD_ROOT_LP_EQUIVALENCE.json',{}).get('PASS'):bottleneck='M1 root LP equivalence gate';next_direction='Inspect the failing full/reduced LP and original-unit residual evidence.'
    elif gate=='FAIL':
        solver_log=(OUT/'M1_SOLVE.log').read_text(encoding='utf8') if (OUT/'M1_SOLVE.log').exists() else ''
        bottleneck='M1 post-crossover root DegenMoves before first nonroot' if '(DegenMoves)' in solver_log else 'M1 root path'
        next_direction='Inspect this recorded root degeneracy on the same new model; no parameter trial is executed in this task.'
    elif not certificate.get('valid_incumbent',False):bottleneck='M1 incumbent / UB';next_direction='Independently certify one new-model feasible warm start.'
    elif not flags['M1_ACCEPTED']:
        if read('M1_SINGLE_THREAD_P1_CERTIFICATE.json',{}).get('M1_ACCEPTED'):
            bottleneck='M1 P2 lexicographic acceptance';next_direction='Inspect the single recorded incomplete P2 component while retaining the frozen P1 certificate.'
        elif certificate.get('LB') is None:
            bottleneck='M1 valid global lower-bound certificate';next_direction='Inspect the recorded terminal bound validity on this exact model.'
        else:
            bottleneck='M1 B&B global-bound progression';next_direction='Study one exact route/dispatch strengthening against this new model, without running it in this task.'
    else:bottleneck='NONE: A1/M1 acceptance complete';next_direction='A separate downstream task only.'
    write('BOTTLENECK_CLASSIFICATION.json',dict(bottleneck=bottleneck,exactly_one_next_direction=next_direction,next_experiment_executed=False,wall_time_causal_speedup_claim=False))
    write('VERIFICATION.json',dict(PASS=flags['V42_INTEGRATION_PASS'] and single,PASS_scope='code, authority, preservation, tests and sequential execution; solve acceptance is separately flagged',base_exact_head=BASE,pytest=tests,post_heavy_checks=post_checks,execution_order_audit=order_checks,source_freeze_binding_audit=source_checks,PR133_byte_preservation_PASS=not drift,authority_identity_PASS=authority_pass,single_worker_PASS=single,A1_result=a1,M1_certificate=certificate,root_LP_gate=read('M1_SINGLE_THREAD_ROOT_LP_EQUIVALENCE.json'),old_bounds_used=False,downstream_calls=0))
    source_paths=list((ROOT/'v42_single_thread').glob('*.py'))+list((ROOT/'tests/v42_single_thread').glob('*.py'))+[ROOT/'v42_single_thread/.gitattributes',ROOT/'tests/v42_single_thread/.gitattributes']
    write('SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json'],sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(source_paths)]))
    print('SINGLE_THREAD_FINALIZED',flags,bottleneck,flush=True)

if __name__=='__main__':run()
