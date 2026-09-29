"""Exactly one native canary entry. Stops at a proved infeasible upstream stage."""
from pathlib import Path
import json
from .prepare import OUT,LOCAL,ROOT,read,record,dump,csv,sha
from .projection import known_planning_gate,capacity_lower_bounds
from v42_native.supervision import supervise
from v42_native.contracts import require


def main():
    bundle=read(OUT/'MAY01_NATIVE_INPUT_BUNDLE.json');known_planning_gate(bundle)
    # The unit-suite receipt is required before the first native invocation.
    import xml.etree.ElementTree as ET
    suites=list(ET.parse(OUT/'PRE_CANARY_TEST_RESULTS.xml').getroot().iter('testsuite'))
    require(suites and all(int(s.attrib.get('errors',0))+int(s.attrib.get('failures',0))==0 for s in suites),'PRE_CANARY_TESTS')
    stage_dir=LOCAL/'canary/A1'
    if stage_dir.exists():
        # The original native launch failed while writing the LP, BEFORE
        # optimize(). Preserve it; permit only the specific filesystem repair.
        failure=read(stage_dir/'stage_receipt.json')
        require(failure['exit_code']!=0 and not (stage_dir/'model_build.json').exists()
                and 'Unable to write to file' in (stage_dir/'worker.log').read_text(encoding='utf8'),
                'NO_RETRY_OF_COMPLETED_OR_STARTED_SOLVE')
        dump('PRE_SOLVE_IO_FAILURE.json',dict(reason='Gurobi Windows Unicode diagnostic path failure before optimize',
            original_receipt=failure,evidence=[record(p,'Preserved pre-solve IO failure') for p in stage_dir.glob('*') if p.is_file()],
            model_or_constraint_changes=False,repair='ASCII temporary diagnostic file, byte-preserving Python copy',
            optimization_attempts_in_failed_launch=0))
        stage_dir=LOCAL/'canary/A1_io_retry'
    require(not stage_dir.exists(),'ONE_NATIVE_CANARY_ONLY_NO_SILENT_RERUN')
    sources=read(OUT/'MAY01_NATIVE_INPUT_MANIFEST.json')['files']
    code=[dict(path=str(p),sha256=sha(p)) for p in list((ROOT/'v42_may01').glob('*.py'))+list((ROOT/'v42_native').glob('*.py'))]
    payload=dict(bundle=str(OUT/'MAY01_NATIVE_INPUT_BUNDLE.json'),bundle_sha=sha(OUT/'MAY01_NATIVE_INPUT_BUNDLE.json'),source_files=sources+code)
    candidate,receipt=supervise('A1','v42_native.may01_worker:worker','v42_native.may01_worker:validator',payload,stage_dir,seconds=600)
    result=read(stage_dir/'projection_result.json') if (stage_dir/'projection_result.json').exists() else dict(status='ERROR',full_A1_infeasible_proven=False)
    require(candidate is None,'PROJECTION_MISLABELED_INCUMBENT')
    if result['full_A1_infeasible_proven']:
        jobs=[r for r in bundle['known_population'] if r['planning_eligible']]
        analytic=capacity_lower_bounds(jobs,bundle['C0_Q50'],sum(bundle['capacities'].values()))
        require(analytic==read(stage_dir/'capacity_lower_bounds.json'),'INDEPENDENT_CERTIFICATE_DRIFT')
        csv('MAY01_RESOURCE_NECESSARY_BOUND.csv',analytic)
    dump('MAY01_A1_RESOURCE_CERTIFICATE.json',dict(**result,supervisor=receipt,
        evidence=[record(p,'Native A1 resource-projection diagnostic') for p in stage_dir.glob('*') if p.is_file()]))
    metrics=[]
    for stage in ('A1','M1','A2','M2'):
        a=stage=='A1';status='INFEASIBLE' if a and result['full_A1_infeasible_proven'] else 'ERROR' if a else 'NOT_RUN_UPSTREAM_A1_'+('INFEASIBLE' if result['full_A1_infeasible_proven'] else 'ERROR')
        row=dict(stage=stage,day='2025-05-01',network='IEEE123',status=status,
            runtime_seconds=receipt['total_wall_seconds'] if a else None,full_MILP_runtime_seconds=None,
            final_gap=None,first_incumbent_seconds=None,binary_count=None,continuous_count=None,constraints=None,
            model_scope='NECESSARY_RESOURCE_RELAXATION' if a else 'NOT_BUILT',
            full_model_built=False,wall_cap_seconds=600,MIPGap_target=.001,incumbent_available=False,
            scientific_PASS=False,native_inputs=True,synthetic_timing_substituted=False)
        dump(f'MAY01_{stage}_SOLVER_METRICS.json',dict(**row,supervisor=receipt if a else None))
        metrics.append(row)
    csv('MAY01_NATIVE_COMPUTATIONAL_CANARY.csv',metrics);csv('MAY01_MODEL_SIZE_AUDIT.csv',metrics)
    csv('MAY01_GAP_TIME_TRACE.csv',[dict(stage='A1',elapsed_seconds=receipt['total_wall_seconds'],status=result['status'],
        incumbent_objective=None,best_bound=None,gap=None,scope='END_OF_RESOURCE_PROJECTION_NO_INCUMBENT')])
    dump('MAY01_WARM_START_AUDIT.json',dict(A1_to_A2_accepted=False,M1_to_M2_accepted=False,
        reason='No A1 incumbent; upstream stop prevents valid downstream handoff',node_count_reduction=None))
    dump('FRESH_AC_MAY01_VALIDATION.json',dict(PASS=False,status='NOT_RUN_NO_FEASIBLE_FINAL_PLANNING_CANDIDATE',
        accepted_schedules=0,Vmin=None,Vmax=None,max_line_loading=None,max_transformer_loading=None,violations=None,
        silent_AC_repair=False,limits_relaxed=False))
    print(json.dumps(dict(A1=result['status'],wall_seconds=receipt['total_wall_seconds'],worst_row=result.get('worst_row'),
        subsequent_blocks='NOT_RUN_UPSTREAM_'+result['status'],Fresh='NOT_RUN'),indent=2))


if __name__=='__main__':main()
