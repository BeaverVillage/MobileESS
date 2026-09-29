"""Read-only scientific checks followed by self-excluding delivery manifests; no fit."""
from common15 import *
import ast,csv,re
sys.path.insert(0,str(REPO));sys.path.insert(0,str(V13))
import train13,common13

def checked(rows):
    for row in rows:
        p=Path(row['path']) if 'path' in row else REPO/row['relative']
        assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
    return len(rows)

def runtime_checks():
    import runtime15
    from v42.semantic_adapter import SemanticFeatureAdapter
    runtime15.guard()
    receipt=read(ROOT/'RUNTIME_INPUT_RECEIPT.json')
    checked(receipt['state_and_R0']);checked([receipt['semantic_projection']])
    for key,row in receipt['memberships'].items():
        checked([row['file']]);f=pd.read_parquet(row['file']['path'],columns=['job_id'])
        assert len(f)==row['N'] and common13.ids(f)==row['membership'],key
    comparison=pd.read_csv(ROOT/'RUNTIME_MODEL_COMPARISON.csv').set_index('arm')
    count=0
    for arm in ['R0','R1','R2']:
        parts=[];summaries=[]
        for i in range(1,6):
            folder=V13/'.local'/f'fold{i}' if arm=='R0' else LOCAL/f'runtime_fold{i}'
            name='EXPANDING_S4' if arm=='R0' else arm
            p=pd.read_parquet(folder/(name+'.parquet'));s=read(folder/(name+'.json'))
            assert np.isfinite(p[['q50','q90','runtime_seconds']].to_numpy()).all()
            assert (p.q90>=p.q50).all() and (p.q50>=0).all()
            q=np.load(folder/(name+'_quantiles.npz'))['q']
            assert np.isfinite(q).all() and (np.diff(q,axis=1)>=-1e-9).all()
            if arm!='R0':
                meta=read(folder/arm/'model.json');assert len(meta['columns'])==({'R1':201,'R2':233}[arm])
                bundle=SemanticFeatureAdapter.load(folder/'adapter')
                assert meta['semantic_bundle_sha256']==bundle.bundle_sha256
                stored=read(folder/'adapter/adapter.json')['training_receipt']
                assert stored['TRAIN_ONLY'] and not stored['label_input']
                assert stored['membership_sha256']==receipt['memberships'][f'{i}_TRAIN']['membership']
                assert read(folder/'SEMANTIC_FOLD_PARITY.json')['PASS'];count+=1
            s.update(arm=arm,calibration='C0');summaries.append(s);parts.append(p)
        actual=train13.summarize(arm,summaries,parts)
        for key in ['Q90_coverage','Q90_pinball','min_fold_coverage','gt4h_coverage','gt12h_coverage','gt24h_coverage','reservation_actual_GPUh','proper_interval_NLL']:
            assert np.isclose(actual[key],comparison.loc[arm,key],rtol=1e-12,atol=1e-10),(arm,key)
        for gate in 'ABCDEFGHI':assert actual['gate_'+gate]==comparison.loc[arm,'gate_'+gate],(arm,gate)
    assert count==10
    return dict(PASS=True,role_memberships=15,new_hazard_models=count,recomputed_arms=3,finite_monotone=True,baseline_refits=0)

def cc4_checks():
    import cc415
    from v42.semantic_adapter import SemanticFeatureAdapter
    cc415.guard();d=cc415.load();l=d['ledger']
    checked(read(ROOT/'CC4_BASELINE_INPUT_RECEIPT.json')['sources'])
    checked(read(ROOT/'CC4_BASELINE_INPUT_RECEIPT.json')['outputs'])
    c0=read(ROOT/'CC4_C0_REPRODUCTION.json');assert c0['PASS'] and c0['refits']==0
    checked([c0['source_anchor'],c0['target_authority'],c0['later_target_confirmation']])
    assert read(ROOT/'CC4_TRAINING_CONDITION_PARITY.json')['PASS']
    assert len(d['days'])==382 and max(d['days'])<'2025-04-01'
    ids=np.flatnonzero(l.target_day.ge('2024-09-01')&l.preApril_maturity)
    original={r['day']:r for r in read(CC4_SOURCE/'docs/cc4_v27_target_feature_sharpness/A0_REFIT_RECEIPTS.json')}
    count=0
    for arm in ['C1','C2']:
        files=list((LOCAL/'cc4_runs'/arm).glob('*.npz'));assert len(files)==len(ids)
        for i in ids:
            z=np.load(LOCAL/'cc4_runs'/arm/(d['days'][i]+'.npz'));prior=original[d['days'][i]]
            np.testing.assert_array_equal(z['training_days'],prior['training_days'])
            np.testing.assert_allclose(z['weights'],prior['weights'],rtol=1e-14,atol=1e-15)
            assert int(z['latest_maturity_ns'])<int(z['issue_ns'])==d['issue'].iloc[i].value
            assert z['q'].shape==(24,2) and np.isfinite(z['q']).all()
            assert (z['q'][:,1]>=z['q'][:,0]).all() and (z['q']>=0).all()
            assert all(re.fullmatch('[a-f0-9]{64}',x) for x in z['model_sha256']);count+=1
    z=np.load(LOCAL/'CC4_SEMANTIC_STATES.npz');assert z['values'].shape==(382,201) and int(z['base_count'])==142
    assert np.isfinite(z['values']).all()
    a=SemanticFeatureAdapter.load(LOCAL/'cc4_adapter')
    ar=read(LOCAL/'cc4_adapter/adapter.json')['training_receipt']
    audit=read(ROOT/'CC4_SEMANTIC_CAUSALITY_AUDIT.json')
    assert ar['TRAIN_ONLY'] and not ar['target_input'] and ar['membership_sha256']==audit['train_membership']
    assert len(audit['checks'])==12 and all(r['future_identical'] for r in audit['checks'])
    replay=read(ROOT/'CC4_FUTURE_INTERFACE_PARITY.json')
    assert replay['PASS'] and len(replay['checks'])==12 and replay['model_refits']==0
    assert all(r['past_positive_control'] for r in audit['checks'] if r['past_window_rows'])
    assert np.load(LOCAL/'cc4_adapter/kmeans_centers.npy').shape==(8,32)
    # Recompute evaluation metrics without changing freezes or reading any new target days.
    table=pd.read_csv(ROOT/'CC4_MODEL_COMPARISON.csv')
    burst=read(ROOT/'CC4_SELECTION_FREEZE.json')['TRAIN_burst_threshold']
    for arm in ['C0','C1','C2']:
        q=d['q0'].copy() if arm=='C0' else np.full_like(d['q0'],np.nan)
        if arm!='C0':
            for i in ids:q[i]=np.load(LOCAL/'cc4_runs'/arm/(d['days'][i]+'.npz'))['q']
        calibrated,_=cc415.calibration(d,q)
        for role in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION','OOS_EXTENSION']:
            ix=cc415.role_ids(d,role)
            for variant,p in [('RAW',q),('CALIBRATED',calibrated)]:
                m=cc415.metric(d['y'][ix],p[ix],burst)
                row=table[table.arm.eq(arm)&table.role.eq(role)&table.variant.eq(variant)].iloc[0]
                for key in ['hourly_Q90_coverage','daily_Q90_coverage','Q90_pinball','requirement_ratio','burst_coverage','WAPE']:
                    assert np.isclose(m[key],row[key],rtol=1e-12,atol=1e-10),(arm,role,variant,key)
    return dict(PASS=True,daily_records=count,quantile_boosters=count*2,exact_original_training_membership_and_weights=True,
                target_days_decoded=382,April_target_days_decoded=0,May_target_days_decoded=0,
                late_maturing_March_days_excluded=int((~l.preApril_maturity).sum()),causal_perturbation_issues=12,future_interface_replay_issues=12)

def boundary_checks():
    files=read(ROOT/'V42_INTERFACE_BASE_SNAPSHOT.json')['files'];checked(files)
    def defs(p):
        t=ast.parse(Path(p).read_text(encoding='utf-8-sig'))
        return {n.name:ast.dump(n,include_attributes=False) for n in t.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    for row in files:
        p=Path(row['path']);old=defs(p);new=defs(REPO/'v42'/p.name)
        allowed={'policy.py':{'Arrival'},'contracts.py':{'Switches'},'runtime_provider_contract.py':{'SubmissionRuntimeRequest'}}[p.name]
        for name,body in old.items():
            if name not in allowed:assert new[name]==body,(p.name,name)
    from v42.contracts import Switches
    assert Switches().ENABLE_SUBMISSION_SEMANTICS is False
    return dict(PASS=True,external_source_files_unchanged=3,legacy_policy_functions_AST_identical=True,default_enabled=False)

def main():
    before=read(ROOT/'BASE_PRESERVATION_RECEIPT.json')
    count=checked(before['tracked_files']);oldlocal=checked(before['local_inputs'])
    for row in before['delivery_manifests']:
        p=Path(row['path'])
        for r in read(p)['files']:assert sha(p.parent/r['relative'])==r['sha256']
    rawcount=0
    with (V14/'RAW_SOURCE_INVENTORY.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            p=Path(r['directory'])/r['filename'];st=Path('\\\\?\\'+str(p)).lstat()
            assert (st.st_size,st.st_mtime_ns)==(int(r['size_bytes']),int(r['mtime_ns'])),str(p);rawcount+=1
    print('PRESERVATION_VERIFIED',count,oldlocal,rawcount,flush=True)
    runtime=runtime_checks();print('RUNTIME_VERIFIED',flush=True)
    cc4=cc4_checks();print('CC4_VERIFIED',flush=True)
    boundary=boundary_checks()
    names=['SEMANTIC_UNIT_TEST_RESULTS.json','SEMANTIC_ADAPTER_PARITY_AUDIT.json','RUNTIME_SEMANTIC_CAUSALITY_AUDIT.json',
           'CC4_SEMANTIC_CAUSALITY_AUDIT.json','V42_SEMANTIC_INTERFACE_AUDIT.json','NEW_JOB_CALLABILITY_TEST.json']
    for name in names:assert read(ROOT/name)['PASS'],name
    call=read(ROOT/'NEW_JOB_CALLABILITY_TEST.json');assert len(call['cases'])==10 and call['no_operational_provider_authorization']
    legacy=LOCAL/'legacy_runtime_tests.log';assert '10 passed' in legacy.read_text(encoding='utf-8-sig')
    verdict=read(ROOT/'FINAL_VERDICT.json')
    assert verdict['RUNTIME_SEMANTIC_MODEL_SELECTED']==(read(ROOT/'RUNTIME_SELECTION_FREEZE.json')['selected'] in ['R1','R2','R3'])
    assert verdict['SELECTED_CC4_ARM']==read(ROOT/'CC4_SELECTION_FREEZE.json')['selected']
    for flag in ['APRIL_USED_FOR_SELECTION','MAY_PAYLOAD_OPENED','V42_OPTIMIZER_CHANGED','MESS_PHYSICS_CHANGED','OPENDSS_EXECUTED_FOR_SELECTION','V42_RUNTIME_USES_SEMANTICS','V42_CC4_USES_SEMANTICS']:assert verdict[flag] is False,flag
    req=(ROOT/'USER_REQUEST.txt').read_text(encoding='utf-8-sig')
    block=req.split('48. REQUIRED FINAL FLAGS')[0].split('47. REQUIRED ARTIFACTS')[-1]
    required=re.findall(r'^([A-Z][A-Z0-9_]+\.(?:json|md|csv))\s*$',block,re.M)
    assert len(required)>=24,required
    for n in required:
        if n not in ['SOURCE_MANIFEST.json','LOCAL_EVIDENCE_MANIFEST.json','DELIVERY_MANIFEST.json','VERIFICATION.json']:assert (ROOT/n).is_file(),n
    assert len(re.findall(r'^## \d+\.',(ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8'),re.M))==50
    public=[p for p in ROOT.iterdir() if p.is_file()]+[p for p in (REPO/'v42').iterdir() if p.is_file()]
    for p in public:
        if p.suffix=='.py':compile(p.read_text(encoding='utf-8-sig'),str(p),'exec')
        assert p.suffix not in ['.npz','.npy','.parquet','.pkl','.bin']
    changed=set(git('diff','--name-only',BASE).splitlines())
    assert all(p.startswith(('docs/runtime_vnext15_reproducible_semantic/','v42/')) for p in changed),changed
    subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--check',BASE],cwd=REPO,check=True)
    print('BOUNDARIES_AND_ARTIFACTS_VERIFIED',flush=True)
    # Models and original identities stay local. Only aggregate audit/metric artifacts are delivered.
    localfiles=[rec(p) for p in sorted(LOCAL.rglob('*')) if p.is_file() and 'test_dependencies' not in p.parts and '__pycache__' not in p.parts]
    write('LOCAL_EVIDENCE_MANIFEST.json',dict(time=now(),files=localfiles,
        excluded='test_dependencies and __pycache__ are tooling, not scientific artifacts',
        test_tool_versions=dict(pytest='8.3.5',colorama='0.4.6',iniconfig='2.3.0',packaging='26.3',pluggy='1.6.0'),
        immutable_earlier_local_evidence_preserved=True,May_payload_decoded=False))
    source_names=['BASE_PRESERVATION_RECEIPT.json','RUNTIME_INPUT_RECEIPT.json','KESTREL_ORIGINAL_PROJECTION_RECEIPT.json',
        'V42_INTERFACE_BASE_SNAPSHOT.json','CC4_BASELINE_INPUT_RECEIPT.json','CC4_EXECUTION_ENVIRONMENT.json','RUNTIME_EXECUTION_ENVIRONMENT.json',
        'PREREGISTRATION.json','PREREGISTRATION_HASH.json','CC4_EXECUTION_FREEZE.json','CC4_PRETRAIN_DOCUMENTATION_CORRECTION.json','CC4_SEMANTIC_ENVIRONMENT_REPAIR.json']
    write('SOURCE_MANIFEST.json',dict(time=now(),base=BASE,receipts=[rec(ROOT/n) for n in source_names],
        private_exporter_used=False,source_inventory=rec(V14/'RAW_SOURCE_INVENTORY.csv'),
        local_evidence_manifest=rec(ROOT/'LOCAL_EVIDENCE_MANIFEST.json')))
    write('VERIFICATION.json',dict(time=now(),PASS=True,prior_tracked_files=count,prior_delivery_manifests=len(before['delivery_manifests']),
        prior_local_evidence_files=oldlocal,raw_size_mtime_fingerprints=rawcount,Runtime=runtime,CC4=cc4,boundaries=boundary,
        relevant_tests_passed=26,callability_cases=10,required_artifacts=len(required),final_review_questions=50,
        source_manifest=rec(ROOT/'SOURCE_MANIFEST.json'),local_evidence_files=len(localfiles),
        public_payload_review='Aggregate CSV/JSON and source only; model dictionaries and row-level IDs/payloads remain ignored in .local. Synthetic literals in tests are intentional.',
        scope='Logical event-time/feature projection, not archive ingestion or original mutable request-version certification',
        broader_optimizer_campaign='NOT_RUN_OUT_OF_SCOPE_UNCHANGED_PHYSICS',April_selection=False,May_payload=False,training_performed_by_verifier=False))
    public=[p for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='DELIVERY_MANIFEST.json']
    write('DELIVERY_MANIFEST.json',dict(time=now(),self_excluded=True,
        files=[dict(relative=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in public],
        repository_files=[dict(relative=p.relative_to(REPO).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted((REPO/'v42').iterdir()) if p.is_file()]))
    for n in required:assert (ROOT/n).is_file(),n
    print('VERIFICATION_PASS',len(public),len(localfiles),flush=True)

def check_delivery():
    manifest=read(ROOT/'DELIVERY_MANIFEST.json')
    for row in manifest['files']:
        p=ROOT/row['relative'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
    checked(manifest['repository_files'])
    local_count=checked(read(ROOT/'LOCAL_EVIDENCE_MANIFEST.json')['files'])
    if '--check-git' in sys.argv:
        entries=[(ROOT/r['relative'],r['sha256']) for r in manifest['files']]
        entries += [(REPO/r['relative'],r['sha256']) for r in manifest['repository_files']]
        entries.append((ROOT/'DELIVERY_MANIFEST.json',sha(ROOT/'DELIVERY_MANIFEST.json')))
        for p,expected in entries:
            committed=subprocess.check_output(['git','show','HEAD:'+p.relative_to(REPO).as_posix()],cwd=REPO)
            assert hashlib.sha256(committed).hexdigest()==expected,str(p)
    print('FROZEN_DELIVERY_HASH_CHECK_PASS',len(manifest['files']),len(manifest['repository_files']),local_count,flush=True)

if __name__=='__main__':
    check_delivery() if '--check-delivery' in sys.argv else main()
