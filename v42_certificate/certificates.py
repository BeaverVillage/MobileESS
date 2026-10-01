"""B3-first certificates; no optimization is performed by this module."""
from .common import *

LABELS={'B1':'_ROUTE','B2':'_ROUTE_MODE','B3':'_BUFFER'}
INHERITED={'B1':'R_ROUTE_ONLY','B2':'R_ACTIVE','B3':'R_BUFFER'}

def analyze():
    assert read(OUT/'NESTING_DOMAIN_VALIDATION.json')['PASS']
    runs={a:read(OUT/(a+'_OPTIMIZATION.json')) for a in WINDOWS if (OUT/(a+'_OPTIMIZATION.json')).exists()}
    assert 'B3' in runs
    old={a:read(PRIOR/(n+'_OPTIMIZATION.json')) for a,n in INHERITED.items()}
    lbs={a:runs[a]['valid_partial_LB'] if a in runs else old[a]['certified_global_LB'] for a in WINDOWS}
    domains={a:set(json.loads(gzip.decompress((PRIOR/(n+'_DOMAIN.json.gz')).read_bytes()))['restored']) for a,n in INHERITED.items()}
    assert domains['B1']<domains['B2']<domains['B3']
    for a,r in runs.items():
        actual=json.loads(gzip.decompress((OUT/(a+'_DOMAIN.json.gz')).read_bytes()))
        assert set(actual['restored'])==domains[a] and not actual['fixed'] and not actual['removed_rows'] and not actual['new_rows']
        assert r['matrix_validation']['PASS'] and r['restored_binary_fractionality']<=TOL
    certs={};rows=[]
    for i,a in enumerate(WINDOWS):
        weaker=list(WINDOWS)[:i+1];stronger=list(WINDOWS)[i:]
        lower_source=max(weaker,key=lambda n:lbs[n]);lower=lbs[lower_source]
        uppers=[(START_UB,'PR112_FULL_ORIGINAL_INTEGER_START')]
        for n,r in runs.items():
            if n in stronger or r['validated_original_UB'] is not None:uppers.append((r['solver_incumbent'],n))
        upper,upper_source=min(uppers,key=lambda z:z[0]);c=interval(lower,upper,runs[a]['solver_status'] if a in runs else None)
        if a in runs:execution='RUN'
        elif c['negative_certificate']:execution='NOT_RUN_NESTING_CERTIFIED'
        elif a=='B2':execution='ELIGIBLE_NOT_YET_RUN' if runs['B3']['direct_interval']['material'] else 'NOT_RUN_GATE_B3_INCONCLUSIVE'
        elif 'B2' not in runs or not runs['B2']['direct_interval']['material']:execution='NOT_RUN_GATE_B2_INCONCLUSIVE'
        else:execution='ELIGIBLE_NOT_YET_RUN'
        status=runs[a]['solver_status'] if a in runs else execution
        lower_source=('NEW_' if lower_source in runs else 'PR112_')+lower_source
        c.update(arm=a,run=a in runs,execution=execution,solver_status=status,
            raw_BestBd=runs[a]['raw_BestBd'] if a in runs else None,
            solver_incumbent=runs[a]['solver_incumbent'] if a in runs else None,
            inherited_solver_status=old[a]['status'],inherited_bound=old[a]['certified_global_LB'],
            inherited_result='COMPUTATIONALLY_INCONCLUSIVE',lower_source=lower_source,upper_source=upper_source,
            solver_status_not_relabelled=True,inclusion_check_PASS=True,
            physical_rows_original=True,restored_binary_count=len(domains[a]),
            nonmaterial_vs_F3=upper-F3<=MATERIAL,global_LB=max(S2,lower),
            optimize_calls=1 if a in runs else 0,
            certificate_type='VALID_LOWER_BOUND_MATERIAL_VS_S2' if c['material'] else 'VALIDATED_FEASIBLE_UPPER_NONMATERIAL_VS_S2'+('_NESTING_TRANSFER' if a not in runs else '') if c['negative_certificate'] else None,
            certificate_valid=bool(c['material'] or c['negative_certificate']),
            solution_source_sha256=sha(OUT/(upper_source+'_SOLUTION.npz')) if upper_source in runs else sha(OUT/'MIP_START_EXACT.npz'))
        certs[a]=c;dump(a+LABELS[a]+'_CERTIFICATE.json',c)
        r=runs.get(a)
        rows.append(dict(arm=a,execution=execution,solver_status=status,partial_LB=lower,partial_UB=upper,interval_width=c['width'],
            global_LB=max(S2,lower),gain_LB_vs_S2=lower-S2,gain_UB_vs_S2=upper-S2,material=c['material'],negative_certificate=c['negative_certificate'],
            tight_interval=c['tight_interval'],conclusion=c['conclusion'],upper_source=upper_source,lower_source=lower_source,
            wall_seconds=r['optimize_wall_seconds'] if r else None,build_seconds=r['build_seconds'] if r else None,
            nodes=r['node_count'] if r else None,root_complete=r['root_complete'] if r else None))
    table('OPTIMUM_INTERVAL_SUMMARY.csv',rows);table('PARTIAL_INTEGRALITY_COMPARISON.csv',rows)
    mode=incremental(certs['B1'],certs['B2']);buffer=incremental(certs['B2'],certs['B3']);case=choose_case(certs)
    crossing=dict(buffer=certs['B3']['material'] and certs['B2']['negative_certificate'],mode=certs['B2']['material'] and certs['B1']['negative_certificate'])
    classification=dict(ROOT_CAUSE_CLASS=case,mode_increment_interval=mode,buffer_increment_interval=buffer,
        threshold_crossing_evidence=crossing,threshold_crossing_alone_not_proof_of_increment_ge_0_001=True,
        B1_B2_B3=certs,primal_mode_quality_is_not_mode_LP_gap_proof=True,
        missing_certificates=[a for a,c in certs.items() if c['conclusion']=='INCONCLUSIVE'],
        no_time_limited_bound_difference_as_exact_effect=True,custom_cut_remedy_implemented=False,
        sequential_execution_order=[a for a in ['B3','B2','B1'] if a in runs])
    dump('ROOT_CAUSE_CLASSIFICATION.json',classification)
    dump('PRODUCTION_AUTHORIZATION.json',dict(authorized=False,execution=False,
        authority='SCOPE_CORRECTION_ADDENDUM.json: B3-first sequential certificate work only; stop and report before production/P2/downstream.',
        original_preregistration_production_gate_superseded=True,native_start_accepted=read(OUT/'MIP_START_NATIVE_ACCEPTANCE.json')['PASS'],
        missing_certificates=classification['missing_certificates'],root_cause_class=case,
        certificate_sequence_report_complete=not any(c['execution']=='ELIGIBLE_NOT_YET_RUN' for c in certs.values()),
        P2_run=False,downstream=False,new_cuts=False))
    print('CERTIFICATE CLASS',case,'new runs',classification['sequential_execution_order'],flush=True)
    return runs,certs,classification
if __name__=='__main__':analyze()
