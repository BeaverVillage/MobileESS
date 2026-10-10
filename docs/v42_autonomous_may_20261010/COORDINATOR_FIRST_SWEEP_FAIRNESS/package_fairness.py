"""Additive exact-copy evidence package; never modify production or old seals."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json

REPO=Path(r'D:\MobileESS_v42_autonomous')
BASE=REPO/'docs/v42_autonomous_may_20261010'
DEST=BASE/'COORDINATOR_FIRST_SWEEP_FAIRNESS'
ROOT=Path(r'D:\v42_may_restart_20261010_02')
OUT=Path(__file__).resolve().parent


def read(path):return json.loads(Path(path).read_bytes().decode('utf-8-sig'))


def record(path):
    raw=Path(path).read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def hashes(paths):return {str(path):record(path)['sha256'] for path in paths}


def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8'))


README='''# Coordinator first-sweep fairness: qualification and actual owned reload

The previous coordinator preferred a verified repair at every free slot.
Finite READY entries were consumed once and did not themselves create HOLD,
but continuously supplied new verified repairs could indefinitely postpone
unvisited dates. The new scheduling rule bounds that dispatch streak while
retaining the existing queue priority order and worker counts.

While an arm has an unvisited initial date, at most two consecutive entered B2
repair starts or one entered B3 repair start precede an initial-date visit in
the next free slot. The streak is durable in the checkpoint. B2 stays at three
workers and B3 at one. Only entered repair starts, including new adoption, count;
re-adopting the same persisted worker does not count twice. Successful initial
starts and local initial admission failures with preserved terminal receipts
reset the streak. Lease contention, unentered retry failures and shared source
blocks do not fabricate a counted start or reset. Malformed counters fail
strictly. Once the first sweep is complete, this restriction is inactive.

The first eligible selection still favors a priority repair. With three free
B2 slots, two priority repairs and one unvisited date start. B3 alternates
repair and initial visits. This means priority repairs need not occupy every
available slot while unvisited dates remain. The existing transition starts
B3 after B2's 31 terminal first attempts even when B2 FAIL or READY repairs
remain. Shared source/environment blocking and all original scientific and
Native-budget guards remain in place. Scheduling liveness applies when slots
become free and shared admission is healthy; no wall-clock or solver-speed
guarantee is made.

## Exact qualification evidence

`OWNER_FINAL_02` and `INDEPENDENT_156` each contain a 156-test strong-denial PASS:
the existing 142 recovery/supervisor regressions and 14 new behavior cases.
Tests exercise endless verified repairs that keep failing, checkpoint reload
and worker re-adoption on every cycle, all 31 first dates, mixed daily terminal
failures, unchanged repair priority, healthy-worker/Native-prefix preservation,
refused starts, local initial admission failure, shared source blocking,
completed-sweep dispatch and strict invalid-counter rejection.

Seven scientific modules were preloaded before denying the actual retained
Gurobi Model.__init__, Model.optimize and gurobipy.Model. Attempted actual model
and Native entries were empty. Test workers and their terminal receipts are
isolated simulations, not new scientific results. The original repository
science1007 and immutable D35/D36 source1111 were byte exact; owner/independent
read-only observations preserved the real three worker identities/requests,
completed Native-ledger prefixes and all nine READY queue entries.

`OWNER_INITIAL_COUNT_FAILURE_01` retains the initial runner's actual exit1 and
PASS=false receipt. All 156 tests passed, but the runner expected 15 focused
cases instead of the actual 14. Only that count check failed. Final runner02
corrected only the expectation and re-ran unchanged source/tests. Exact original
receipt, XML, captured pytest stdout/stderr and raw Native snapshots are kept;
the initial harness failure is not hidden or labeled as a scientific failure.
The receipt's `actual_exit_code` records pytest exit0; the wrapper process
returned exit1 because the separate count check failed.

`CONTROL_CURRENT` contains the qualified supervisor, unchanged recovery module,
new focused tests and both existing controller test modules. The archived
`CONTROL_BEFORE_POLICY` supervisor SHA4ad79721 is copied from the previously
sealed startup evidence. It is a historical control baseline, not a newly
invented initial read-only audit. The earlier scheduling review was communicated
in this task; no separate sealed proposal artifact existed to copy.

## Actual reload evidence

`ROOT_ACTUAL_RELOAD` contains the exact helper, ownership/heartbeat/OS-mutex
baseline, launch receipt, original three Native-prefix snapshots, prior raw
SUPERVISOR_ERROR bytes, actual verification, stdout/stderr and historical lease
receipts. The independently reviewed helper was unexecuted at its static review;
the later Root actual verification records the real operation.

Root terminated only exact owned old supervisor107788 and launched sole owned
replacement82852. The actual verification binds the new supervisor creation,
command and cwd, all three unchanged Source35 workers98148/103128/80288, current
requests, original completed Native prefixes and unchanged raw prior error.
Scientific-worker terminate calls, new Model/Native calls and replacement P2
calls were zero. Original 5400-second budgets and scientific source identities
were retained. No date PASS, final 3% Global Gap or fresh Actual result is claimed.

`ACTUAL_RELOAD_INDEPENDENT` contains the separate read-only post-reload audit
and its exact raw observations. All three scientific slots were occupied at
that audit, so no live fairness dispatch choice or Source36 Native execution
was observed yet. Process-memory bytecode was not inspected; source hashes,
owned process/launch/heartbeat observations and separate controller tests are
the evidence. The historical fairness repair lease705bf36e...
was RELEASED at00:54:59.422107 UTC; this is a historical receipt, not a claim
about any later global repair lease. These observations describe their sealed
timestamps and do not freeze subsequent healthy scientific progress.
The latest Root hourly-automation verification is copied exactly. Its ACTIVE
configuration and saved policy are distinguished from an actual scheduled run.

`PACKAGE_HARNESS_FAILURE_01` preserves the first packaging assertion failure,
which confused that owner01 pytest exit0 field with the wrapper's exit1.
It failed before creating this new docs directory or performing any production
action. The corrected assertion preserves both distinct exit-code meanings.

## Package seal

`COPY_PROVENANCE.json` maps every exact source copy to its origin SHA256/bytes.
`SHA_INVENTORY.json` seals every payload except itself. Local `.gitattributes`
disables text conversion only in this new evidence directory. Existing Source35,
Source36, monitor, full-LP diagnosis and earlier controller inventories are
unchanged. This packaging step imported no scientific modules, constructed no
model, ran no Native, changed no production processes or queues and made no
Git mutation. Actual Root reload is recorded separately and accurately.
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--actual-dir',required=True)
    parser.add_argument('--actual-receipt-name',required=True)
    parser.add_argument('--actual-receipt-sha',required=True)
    args=parser.parse_args()
    actual=Path(args.actual_dir).resolve()
    actual_receipt=actual/args.actual_receipt_name
    assert record(actual_receipt)['sha256']==args.actual_receipt_sha
    assert read(actual_receipt)['PASS'] is True
    assert not DEST.exists(),'NEW_PACKAGE_ALREADY_EXISTS'
    owner1=Path(r'D:\v42_first_sweep_fairness_owner_review_20261010_01')
    owner2=Path(r'D:\v42_first_sweep_fairness_owner_review_20261010_02')
    indep=Path(r'D:\v42_first_sweep_fairness_independent_review_20261010_01')
    critical={
        owner1/'FIRST_SWEEP_FAIRNESS_OWNER_NATIVE_DENIED_REVIEW_RECEIPT.json':
            '72bef4f31b83636097e23f9aa20419ebdb22d50e5198480c5f6789c31a352cb7',
        owner2/'FIRST_SWEEP_FAIRNESS_OWNER_NATIVE_DENIED_REVIEW_RECEIPT.json':
            '09b7b6d7c4ecf43dab7a5ddd1206d54048749f85e886830f529944a813728c59',
        indep/'FIRST_SWEEP_FAIRNESS_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json':
            '773b1d7baa2da806bc26b1b6ac5928114ef0891e4f45ddcbfc5cc2af2af59cee',
        indep/'FIRST_SWEEP_FAIRNESS_STATIC_AND_RELOAD_HELPER_REVIEW.json':
            '711a6709bf45ddebff8c965fdc22ed126de5473f670b7fc1a02358bb4c8b25d2',
        ROOT/'autonomous/CONTROLLER_RETRY_FAIRNESS_RELOAD_VERIFICATION.json':
            'b9a97ecf2fc87bb7912f91f809db9fe5cba7afb015690c94ad07ec28ba581041',
        ROOT/'autonomous/reload_owned_supervisor_retry_fairness.py':
            'd63598af0bb842b681db5b3e5a0354020dcf48917699122748b14b8cc2180f87',
        ROOT/'autonomous/CODEX_HOURLY_AUTOMATION_VERIFICATION_20261010T005601.json':
            '7dc988e808569f72eeb3c9fc36d31e40b09bd348a6d7c85fb08a0f244dbb63d7',
        REPO/'v42_autonomous/supervisor.py':
            'cce72776da0e8f31d834f63fc9530e9894eb77a5164c694b7a9a937a2de1c77a',
        REPO/'tests/test_v42_autonomous_first_sweep_fairness.py':
            'fca4b18fa0dfbbc2df5872e9e349eff058e17a563e0cdf3e41719d4d3fb249f4',
        BASE/'CONTROLLER_DUPLICATE_STARTUP/source4_raw/v42_autonomous/supervisor.py':
            '4ad79721ca02272e6471fe56e1637b60b9f38a48748da5cd39d6a2adf5f45f92',
    }
    for path,digest in critical.items():assert record(path)['sha256']==digest,('SEALED_INPUT_DRIFT',str(path))
    first=read(owner1/'FIRST_SWEEP_FAIRNESS_OWNER_NATIVE_DENIED_REVIEW_RECEIPT.json')
    # The preserved receipt records pytest exit0; its count-failed wrapper exited1.
    assert first['PASS'] is False and first['actual_exit_code']==0 and first['focused_test_count']==14
    assert [name for name,passed in first['checks'].items() if not passed]==['focused_15_behavior_tests']
    for path in (owner2/'FIRST_SWEEP_FAIRNESS_OWNER_NATIVE_DENIED_REVIEW_RECEIPT.json',
                 indep/'FIRST_SWEEP_FAIRNESS_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json'):
        assert read(path)['PASS'] is True
    final=read(owner2/'FIRST_SWEEP_FAIRNESS_OWNER_NATIVE_DENIED_REVIEW_RECEIPT.json')
    frozen={}
    for version in ('35','36'):
        declared=read(ROOT/('autonomous/V'+version+'_SPARSE_IMMUTABLE_FREEZE.json'))
        frozen[version]={row['path']:row['sha256'] for row in declared['source_files']}
    expected_original=final['before']['original_repo']
    sources_before=dict(original=hashes(expected_original),
        frozen={v:hashes(paths) for v,paths in frozen.items()})
    assert sources_before['original']==expected_original
    assert all(sources_before['frozen'][v]==expected for v,expected in frozen.items())
    previous=[BASE/path for path in [
        'SOURCE35/SHA_INVENTORY.json','SOURCE35/PRICE_REVIEW/SHA_INVENTORY.json',
        'SOURCE35/DIAGNOSIS/SHA_INVENTORY.json','SOURCE35/DEPLOYMENT/SHA_INVENTORY.json',
        'SOURCE36/SHA_INVENTORY.json',
        'SOURCE36/RMP_PRIMAL_REVIEW/SHA_INVENTORY.json',
        'SOURCE36/ACTUAL_SOURCE35_RMP_DIAGNOSIS/SHA_INVENTORY.json',
        'MONITOR_ASSEMBLED_LB_EXCLUSIVE_HOST/SHA_INVENTORY.json',
        'SOURCE35_FULL_LP_DIAGNOSIS/SHA_INVENTORY.json',
        'CONTROLLER_DUPLICATE_STARTUP/SHA_INVENTORY_FINAL.json',
        'CONTROLLER_HEARTBEAT_IO/SHA_INVENTORY.json']]
    previous_before={str(path):record(path) for path in previous}
    copies=[]
    for directory,prefix in [(owner1,'OWNER_INITIAL_COUNT_FAILURE_01'),(owner2,'OWNER_FINAL_02'),
                             (indep,'INDEPENDENT_156'),(actual,'ACTUAL_RELOAD_INDEPENDENT')]:
        for path in sorted(directory.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
                copies.append((path,Path(prefix)/path.relative_to(directory)))
    for name in ['v42_autonomous/supervisor.py','v42_autonomous/recovery.py',
                 'tests/test_v42_autonomous_first_sweep_fairness.py',
                 'tests/test_v42_autonomous_supervisor.py','tests/test_v42_autonomous_recovery.py']:
        copies.append((REPO/name,Path('CONTROL_CURRENT')/name))
    copies.append((BASE/'CONTROLLER_DUPLICATE_STARTUP/source4_raw/v42_autonomous/supervisor.py',
        Path('CONTROL_BEFORE_POLICY/v42_autonomous/supervisor.py')))
    root_files=['reload_owned_supervisor_retry_fairness.py',
        'CODEX_HOURLY_AUTOMATION_VERIFICATION_20261010T005601.json',
        'CONTROLLER_RETRY_FAIRNESS_RELOAD_BEFORE.json','CONTROLLER_RETRY_FAIRNESS_RELOAD_LAUNCH.json',
        'CONTROLLER_RETRY_FAIRNESS_RELOAD_VERIFICATION.json','CONTROLLER_RETRY_FAIRNESS_PRIOR_SUPERVISOR_ERROR.json',
        'controller_retry_fairness_stderr.log','controller_retry_fairness_stdout.log',
        *['CONTROLLER_FAIRNESS_RELOAD_B2_2025-05-'+day+'_NATIVE_BEFORE.json' for day in ('01','02','03')]]
    for name in root_files:copies.append((ROOT/'autonomous'/name,Path('ROOT_ACTUAL_RELOAD')/name))
    token='705bf36e5f9a489bb9b0121ce2844fca'
    assert read(ROOT/('repair_leases/'+token+'.json'))['state']=='RELEASED'
    for suffix in ('.json','.ready.json','.end.json'):
        name=token+suffix
        copies.append((ROOT/'repair_leases'/name,Path('ROOT_ACTUAL_RELOAD/historical_lease')/name))
    copies.append((Path(__file__).resolve(),Path('package_fairness.py')))
    for name in ('package_fairness_initial_harness_01.py','PACKAGE_HARNESS_RECEIPT_EXIT_FIELD_FAILURE_01.json'):
        copies.append((OUT/name,Path('PACKAGE_HARNESS_FAILURE_01')/name))
    originals={str(origin):record(origin) for origin,_ in copies}
    DEST.mkdir(parents=True)
    provenance={}
    for origin,relative in copies:
        target=DEST/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(origin.read_bytes())
        src,dst=record(origin),record(target)
        assert all(src[name]==dst[name] for name in ('bytes','sha256'))
        provenance[relative.as_posix()]=dict(origin=src,copied=dst)
    (DEST/'README.md').write_bytes(README.encode('utf8'))
    (DEST/'.gitattributes').write_bytes(b'* -text\n** -text\n')
    write(DEST/'COPY_PROVENANCE.json',dict(schema='V42_COORDINATOR_FIRST_SWEEP_FAIRNESS_EXACT_COPY_PROVENANCE',
        UTC=datetime.now(timezone.utc).isoformat(),copies=provenance,
        packaging_production_mutations=0,packaging_Native_optimize_calls=0,packaging_model_constructions=0,
        packaging_scientific_module_imports=0,packaging_Git_mutations=0,
        actual_root_owned_supervisor_reload_recorded_separately=True,
        mathematical_campaign_PASS_claimed=False))
    payload={path.relative_to(DEST).as_posix():{name:record(path)[name] for name in ('bytes','sha256')}
        for path in sorted(DEST.rglob('*')) if path.is_file()}
    inventory=DEST/'SHA_INVENTORY.json'
    write(inventory,dict(schema='V42_COORDINATOR_FIRST_SWEEP_FAIRNESS_DOC_INVENTORY',
        UTC=datetime.now(timezone.utc).isoformat(),files=payload,
        payload_file_count=len(payload),payload_bytes=sum(row['bytes'] for row in payload.values()),
        exact_origin_copy_count=len(copies),inventory_excludes_only_itself=True,
        scientific_date_PASS_claimed=False))
    current={path.relative_to(DEST).as_posix():{name:record(path)[name] for name in ('bytes','sha256')}
        for path in sorted(DEST.rglob('*')) if path.is_file() and path!=inventory}
    assert current==payload
    assert {str(origin):record(origin) for origin,_ in copies}==originals
    assert {str(path):record(path) for path in previous}==previous_before
    sources_after=dict(original=hashes(expected_original),
        frozen={v:hashes(paths) for v,paths in frozen.items()})
    assert sources_after==sources_before
    proof=dict(PASS=True,schema='V42_COORDINATOR_FIRST_SWEEP_FAIRNESS_DOC_SEAL_VERIFICATION',
        UTC=datetime.now(timezone.utc).isoformat(),package=str(DEST),inventory=record(inventory),
        total_file_count=len(payload)+1,payload_file_count=len(payload),
        payload_bytes=sum(row['bytes'] for row in payload.values()),exact_origin_copy_count=len(copies),
        all_payload_file_set_bytes_and_SHA_verified=True,all_origins_start_end_byte_exact=True,
        original_repo_1007_and_frozen_D35_D36_1111_start_end_exact=True,
        previous_sealed_inventories_start_end_exact=previous_before,
        packaging_production_mutations=0,packaging_Native_optimize_calls=0,
        packaging_model_constructions=0,packaging_scientific_imports=0,packaging_Git_mutations=0,
        copied_actual_independent_receipt=record(actual_receipt),
        mathematical_campaign_PASS_claimed=False)
    path=OUT/'COORDINATOR_FIRST_SWEEP_FAIRNESS_DOC_PACKAGE_SEAL_VERIFICATION.json'
    write(path,proof)
    print(json.dumps(dict(PASS=True,package=str(DEST),inventory=record(inventory),
        files=proof['total_file_count'],payload_bytes=proof['payload_bytes'],
        copies=len(copies),verification=record(path))))


if __name__=='__main__':main()
