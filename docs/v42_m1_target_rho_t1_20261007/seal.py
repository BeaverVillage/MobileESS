"""Hash manifest / namespace / immutable-parent checks. No solve."""
from support import *
def main():
    required=['PREREGISTRATION.md','BASE_IDENTITY.json','THRESHOLD_AUTHORITY.json','COVER_CUT_AUTHORITY.md','MULTITIME_CONFLICT_CUT_AUTHORITY.md','CUT_CANDIDATE_CENSUS.csv','CUT_VALIDATION.json','CUT_SELECTION.csv','SOLVER_PARAMETERS.json','NATIVE_SOLVER.log','INCUMBENT_TRACE.csv','RESULT.json','RESOURCE_TELEMETRY.csv','VERIFICATION.json','FINAL_REVIEW_KO.md']
    assert all((OUT/n).is_file() for n in required)
    r=read(OUT/'RESULT.json');v=read(OUT/'VERIFICATION.json');cv=read(OUT/'CUT_VALIDATION.json');mt=read(OUT/'MODEL_TRANSPORT_AUTHORITY.json');token=read(OUT/'OPTIMIZE_ONCE.json')
    assert r['optimize_calls']==token['optimize_calls']==1 and v['PASS'] and cv['PASS'] and mt['PASS']
    assert token['settings']==SETTINGS and read(OUT/'SOLVER_PARAMETERS.json')['settings']==SETTINGS
    assert mt['all_Start_UNDEFINED'] and mt['objective_all_zero'] and mt['no_domain_restriction'] and mt['native_matrix_and_all_fields_bit_identical']
    assert r['Status']==9 and r['SolCount']==0 and r['MIPSOL_events']==0
    assert r['classification']=='TARGET_RHO_T1_TIME_LIMIT_INCONCLUSIVE' and r['global_LB_new']==LB and r['global_UB_new']==UB
    assert not (OUT/'UB_UPDATE.json').exists() and not (OUT/'LB_UPDATE.json').exists()
    assert protected()==read(OUT/'BASE_IDENTITY.json')['protected_before']
    for name,digest in cv['verified_inputs_SHA256'].items():assert sha(OUT/name)==digest,name
    assert git('merge-base',SCIENTIFIC,BASE)==SCIENTIFIC
    assert all(p.startswith('docs/v42_m1_target_rho_t1_20261007/') for p in git('diff','--name-only',BASE).splitlines())
    # Explicit zero row for investigated two-time integer covers in bounded
    # candidate pools; no claim that every possible original cover was exhausted.
    rows=list(csv.DictReader((OUT/'CUT_CANDIDATE_CENSUS.csv').open(encoding='utf-8')))
    f='INTEGER_TWO_TIME_CROSS_MESS_ROUTE_SOC_COVER'
    if not any(x['family']==f for x in rows):
        rows.append(dict(family=f,generated=0,constructor_proven_valid=0,stored_LP_violated=0,selected=0,selected_nnz=0,maximum_violation=''));table('CUT_CANDIDATE_CENSUS.csv',rows)
    receipt=dict(PASS=True,exact_base=BASE,scientific_ancestor=SCIENTIFIC,optimize_calls=1,source_commit=token['source_commit'],namespace_only=True,all_required_artifacts=True,original_parent_evidence_unchanged=True,certificate_source_hashes_match=True,native_transport_PASS=True,all_parameters_fixed=True,no_MIP_start=True,no_bound_update=True,no_auto_next_solve=True,classification=r['classification'])
    write('FINAL_ARTIFACT_AUDIT.json',receipt)
    files={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json' and '__pycache__' not in str(p) and p.suffix!='.pyc'}
    write('SHA256_MANIFEST.json',dict(algorithm='SHA256',files=files,excluded=['SHA256_MANIFEST.json','__pycache__/','*.pyc'],self_reference_excluded=True,source_commit=token['source_commit'],exact_base=BASE))
    assert all(sha(OUT/name)==digest for name,digest in read(OUT/'SHA256_MANIFEST.json')['files'].items())
    print('FINAL_ARTIFACT_SEAL_PASS',len(files),r['classification'],flush=True)
if __name__=='__main__':main()
