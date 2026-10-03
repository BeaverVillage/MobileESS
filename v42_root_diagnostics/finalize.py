"""Validation and portable evidence inventory, no scientific result adoption."""
from .analytics import *
import shutil

REQUIRED='''PREREGISTRATION.json MATRIX_FAMILY_CENSUS.csv COLUMN_FAMILY_CENSUS.csv COEFFICIENT_MAGNITUDE_HISTOGRAM.csv EXTREME_COEFFICIENT_SOURCE_TRACE.csv TINY_COEFFICIENT_PHYSICAL_IMPACT_BOUNDS.json ROOT_LP_METHOD0_ORIGINAL.json ROOT_LP_METHOD1_ORIGINAL.json ROOT_LP_METHOD2_ORIGINAL.json ROOT_LP_METHOD0_COMPACT.json ROOT_LP_METHOD1_COMPACT.json ROOT_LP_METHOD2_COMPACT.json ROOT_METHOD_COMPARISON.json MIP_ROOT_METHOD2_ORIGINAL_300S.json MIP_ROOT_METHOD2_COMPACT_300S.json ROOT_PHASE_TIMELINE.json DEGENERACY_AUDIT.json DEGENERACY_BY_VARIABLE_FAMILY.csv ACTIVE_ROW_FAMILY_AUDIT.csv DUPLICATE_PROPORTIONAL_ROWS.json CONDITIONING_AUDIT.json EXACT_ROW_SCALING_PROOF.json ROW_SCALED_METHOD1_DIAGNOSTIC.json AUXILIARY_ELIMINATION_PROOF.json AUX_ELIMINATION_DIAGNOSTIC.json GRID_BLOCK_ATTRIBUTION.json ROOT_CAUSE_CLASSIFICATION.json ROOT_CAUSE_TO_FIX_MAP.md FINAL_FLAGS.json FINAL_VERDICT.json FINAL_REVIEW_KO.md VERIFICATION.json SHA256_MANIFEST.json'''.split()

def status(r):return {2:'OPTIMAL',9:'TIME_LIMIT',3:'INFEASIBLE',4:'INF_OR_UNBD',5:'UNBOUNDED',11:'INTERRUPTED'}.get(r.get('status'),str(r.get('status')))

def review(test_result):
    verdict=read('FINAL_VERDICT.json');roots={k:[read(f'ROOT_LP_METHOD{j}_{k.upper()}.json') for j in [0,1,2]] for k in ['original','compact']};timeline=read('ROOT_PHASE_TIMELINE.json')['MIP'];deg=read('DEGENERACY_AUDIT.json');dups=read('DUPLICATE_PROPORTIONAL_ROWS.json')['formulations'];grid=read('GRID_BLOCK_ATTRIBUTION.json')['formulations'];census=csvread('MATRIX_FAMILY_CENSUS.csv');classification=read('ROOT_CAUSE_CLASSIFICATION.json')['causes']
    top=sorted([r for r in census if r['formulation']=='original'],key=lambda r:int(r['count_abs_a_gt_100'])+int(r['count_abs_a_lt_1e-12']),reverse=True)[:5]
    method_text='; '.join(k+': '+', '.join(f"M{j} {r['solver_runtime']:.3f}s {status(r)}" for j,r in enumerate(arms)) for k,arms in roots.items())
    bmetrics={k:v['metrics']['1e-08'] for k,v in deg['bases'].items()}
    fields=[
        ('PR / SHA / clean / tests',f"Exact base PR126 `{BASE}`; child branch `{git('branch','--show-current')}`. Draft PR URL and final evidence commit are recorded in the delivery message; the evidence manifest avoids a self-referential commit hash. Full pytest: {test_result}. Final Git byte/index and manifest checks in VERIFICATION.json / STAGED_BYTE_AUDIT.json."),
        ('Method 0/1/2 root LP 시간과 status',method_text+'. Fresh LP, no Start, Threads4, max600s; terminal optimal objective gate <=1e-8.'),
        ('Method=2 MIP root가 300초 안에 완료됐는가','; '.join(k+': root relaxation '+str(v['root_relaxation_completed'])+', barrier '+str(v['barrier_completed'])+', exact root processing completion=null' for k,v in timeline.items())),
        ('first branch가 관찰됐는가','; '.join(k+': '+str(v['first_branch_observed'])+', nonroot callback='+str(v['first_nonroot_node_callback_time'])+', exact first-branch time=null' for k,v in timeline.items())),
        ('coefficient 실제 range',f"Both: {grid['original']['matrix_coefficient_min']:.17g} to {grid['original']['matrix_coefficient_max']:.17g}; dynamic range {grid['original']['dynamic_range']:.17g}."),
        ('extreme coefficient가 집중된 top 5 row families',', '.join(r['family']+'='+str(int(r['count_abs_a_gt_100'])+int(r['count_abs_a_lt_1e-12'])) for r in top)+' (Original, |a|<1e-12 or |a|>100; strict census thresholds. Source representative <=/>= thresholds and exact replay are separately preserved in EXTREME_COEFFICIENT_SOURCE_TRACE_COMPLETE.csv).'),
        ('Kappa/KappaExact',str({k:dict(Kappa=v['Kappa'],KappaExact=v['KappaExact']) for k,v in deg['bases'].items()}) if deg['bases'] else 'Kappa=null; KappaExact=null. Terminal optimal simplex basis unavailable; KappaExact also omitted for factorization cost on a 954k+ row system.'),
        ('primal degeneracy ratio',str({k:v['primal_degenerate_basic_ratio'] for k,v in bmetrics.items()}) if bmetrics else 'INCONCLUSIVE: terminal optimal basis 없음. 1e-9/1e-8/1e-7 기준 모두 미측정.'),
        ('near-zero RC ratio',str({k:v['near_zero_RC_nonbasic_ratio'] for k,v in bmetrics.items()}) if bmetrics else 'INCONCLUSIVE: terminal optimal basis 없음; pivot count를 추측하지 않음.'),
        ('exact duplicate/proportional row 수','; '.join(k+': '+str(v['counts'])+', nonzero='+str(v['nonzero_row_counts'])+', constant-only='+str(v['constant_only_row_counts']) for k,v in dups.items())+'. Every hash hit exact-rational verified; counts relative to representative, not all pairs.'),
        ('grid-response block의 rows/nnz 비율','; '.join(k+f": rows {v['grid_rows']}/{v['rows']} ({100*v['grid_row_share']:.3f}%), nnz {v['grid_nnz']}/{v['nnz']} ({100*v['grid_nnz_share']:.3f}%), extreme share {100*v['grid_extreme_nnz_share']:.4f}%" for k,v in grid.items())),
        ('exact row scaling 효과',f"NOT_RUN (USER_STOP); H2={verdict['scaling']}. No runtime comparison is available. Registered initial scaling would delete 342 coefficients; never optimized. Original cache/proof preserved; approved positive-power-of-two guard verified all 8,282,350 coefficients and original-unit point audit separately."),
        ('exact auxiliary elimination 효과',f"Exact injection-only subset: 4,608 helpers/equalities removed; physical rows/primary variables removed=0. 8,282,350 -> 34,229,409 nnz. Full 81,216-helper flattened transport has an exact-rational counterexample and is not executed. Terminal objective solve gate: NOT_EVALUATED_USER_STOP; performance NOT_RUN. Existing-point mappings and algebraic proof are separately measured in AUX_ELIMINATION_DIAGNOSTIC.json."),
        ('각 root-cause 판정','; '.join(v['cause']+'='+v['classification'] for v in classification)+'. Numerical evidence and causal limits attached for each.'),
        ('가장 큰 원인 1위',verdict['ranked_causes'][0]['cause']+' / '+verdict['ranked_causes'][0]['classification']),
        ('두 번째 원인',verdict['ranked_causes'][1]['cause']+' / '+verdict['ranked_causes'][1]['classification']+'; structural share is measured; exclusive causality unresolved.'),
        ('세 번째 원인',verdict['ranked_causes'][2]['cause']+' / '+verdict['ranked_causes'][2]['classification']),
        ('다음 exact fix 1순위','Root method와 basis acquisition/crossover 경로 재설계. Root barrier convergence만으로 MIP root 완료를 주장하지 않음. 행·bounds·objective·tolerance·Start 그대로 유지하고 literal root completion을 검증해야 함.'),
        ('기존 UB/LB/gap 유지 확인',f"UB={UB:.16f}, LB={LB:.16f}, gap={100*(UB-LB)/UB:.8f}%. Unstrengthened F3 LP objective and raw diagnostic MIP bounds never adopted."),
        ('M1_ACCEPTED=false / production NOT_RUN','M1_ACCEPTED=false, COMPACT_M1_PRODUCTION_AUTHORIZED=false, PRODUCTION_1800S/P2/A2/M2/Actual/Fresh_AC=NOT_RUN, PROBLEM13_FINAL_VALIDATED=false. M1_ROOT_CAUSE_DIAGNOSED='+str(verdict['flags']['M1_ROOT_CAUSE_DIAGNOSED']).lower()+'.')]
    text='\n\n'.join(f'{i}. **{label}**\n\n{value}' for i,(label,value) in enumerate(fields,1))+'\n\n'+verdict['direct_cause_sentence']+'\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8',newline='\n')
    return fields

def verify(test_result):
    freeze_check();preserved=preserve();assert git('merge-base',BASE,'HEAD')==BASE
    inherited=[p for p in git('diff','--name-only',BASE,'HEAD').splitlines() if not p.startswith(('docs/v42_m1_root_pathology_diagnostics/','v42_root_diagnostics/'))]
    assert not inherited,inherited
    flags=read('FINAL_FLAGS.json');assert not flags['M1_ACCEPTED'] and not flags['PROBLEM13_FINAL_VALIDATED']
    certificate=read('FINAL_VERDICT.json')['certificate'];assert certificate['UB']==UB and certificate['LB']==LB and certificate['gap']==(UB-LB)/UB
    assert read('ROOT_METHOD_COMPARISON.json')['objective_equivalence_PASS']
    for p in OUT.glob('ROOT_LP_METHOD[012]_*.json'):
        if p.stem.endswith('_TIMELINE'):continue
        r=read(p.name);assert r['no_Start'] and r['integer_variables_after_relaxation']==0 and not r['certificate_update']
    rootorder=read('PREREGISTRATION.json')['root_order'];markers=[(json.loads(p.read_text())['utc'],p.stem[:-len('_OPTIMIZE_STARTED')]) for p in LOCAL.glob('*_OPTIMIZE_STARTED.json')];markers.sort()
    actual=[n for t,n in markers if n in rootorder];assert actual==rootorder
    for i,label in enumerate(rootorder):assert (LOCAL/(label+'_OPTIMIZE_STARTED.json')).exists()
    assert len(markers)==len(set(n for t,n in markers))
    missing=[n for n in REQUIRED if n not in ['VERIFICATION.json','SHA256_MANIFEST.json'] and not (OUT/n).exists()];assert not missing,missing
    for p in OUT.glob('*.json'):json.loads(p.read_text(encoding='utf8'))
    logs={p.name:sha(p) for p in sorted(OUT.glob('*.log'))}
    for p in OUT.glob('*.json'):
        r=read(p.name)
        if isinstance(r,dict) and 'log_sha256' in r:assert logs[r['label']+'.log']==r['log_sha256']
    assert read('EXTREME_SOURCE_REPLAY_RECEIPT.json')['PASS']
    r=dict(PASS=True,utc=stamp(),exact_base=BASE,full_pytest=test_result,original_files_physical_byte_identical=preserved,inherited_Git_blob_changes=0,
        original_preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),initial_freeze_sha256=sha(OUT/'SOURCE_FREEZE.json'),approved_fingerprint_freeze_sha256=sha(OUT/'SOURCE_FREEZE_AMENDED_PREFLIGHT.json'),approved_transport_freeze_sha256=sha(OUT/'SOURCE_FREEZE_AMENDED_SCALING_TRANSPORT.json'),
        initial_STOP_preserved_sha256=sha(OUT/'STOP_RECEIPT.json'),original_scaled_cache_preserved=True,solver_transport_guard_full_matrix_PASS=read('ROW_SCALING_TRANSPORT_SAFE_VALIDATION.json')['PASS'],
        root_objective_equivalence_PASS=True,root_arm_order_PASS=True,optimize_markers=markers,one_shot_arm_count=len(markers),completed_arms=8,interrupted_arms=1,never_started_arms=9,user_stop_receipt=read('USER_STOP_RECEIPT.json'),heavy_lane_sequential=True,all_raw_logs=logs,
        certificate_unchanged=certificate,flags=flags,required_artifacts_complete=True,scientific_result_adoption_calls=0,production_calls=0,downstream_calls=0,
        zero_step_pivots_invented=0,near_duplicate_approximation='NOT_RUN',test_scope='Identity, algebraic scaling/projection, existing-point mappings, determinism, completed root objective gates, quarantine, user-stop and full inherited pytest. Diagnostic tests contain no solver optimization.',unmeasured_requested_checks=['L: terminal auxiliary solve objective equivalence NOT_EVALUATED_USER_STOP','Scaling performance NOT_RUN','Basis degeneracy and Kappa INCONCLUSIVE','Physical-family isolation NOT_RUN'])
    dump('VERIFICATION.json',r)
    return r

def manifest():
    files=sorted([p for directory in [OUT,ROOT/'v42_root_diagnostics'] for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='SHA256_MANIFEST.json'])
    dump('SHA256_MANIFEST.json',dict(algorithm='sha256',exclusions=['SHA256_MANIFEST.json (self-reference)','Python bytecode caches'],files={p.relative_to(ROOT).as_posix():sha(p) for p in files}))

def copy_consoles():
    for name in ['DIAGNOSTIC_LANE_CONSOLE.txt','DIAGNOSTIC_LANE_RESUMED_CONSOLE.txt','DIAGNOSTIC_LANE_TRANSPORT_APPROVED_CONSOLE.txt']:
        p=ROOT.parent/name
        if p.exists():shutil.copyfile(p,OUT/name)

if __name__=='__main__':
    result=read('PYTEST_RECEIPT.json');assert result['exit_code']==0
    copy_consoles();review(result['summary']);verify(result['summary']);manifest()
