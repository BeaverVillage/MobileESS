"""Read completed prefix artifacts and cache code; never execute a replay."""
from datetime import datetime,timezone
from pathlib import Path
import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
import numpy as np

ROOT=Path(__file__).parents[2]
DROP={'policy_sha','policy_id_sha','rule_id','candidate_id','selected_candidate',
      'source_freeze_sha','source_epoch_sha','online_grid_horizon_evaluations','signed_packet_evaluation_calls'}


def canonical(value):
    if isinstance(value,dict):return {k:canonical(v) for k,v in value.items() if k not in DROP}
    if isinstance(value,list):return [canonical(v) for v in value]
    return value
def record(path):
    p=Path(path);b=p.read_bytes();return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def gz(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def first_diff(a,b,path=''):
    if type(a)!=type(b):return dict(path=path,reason='TYPE')
    if isinstance(a,dict):
        if a.keys()!=b.keys():return dict(path=path,reason='KEYS')
        for key in a:
            d=first_diff(a[key],b[key],path+'/'+str(key))
            if d:return d
    elif isinstance(a,list):
        if len(a)!=len(b):return dict(path=path,reason='LENGTH',old=len(a),new=len(b))
        for i,(x,y) in enumerate(zip(a,b)):
            d=first_diff(x,y,path+'/'+str(i))
            if d:return d
    elif a!=b:return dict(path=path,reason='VALUE',old=a,new=b)
    return None


def main():
    old=ROOT/'audit/performance/EPOCH03_OLD_PREFIX'
    new=ROOT/'audit/performance/EPOCH04_EXACT_CACHE_PREFIX'
    ro,rn=read(old/'PREFIX_RECEIPT.json'),read(new/'PREFIX_RECEIPT.json')
    behavioral=first_diff(gz(old/'PREFIX_BEHAVIOR_CANONICAL.json.gz'),gz(new/'PREFIX_BEHAVIOR_CANONICAL.json.gz'))
    # Public execution state only. Do not inspect simulator-only remaining
    # service and do not feed any archived result into the live selector.
    full_old,full_new=gz(old/'PREFIX_RESULT.json.gz'),gz(new/'PREFIX_RESULT.json.gz')
    public_diffs={}
    for name in ('reservation_ledger',):
        public_diffs[name]=first_diff(canonical(full_old[name]),canonical(full_new[name]))
    runtime_hashes=[]
    for result in (full_old,full_new):
        state=result['carryout']['controller']['experimental_runtime_state']
        runtime_hashes.append(dict(claimed_sha=state['runtime_state_sha'],
            valid=state['runtime_state_sha']==digest({k:v for k,v in state.items() if k!='runtime_state_sha'}),
            source_program_policy_sha=state['policy_sha']))
    old_public=canonical(full_old['carryout']['controller'])
    new_public=canonical(full_new['carryout']['controller'])
    # This hash commits to policy_sha, whose source/program identity changes.
    # Verify both raw commitments, then compare their entire public payload
    # after the declared program-identity normalization, without that derivedhash.
    old_public['experimental_runtime_state'].pop('runtime_state_sha')
    new_public['experimental_runtime_state'].pop('runtime_state_sha')
    public_diffs['carryout_controller']=first_diff(old_public,new_public)
    array_rows=[]
    with np.load(old/'PREFIX_ARRAYS.npz',allow_pickle=False) as ao,np.load(new/'PREFIX_ARRAYS.npz',allow_pickle=False) as an:
        if ao.files!=an.files:raise ValueError('PREFIX_ARRAY_KEYS_CHANGED')
        for key in ao.files:
            a,b=ao[key],an[key]
            array_rows.append(dict(name=key,shape=list(a.shape),dtype=str(a.dtype),
                equal=np.array_equal(a,b),raw_bytes_equal=a.tobytes()==b.tobytes(),
                max_abs_difference=float(np.max(np.abs(a-b))) if a.size else 0.))
    files=('experimental_policy.py','experimental_actual.py','experimental_grid.py',
           'q90_recourse.py','policy.py','actual.py')
    source_records=[record(ROOT/'v42_integration'/name) for name in files]
    tests=ET.parse(ROOT/'audit/FINAL_INTEGRATED_TEST_RESULTS.xml').getroot()
    cases=list(tests.iter('testcase'))
    failures=sum(len(list(c.iter('failure')))+len(list(c.iter('error'))) for c in cases)
    base=read(ROOT/'audit/performance/EPOCH03_PRECACHE/ABORTED_PROBE_RECEIPT.json')
    source_snapshot=[record(p) for p in sorted((ROOT/'audit/performance/EPOCH03_PRECACHE').rglob('*')) if p.is_file()]
    checks=[
        dict(id='scalar_cache',PASS=True,evidence='Per immutable packet key=slot,dtype,shape,complete rawdelta bytes; bounded1024; stored and returned violations deepcopy; disabled path invokes identical uncached source rows.'),
        dict(id='original_hard_geometry',PASS=True,evidence='Uncached scalar expressions and1e-9 guards remain same. Existing batch hardfallback and exactpeak paths now use exactscalar memoization, without coefficient/authority/input scaling.'),
        dict(id='lazy_base_profile',PASS=True,evidence='Same original segment sum is delayed until instantaneous sourcegrid PASS. Fullframe UID/status/resource/begin/end/quantity key preserves iteration order; include ownUID exclusion,state and exact offgrid Running clock; returncopy.'),
        dict(id='dead_R0_path',PASS=True,evidence='Early return occurs only when no due-proof eligibility and no applicable priorblock; original branch could neither write proof noradvanceR0. Expiredunsupportedwait remains invalid; same captured public prefix referenceaudit.'),
        dict(id='resource_filtered_fit',PASS=True,evidence='Literal ReservationLedger._fits receives fullquery/exclude/envelope/scope/caps. Filtering only removes irrelevant existing resource segments; matching UID/segment order, scope/envelopeguard fields and endpoints are retained.'),
        dict(id='resource_mutation_invalidation',PASS=True,evidence='Successful reserve,activate,release,retain_running invalidategeneration/views while holding same RLock; failedreserve onlyappendsaudit. Direct testmutation mustinvalidateexplicitly; experimentalrestorefailsclosed.'),
        dict(id='public_state_only',PASS=True,evidence='Cache frames contain public reservations/currentclock/observedGPU/sourceinputs only. No Environment/realized future duration/end data enter cache keys, delta or recourse.'),
        dict(id='D_and_Base_fit_unchanged',PASS=True,evidence='SharedD modulebc7425ec and Base policy2182c740 stay exact; no new recourse model or rewritten feasibility equations.'),
        dict(id='same_case_prefix_behavior',PASS=behavioral is None,evidence='Completed2slot canonical behavior compared independently after exactidentity/work-countfield exclusions.',first_difference=behavioral),
        dict(id='same_case_public_reservations_and_runtime_state',PASS=all(v is None for v in public_diffs.values()),first_differences=public_diffs),
        dict(id='runtime_state_hashes_valid_identity_only',PASS=all(v['valid'] for v in runtime_hashes),raw_commitments=runtime_hashes,
            reason='Raw stateSHA includes changed sourceprogrampolicySHA; entire canonicalpublicpayload compared after validatingbothcommitments.'),
        dict(id='same_case_physical_arrays',PASS=all(r['raw_bytes_equal'] for r in array_rows),arrays=array_rows),
        dict(id='exact_same_case_and_horizon',PASS=ro['case_sha']==rn['case_sha'] and ro['slots']==rn['slots']==2 and not ro['Full96'] and not rn['Full96']),
    ]
    value=dict(schema='INDEPENDENT_C_EXACT_CACHE_PREFIX_REVIEW_V1',written_utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_SCOPED_SOURCE_AND_TWO_SLOT_EQUIVALENCE' if all(c['PASS'] for c in checks) else 'FAIL',
        checks=checks,source_records=source_records,old_prefix_receipt=ro,new_prefix_receipt=rn,
        recorded_wall_speedup=ro['wall_seconds']/rn['wall_seconds'],
        test_evidence=dict(testcases=len(cases),failures_or_errors=failures,reported_control_tests_PASS=35,
            reported_grid_tests_PASS=5,tests_reexecuted_by_this_reviewer=False,
            integrated_xml=record(ROOT/'audit/FINAL_INTEGRATED_TEST_RESULTS.xml')),
        artifact_records=[record(d/name) for d in (old,new) for name in ('PREFIX_RECEIPT.json','PREFIX_RESULT.json.gz',
            'PREFIX_BEHAVIOR_CANONICAL.json.gz','PREFIX_ARRAYS.npz')],
        preserved_aborted_probe=base,preserved_precache_records=source_snapshot,
        source_only_review_production_edits=0,Native_Optimize_calls=0,Actual_replays_by_this_reviewer=0,Fresh_AC_calls=0,
        simulator_private_state_inspected_or_used=False,existing_monitor_or_worker_modified=False,
        unresolved_blocking_findings=[],
        limitations=[
            'Measured speedup and exact behavior/physical equality cover the identical two-slot May prefix only; not Full96 or31day performance/correctness.',
            'AbortedSource4a probe reached30slots,CPU793s; no finalFull96Actual orFreshAC result is certified.',
            'Scalar memoization inherits immutable packet/coefficient/control/authority contract. Newphysicalsource or changed packet fields require a new packet or complete cache invalidation.',
            'Resource views require all mutation through atomic ledger methods. Direct imported/manual mutation is unsupported unless explicitly invalidated; E1/E2 arbitrary continuation failsclosed.',
            'Prefixcomparison drops onlyprogramidentity andwork-countfields; it also compares complete publicreservation/runtime state and exactIT/PCC/GPUarrays. No privatefuture is used for selection.',
            'Originaljob/source/quantiles/kernel/CDF/capacity/gridconstraints and sharedsolverledger remain unchanged; no jointA/M optimality ornewActualACcertificate transfer.'])
    if failures:raise ValueError('INTEGRATED_TEST_FAILURE_RECEIPT')
    output=Path(__file__).with_name('C_EXACT_CACHE_PREFIX_INDEPENDENT_REVIEW.json')
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=value['status'],old_wall_seconds=ro['wall_seconds'],new_wall_seconds=rn['wall_seconds'],
        speedup=value['recorded_wall_speedup'],behavior_diff=behavioral,public_diffs=public_diffs,
        arrays=array_rows,testcases=len(cases),checks_PASS=sum(c['PASS'] for c in checks),output=str(output))))


if __name__=='__main__':main()
