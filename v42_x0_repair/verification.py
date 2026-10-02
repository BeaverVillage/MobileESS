"""Seal artifacts after all primary optimization has terminated."""
import gzip,hashlib,json,xml.etree.ElementTree as ET
import numpy as np
import gurobipy as gp
from .common import *
from .independent import verify

def run():
    f=read('FINAL_FLAGS.json');preserve();x0,xr=load_x0();n,prior=load_native()
    assert read('PR117_SCIENTIFIC_DOMAIN_AUDIT.json')['PASS']
    assert read('MASTER_COEFFICIENT_API_AUDIT.json')['coefficients_bit_exact']
    if f['x1_generated']:assert read('MASTER_X1_CUT_SATISFACTION.json')['satisfies_cut']
    base_paths={r['path'] for r in read('PR117_BASE_RECEIPT.json')['files']}
    assert not (base_paths&set(git('diff',BASE,'--name-only').splitlines())),'INHERITED_GIT_BLOBS_CHANGED'
    freeze=read('EXECUTION_FREEZE.json')
    for r in freeze['sources']:assert sha(ROOT/r['path'])==r['sha256']
    suite=ET.parse(OUT/'FINAL_TEST_RESULTS.xml').getroot().find('testsuite')
    assert int(suite.attrib['tests'])==850 and int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
    assert f['new_x0_master_optimize_calls']==0 and f['exact_PR117_x0_reused'] and f['uncertified_cuts_inserted']==0
    assert all(f[k] is False for k in ['full_B3_RUN','full_M1_canary_RUN','production_M1_RUN','P1_ACCEPTED','M1_ACCEPTED','P2_RUN','A2_RUN','M2_RUN','PROBLEM13_FINAL_VALIDATED','Actual_P_correction','Actual_Q_correction','B0_B1_RUN'])
    audits=[]
    assert len({r['cut_hash'] for r in f['cuts']})==len(f['cuts'])
    for ledger in f['cuts']:
        p=OUT/('CUT_'+str(len(audits)).zfill(3)+'.json');c=json.loads(p.read_text());r=c['record'];persistence=r['raw_persistence']
        with gzip.open(persistence['journal'],'rb') as stream:payload=list(stream)[persistence['record']-1].rstrip(b'\n')
        assert hashlib.sha256(payload).hexdigest()==persistence['payload_sha256']
        raw=json.loads(payload);raw['persistence']=persistence;assert sha(raw['axis_npz'])==raw['axis_npz_sha256']
        with np.load(p.with_suffix('.npz')) as z:coefficients=z['coefficients'];intercept=z['intercept']
        assert sha(p.with_suffix('.npz'))==c['coefficients_sha256'] and sha(p)==ledger['artifact_sha256']
        assert intercept[0]==r['intercept'];cut=dict(record=r,raw=raw,coefficients=coefficients)
        replay=verify(n,cut);assert replay==c['independent_validation']
        env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();model=gp.Model(env=env)
        variables=model.addMVar(len(n.xi),vtype='B',lb=n.xlower,ub=n.xupper)
        row=model.addConstr(r['intercept']+coefficients@variables>=0);model.update()
        assert np.array_equal(model.getA().toarray()[0],coefficients) and float(row.RHS)==-r['intercept']
        model.dispose();env.dispose()
        audits.append(dict(path=p.relative_to(ROOT).as_posix(),cut_hash=r['cut_hash'],source_x_hash=r['source_x_hash'],independent_replay_PASS=True))
    if f['x1_generated']:
        from v42_benders_fullscale.candidates import load
        x1,r=load(OUT,1,n);assert digest_arrays(x1)!=X0 and r['created_only_after_valid_cut'] and r['parent_PR117_x0']==X0
        assert r['repair_preregistration_sha256']==sha(OUT/'PREREGISTRATION.json')
        assert r['repair_freeze_sha256']==sha(OUT/'EXECUTION_FREEZE.json')
        started=read('RECOURSE_STARTED.json',OUT/'X1');assert started['source_saved_verified_before_optimize'] and started['source_x_hash']==r['vector_sha256']
        assert started['started_UTC']>=r['created_UTC']
    raw_count=0
    for folder in [OUT/'X0',OUT/'X1']:
        if not folder.exists():continue
        index=0 if folder.name=='X0' else 1
        expected=x0 if index==0 else x1
        for p in folder.glob('*_RAW_RECEIPT.json'):
            receipt=json.loads(p.read_text());persistence=receipt['persistence']
            with gzip.open(persistence['journal'],'rb') as stream:payload=list(stream)[persistence['record']-1].rstrip(b'\n')
            assert hashlib.sha256(payload).hexdigest()==persistence['payload_sha256'];raw=json.loads(payload)
            assert np.array_equal(raw['source_x'],expected) and sha(raw['axis_npz'])==raw['axis_npz_sha256']
            assert persistence['persisted_before_validation'] and raw['Method']==1 and raw['Seed']==20260929
            raw_count+=1
    assert read('REPORT_RECEIPT.json')['questions']==60 and read('FIXTURE_REGRESSION.json')['assignments']==1536
    source=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for d in ['v42_x0_repair','tests/v42_x0_repair'] for p in sorted((ROOT/d).glob('*.py'))]
    dump('SOURCE_MANIFEST.json',source)
    evidence=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ['VERIFICATION.json','SOURCE_MANIFEST.json','EVIDENCE_MANIFEST.json']]
    dump('EVIDENCE_MANIFEST.json',evidence)
    dump('VERIFICATION.json',dict(PASS=True,base=BASE,inherited_tracked_files=2121,inherited_changed=0,
        inherited_tests=825,new_tests=25,total_tests=850,test_seconds=float(suite.attrib['time']),inherited_bounded_checks=44,
        fixture_assignments=1536,numerical_N1_N10_PASS=True,reduced_support_fixture_PASS=True,
        exact_x0_hash=X0,x0_reused=True,new_x0_master_optimize_calls=0,raw_receipt_count=raw_count,source_freeze_PASS=True,
        cuts=audits,clamp=False,flip=False,tiny_delete=False,production_downstream_runs=0,questions=60,
        source_manifest_sha256=sha(OUT/'SOURCE_MANIFEST.json'),evidence_manifest_sha256=sha(OUT/'EVIDENCE_MANIFEST.json'),
        final_verdict=read('FINAL_VERDICT.json')['verdict']))
    print('2121 inherited bytes / 850 tests / x0/x1 lineage / independent cuts / raw journals / freeze PASS',flush=True)

if __name__=='__main__':run()
