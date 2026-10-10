"""Qualify owned scheduling only, with retained real model/Native denial."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import hashlib
import importlib
import json
import os
import sys
import xml.etree.ElementTree as ET

REPO=Path(r'D:\MobileESS_v42_autonomous')
ROOT=Path(r'D:\v42_may_restart_20261010_02')
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(REPO))


def read(path):return json.loads(Path(path).read_bytes().decode('utf-8-sig'))


def record(path):
    raw=Path(path).read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def hashes(paths):return {str(path):record(path)['sha256'] for path in paths}


def live_observation(label):
    import psutil
    cp=read(ROOT/'SUPERVISOR_STATE.json')
    result={}
    for day in ('2025-05-01','2025-05-02','2025-05-03'):
        worker=cp['workers'].get('B2/'+day)
        if not worker:continue
        request=read(worker['request'])
        ledger_path=Path(worker['request']).parent/'NATIVE_RUNTIME_LEDGER.json'
        raw=ledger_path.read_bytes()
        ledger=json.loads(raw)
        path=OUT/(day+'_'+label+'_NATIVE_RAW.json')
        path.write_bytes(raw)
        process=psutil.Process(worker['PID'])
        result[day]=dict(worker=worker,request=record(worker['request']),ledger=record(path),
            actual_process=dict(PID=process.pid,created=process.create_time(),command=process.cmdline(),cwd=process.cwd()),
            scientific_output=request['output'],calls=ledger.get('calls',[]),
            measured_Native_Runtime=ledger.get('measured_Native_Runtime'),
            inflight=ledger.get('inflight'))
    return result


def main():
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
    os.chdir(REPO)
    preload=[]
    for name in ('v42_autonomous_b2.pricing_cache','v42_autonomous_b2.rmp_presolve',
                 'v42_autonomous_b2.worker','v42_autonomous_b2.f1_basis',
                 'v42_autonomous_b2.f1_state','v42_autonomous_b2.dw_native',
                 'v42_autonomous_b2.f1_price_seed'):
        importlib.import_module(name);preload.append(name)
    import pytest
    import gurobipy as gp
    from v42_autonomous import supervisor,recovery
    manifest=read(ROOT/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json')
    original={str(REPO/name):digest for name,digest in manifest['builder_original_sources'].items()}
    execution={str(REPO/name):digest for name,digest in manifest['execution_sources'].items()}
    frozen={}
    for version in ('35','36'):
        freeze=read(ROOT/('autonomous/V'+version+'_SPARSE_IMMUTABLE_FREEZE.json'))
        frozen[version]={item['path']:item['sha256'] for item in freeze['source_files']}
    selected=['tests/test_v42_autonomous_first_sweep_fairness.py',
              'tests/test_v42_autonomous_supervisor.py','tests/test_v42_autonomous_recovery.py']
    assert record(REPO/'v42_autonomous/supervisor.py')['sha256']=='cce72776da0e8f31d834f63fc9530e9894eb77a5164c694b7a9a937a2de1c77a'
    assert record(REPO/'tests/test_v42_autonomous_first_sweep_fairness.py')['sha256']=='fca4b18fa0dfbbc2df5872e9e349eff058e17a563e0cdf3e41719d4d3fb249f4'
    owned=[REPO/name for name in ['v42_autonomous/supervisor.py','v42_autonomous/recovery.py',*selected]]
    before=dict(original_repo=hashes(original),execution_repo=hashes(execution),frozen={v:hashes(paths) for v,paths in frozen.items()},
        owned=hashes(owned),producer=record(__file__))
    live_before=live_observation('BEFORE')
    queue_before=record(ROOT/'RECOVERY_QUEUE.json')
    queue_doc=read(ROOT/'RECOVERY_QUEUE.json')
    ready_before={row['queue_id']:row for row in queue_doc['entries']
        if row['verification_status']=='READY_VERIFIED_REPAIR'}
    attempted=[]
    def deny_model(*args,**kwargs):
        attempted.append('gurobipy.Model');raise AssertionError('FAIRNESS_REAL_MODEL_DENIED')
    def deny_init(*args,**kwargs):
        attempted.append('retained_Model.__init__');raise AssertionError('FAIRNESS_RETAINED_MODEL_DENIED')
    def deny_native(*args,**kwargs):
        attempted.append('retained_Model.optimize');raise AssertionError('FAIRNESS_REAL_NATIVE_DENIED')
    model=gp.Model
    xml=OUT/'FIRST_SWEEP_FAIRNESS_INDEPENDENT_NATIVE_DENIED_TESTS.xml'
    output=OUT/'FIRST_SWEEP_FAIRNESS_INDEPENDENT_NATIVE_DENIED_OUTPUT.log'
    with output.open('w',encoding='utf8',newline='') as stream:
        with patch.object(model,'__init__',deny_init),patch.object(model,'optimize',deny_native),patch.object(gp,'Model',deny_model):
            with redirect_stdout(stream),redirect_stderr(stream):
                exit_code=pytest.main([*selected,'-q','-p','no:cacheprovider',
                    '--junitxml='+str(xml),'--basetemp='+str(REPO/'tmp/first_sweep_fairness_independent_01')])
    after=dict(original_repo=hashes(original),execution_repo=hashes(execution),frozen={v:hashes(paths) for v,paths in frozen.items()},
        owned=hashes(owned),producer=record(__file__))
    live_after=live_observation('AFTER')
    queue_after=record(ROOT/'RECOVERY_QUEUE.json')
    ready_after={row['queue_id']:row for row in read(ROOT/'RECOVERY_QUEUE.json')['entries']
        if row['verification_status']=='READY_VERIFIED_REPAIR'}
    suites=ET.parse(xml).getroot()
    stats={name:sum(int(suite.get(name,'0')) for suite in suites.iter('testsuite'))
        for name in ('tests','failures','errors','skipped')}
    focused=sum(case.get('classname','').endswith('test_v42_autonomous_first_sweep_fairness')
        for case in suites.iter('testcase'))
    prefix_preserved=(set(live_before)==set(live_after)=={'2025-05-01','2025-05-02','2025-05-03'}
        and all(live_before[d]['worker']==live_after[d]['worker']
            and live_before[d]['request']==live_after[d]['request']
            and live_before[d]['actual_process']==live_after[d]['actual_process']
            and live_after[d]['calls'][:len(live_before[d]['calls'])]==live_before[d]['calls']
            for d in live_before))
    checks=dict(selected_tests_PASS=exit_code==0 and stats['tests']>0
        and stats['failures']==stats['errors']==stats['skipped']==0,
        focused_14_behavior_tests=focused==14,actual_model_native_attempts_zero=attempted==[],
        owned_and_original_source_bytes_start_end=before==after,
        original_repo_1007_matches_manifest=before['original_repo']==original and len(original)==1007,
        execution_repo_99_matches_Source36_manifest=before['execution_repo']==execution and len(execution)==99,
        immutable_35_36_each_1111_matches_declared=all(before['frozen'][v]==expected and len(expected)==1111
            for v,expected in frozen.items()),
        owned_supervisor_outside_original_and_scientific_maps=all(
            name not in {**manifest['builder_original_sources'],**manifest['execution_sources']}
            for name in ('v42_autonomous/supervisor.py','v42_autonomous/recovery.py')),
        actual_healthy_three_worker_requests_and_Native_prefix_preserved=prefix_preserved,
        actual_nine_READY_queue_bytes_unchanged=queue_before==queue_after and ready_before==ready_after and len(ready_before)==9)
    receipt=dict(PASS=all(checks.values()),schema='V42_FIRST_SWEEP_FAIRNESS_INDEPENDENT_NATIVE_DENIED_REVIEW',
        UTC=datetime.now(timezone.utc).isoformat(),checks=checks,actual_exit_code=exit_code,
        selected=selected,statistics=stats,focused_test_count=focused,
        protected_science_preloads_before_retained_descriptor_denial=preload,
        attempted_model_native_entries=attempted,Native_optimize_calls=0,real_model_constructions=0,real_Native_model_constructions=0,modelattempts=[],nativeattempts=[],
        before=before,after=after,actual_live_before=live_before,actual_live_after=live_after,
        actual_queue_before=queue_before,actual_queue_after=queue_after,
        actual_READY_queue_ids=list(ready_before),source_start_end_identical=before==after,test_start_end_identical=all(before['owned'][str(REPO/name)]==after['owned'][str(REPO/name)] for name in selected),test_XML=record(xml),
        pytest_stdout_stderr_python_redirect_exact=record(output),production_mutations=0,Git_mutations=0,
        policy='B2 at most2 entered retry starts before a pending initial visit; B3 at most1; durable checkpoint streak; no delay after first sweeps.',
        tradeoff='Priority stays within retries; next initial date takes a free slot after2 B2 repairs or1 B3 repair, so priority repairs need not occupy every free slot.',
        limitations=['Controller tests use fake owned workers and simulated admission/terminal receipts; no actual Native performance or scientific date PASS claim.',
            'Current producer ledger prefix is observed read-only while original healthy workers continue; no worker lifecycle or queue mutation.',
            'No supervisor reload or production integration is performed by this runner.'])
    path=OUT/'FIRST_SWEEP_FAIRNESS_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json'
    assert not path.exists()
    path.write_bytes((json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps(dict(PASS=receipt['PASS'],checks=checks,statistics=stats,
        focused_tests=focused,receipt=record(path),output=record(output),model_native_attempts=attempted)))
    return 0 if receipt['PASS'] else 1


if __name__=='__main__':raise SystemExit(main())
