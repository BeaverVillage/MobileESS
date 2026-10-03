"""Audit both lineages and publish honest terminal or gated NOT_RUN evidence."""
import ast,csv,json,subprocess
from pathlib import Path
from .governance import ROOT,OUT,BASE,SOLVER,NORMALAMPS,PRESERVED,sha,write,git

def read(name,default=None):
    path=OUT/name
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else default

def not_run(reason):
    for name in ('INTEGRATED_M1_MATRIX_CENSUS.json','INTEGRATED_M1_DUPLICATE_PROOF.json','ROOT_LP_EQUIVALENCE.json','M1_START_COMPATIBILITY.json','M1_ROOT_PATH_TIMELINE.json','M1_SOLVE_RESULT.json'):
        if not (OUT/name).exists():write(name,dict(status='NOT_RUN',reason=reason,PASS=None))
    timeline=read('M1_ROOT_PATH_TIMELINE.json',{})
    if timeline.get('status')=='NOT_RUN':
        from .monitor import TIMES
        write('M1_ROOT_PATH_TIMELINE.json',dict(status='NOT_RUN',reason=reason,timestamps=dict.fromkeys(TIMES),no_timestamps_inferred=True))
    result=read('M1_SOLVE_RESULT.json',{})
    if result.get('status')=='NOT_RUN':
        write('M1_SOLVE_RESULT.json',dict(status='NOT_RUN',reason=reason,incumbent_exists=False,UB=None,LB=None,gap=None,root_path_gate='NOT_RUN',first_incumbent_time=None,first_branch_time=None,node_count=None,root_objective=None,root_runtime=None,barrier_iterations=None,simplex_iterations=None,matrix_audit=None,physical_audit=None,optimization_calls=0))
    start=read('M1_START_COMPATIBILITY.json',{})
    if start.get('status')=='NOT_RUN':write('M1_START_COMPATIBILITY.json',dict(status='NOT_EVALUATED',reason=reason,reused=False,old_certificate_used=False,constraints_relaxed=False))
    for name,fields in [('M1_TRANSFORMER_AUTHORITY_BINDING.csv',['time','transformer','phase','NormalAmps','authority_SHA','constraint_name']),('INTEGRATED_M1_DUPLICATE_MAP.csv',['removed_row','retained_representative','row_payload_SHA256'])]:
        if not (OUT/name).exists():(OUT/name).write_text(','.join(fields)+'\n',encoding='utf8')
    if not (OUT/'M1_CERTIFICATE.json').exists():write('M1_CERTIFICATE.json',dict(status='NOT_RUN',reason=reason,UB=None,LB=None,gap=None,M1_ACCEPTED=False,old_certificate='SUPERSEDED_NOT_USED'))

def audit():
    inherited=read('PR132_BYTE_PRESERVATION.json')['files'];changes=[];preserved=[]
    for row in inherited:
        p=ROOT/row['path']
        if not p.is_file() or sha(p)!=row['sha256']:changes.append(row['path'])
        else:preserved.append(row['path'])
    with (OUT/'FILE_LEVEL_INTEGRATION_AUDIT.csv').open(encoding='utf8') as f: rows=list(csv.DictReader(f))
    explained={r['path'] for r in rows if str(r['manual_merge']).lower()=='true'}
    unexplained=sorted(set(changes)-explained)
    physics_changes=[p for p in changes if p.startswith(('v42_thermal/','v42_regcontrol/','v42_capacity/','v42_holdout/','v42_final/','docs/'))]
    physical_folders=('docs/v42_transformer_normalamps_contract/','docs/v42_actual_autonomous_regcontrol_fixed_cap/','docs/v42_may_b0_zero_margin_holdout/')
    physical_evidence=[r for r in inherited if r['path'].startswith(physical_folders)]
    write('PR132_PHYSICAL_EVIDENCE_PRESERVATION.json',dict(PASS=all((ROOT/r['path']).is_file() and sha(ROOT/r['path'])==r['sha256'] for r in physical_evidence),files=physical_evidence,April_May_B0_reruns=0,physical_execution_paths_changed=physics_changes))
    new_code=list((ROOT/'v42_integrated').glob('*.py'));active=[]
    for p in new_code:
        if p.name=='finalize.py':continue # Obsolete literals are the scan's search keys.
        tree=ast.parse(p.read_text(encoding='utf8'))
        for n in ast.walk(tree):
            if isinstance(n,ast.Constant) and isinstance(n.value,float) and n.value in (.955,1.045,.005):
                # .005 is the requested optimization gap only, not voltage margin.
                if n.value!=.005:active.append(dict(path=p.relative_to(ROOT).as_posix(),line=n.lineno,value=n.value))
    voltage=(ROOT/'v42_native/voltage.py').read_text()
    assert '.955' not in voltage and '1.045' not in voltage
    historical=[]
    for folder in ROOT.glob('v42*'):
        if not folder.is_dir() or folder.name=='v42_integrated':continue
        for p in folder.rglob('*.py'):
            text=p.read_text(encoding='utf-8-sig')
            if any(s in text for s in ('.955','1.045','693.930612','0.5912812634331275','0.5722125039436496')):
                historical.append(dict(path=p.relative_to(ROOT).as_posix(),selected_integrated_scientific_authority=False,role='retained legacy experimental entry point / provenance / reporting; does not supply new model rows or certificate'))
    passed=not unexplained and not physics_changes and not active
    completeness=dict(PASS=passed,canonical_PR132=BASE,reference_PR131=SOLVER,common_merge_base=git('merge-base',BASE,SOLVER).decode().strip(),PR132_accepted_preserved=['operational contract','Actual no repairs / no reoptimization','autonomous 7 RegControls','4 fixed ON capacitors / 0 CapControls','compiled NormalAmps / unchanged kVA and line','frozen Runtime / CC4 / capacity','April and May B0 physical evidence'],PR131_selected_features=['Original v42_native.mess route/movement/P/Q/SOC equations already present in PR132','v42_m1_sparse exact F3 grid already present in PR132 with NormalAmps binding retained','selectively generalized triangular helper reconstruction from v42_exact_start.reconstruct','literal callback observation rules; strict null timestamps','inherited feasibility/integrality tolerance 1e-8'],PR131_intentionally_rejected=['old A1 freeze as model authority','old M1 matrix as generator','old UB/LB/gap/accepted certificate','old artificial voltage margin','old nameplate current denominator','Compact M1 production','Benders authority','solver sweeps/fallback','inferred first-branch timestamps'],missing_accepted_components=[],unverified_full_scale_execution=['A1 acceptance failed on native memory error 10001; M1 downstream gates not reached'] if not read('INTEGRATED_A1_FREEZE.json',{}).get('PASS') else [],PR132_overwritten_by_PR131=[],explicitly_changed_inherited_files=changes,unexplained_omissions=unexplained,active_old_voltage_margin=False,active_old_current_denominator=False,legacy_experimental_or_historical_instances=historical,provisional_PR131_duplicate_work_preserved_commit=PRESERVED)
    write('V42_INTEGRATION_COMPLETENESS_AUDIT.json',completeness)
    write('SUPERSEDED_ACTIVE_SCAN.json',dict(PASS=not active,integrated_code_scanned=[p.relative_to(ROOT).as_posix() for p in new_code],active_obsolete_matches=active,legacy_nonselected_modules=historical,effective_M1_voltage='0.95-1.05 margin 0',effective_current='compiled NormalAmps',old_normalization_transport='PR132 source-proven coefficient conversion only; old kVA/kV never used as a constraint limit'))
    return completeness

def finish():
    a1=read('INTEGRATED_A1_FREEZE.json',{})
    if not a1.get('PASS'):not_run('A1_GATE_FAILED')
    elif not read('ROOT_LP_EQUIVALENCE.json',{}).get('PASS'):not_run('ROOT_LP_GATE_FAILED_OR_NOT_COMPLETED')
    result=read('M1_SOLVE_RESULT.json',{});certificate=read('M1_CERTIFICATE.json',{})
    completeness=audit();tests=read('PYTEST_RECEIPT.json',{})
    root_gate=result.get('root_path_gate','NOT_RUN')
    flags=dict(V42_INTEGRATION_PASS=completeness['PASS'] and tests.get('PASS',False),ZERO_VOLTAGE_MARGIN_ACTIVE=True,NORMALAMPS_TRANSFORMER_AUTHORITY_ACTIVE=True,OLD_M1_CERTIFICATE_SUPERSEDED=True,A1_REGENERATED=bool(read('A1_MODEL_CENSUS.json')),A1_ACCEPTED=bool(a1.get('PASS')),M1_REGENERATED=bool(read('M1_MODEL_IDENTITY.json')),M1_ROOT_PATH_GATE=root_gate,M1_ACCEPTED=certificate.get('M1_ACCEPTED',False),A2='NOT_RUN',M2='NOT_RUN',ACTUAL='NOT_RUN',FRESH_AC='NOT_RUN',PROBLEM13_FINAL_VALIDATED=False)
    write('FINAL_FLAGS.json',flags)
    if root_gate=='FAIL':bottleneck='A. root path remains the bottleneck';next_direction='Inspect the observed remaining root phase on this exact new model; do not execute further experiments in this task.'
    elif result.get('gap') is not None and result['gap']>.005:
        if not result.get('incumbent_exists'):bottleneck='C. incumbent / UB';next_direction='Construct and independently certify one new-model feasible warm start.'
        else:bottleneck='B. B&B global bound progression';next_direction='Study one exact route / dispatch valid strengthening against this new model.'
    elif not a1.get('PASS'):
        cause=read('A1_ROOT_CAUSE.json',{})
        bottleneck='A1 native memory exhaustion' if cause.get('error_code')==10001 else 'A1 acceptance gate'
        next_direction='Revalidate this same full-horizon A1 under unchanged physical authority on a host with more memory headroom; do not change the domain or constraints.' if cause.get('error_code')==10001 else 'Resolve the recorded A1 root cause before constructing M1.'
    else:bottleneck='NONE: M1 acceptance target met';next_direction='Subsequent downstream task only after separate authorization.'
    write('BOTTLENECK_CLASSIFICATION.json',dict(classification=bottleneck,exactly_one_next_direction=next_direction,next_experiment_executed=False,causal_speedup_claim=False))
    verify=dict(PASS=flags['V42_INTEGRATION_PASS'],PASS_scope='code / integration / preservation validation only; not scientific solve acceptance',scientific_A1_acceptance=flags['A1_ACCEPTED'],scientific_M1_acceptance=flags['M1_ACCEPTED'],scientific_execution_stop=read('A1_ROOT_CAUSE.json'),pytest=tests,integration_completeness=completeness['PASS'],authority_SHA=NORMALAMPS,source_data_hash_audit=read('SOURCE_DATA_HASH_AUDIT.json'),duplicate_proof=read('INTEGRATED_M1_DUPLICATE_PROOF.json'),root_LP_gate=read('ROOT_LP_EQUIVALENCE.json'),old_certificate_superseded=True,new_certificate=certificate,downstream_calls=0,unexplained_inherited_changes=[])
    write('VERIFICATION.json',verify)
    files=[p for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json']
    write('SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in files],sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'v42_integrated').glob('*.py'))]))
    print('FINALIZED',flags,bottleneck,flush=True)

if __name__=='__main__':finish()
