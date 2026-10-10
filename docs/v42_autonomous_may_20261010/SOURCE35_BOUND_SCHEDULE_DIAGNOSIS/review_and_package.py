"""Read source text and saved artifacts only; no original functions or probes."""
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
import csv
import hashlib
import json

SOURCE=Path(r'D:\v42_source35_bound_schedule_readonly_20261010_01')
REPO=Path(r'D:\MobileESS_v42_autonomous')
ROOT=Path(r'D:\v42_may_restart_20261010_02')
BASE=REPO/'docs/v42_autonomous_may_20261010'
DEST=BASE/'SOURCE35_BOUND_SCHEDULE_DIAGNOSIS'
OUT=Path(__file__).resolve().parent


def record(path):
    raw=Path(path).read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def read(path):return json.loads(Path(path).read_bytes().decode('utf-8-sig'))


def hashes(paths):return {str(path):record(path)['sha256'] for path in paths}


def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8'))


def main():
    assert not DEST.exists(),'NEW_DOC_PACKAGE_ALREADY_EXISTS'
    assert record(SOURCE/'REPORT.md')['sha256']=='8ac6ce651bf966fa50cb4d8ef2e972bd5f2115b5e63e959a8b53efadd4cec795'
    assert record(SOURCE/'SHA_INVENTORY.json')['sha256']=='a2e48b06669ff4b3aafc00bfdd541bfb067f28995212489301f5388334826623'
    inventory=read(SOURCE/'SHA_INVENTORY.json')['files']
    actual_files={path.relative_to(SOURCE).as_posix() for path in SOURCE.rglob('*')
        if path.is_file() and path.name!='SHA_INVENTORY.json' and '__pycache__' not in path.parts}
    assert actual_files==set(inventory),'SEALED_SOURCE_FILE_SET_DRIFT'
    for relative,expected in inventory.items():
        current=record(SOURCE/relative)
        assert all(current[key]==expected[key] for key in ('bytes','sha256')),(relative,'SOURCE_INVENTORY_DRIFT')
    evidence=read(SOURCE/'SOURCE35_BOUND_SCHEDULE_READONLY_EVIDENCE.json')
    assert evidence['PASS_scope']=='source-byte and saved-log consistency only; no scientific replay or final PASS qualification'
    m35=read(ROOT/'B2_V35_ZERO_START_DEPLOYMENT_MANIFEST.json')
    m36=read(ROOT/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json')
    assert m35['builder_original_sources']==m36['builder_original_sources']
    expected_original={str(REPO/name):digest for name,digest in m36['builder_original_sources'].items()}
    frozen={}
    for version in ('35','36'):
        freeze=read(ROOT/('autonomous/V'+version+'_SPARSE_IMMUTABLE_FREEZE.json'))
        frozen[version]={row['path']:row['sha256'] for row in freeze['source_files']}
    protected_before=dict(original=hashes(expected_original),frozen={v:hashes(paths) for v,paths in frozen.items()})
    assert protected_before['original']==expected_original
    assert all(protected_before['frozen'][v]==expected for v,expected in frozen.items())
    ranges={
        'v42_may_campaign_native90/m_stage.py':(215,270),
        'v42_m1_anytime/algorithms.py':(150,213),
        'v42_m1_anytime/core.py':(135,193),
        'v42_m1_hybrid/blocks.py':(1,120),
        'v42_m1_hybrid/pricing.py':(300,371),
        'v42_m1_hybrid/dw.py':(84,118),
        'v42_m1_hybrid/bound.py':(30,72),
        'v42_m1_hybrid/verify.py':(110,152),
        'v42_m1_research/check_lb.py':(94,166),
    }
    references={}
    for name,(start,end) in ranges.items():
        raw35=(SOURCE/'source35'/name).read_bytes()
        raw36=(SOURCE/'source36'/name).read_bytes()
        assert raw35==raw36
        digest=hashlib.sha256(raw35).hexdigest()
        assert digest==m35['builder_original_sources'][name]
        assert digest==frozen['35'][str(Path(r'D:\v42run35')/name)]==frozen['36'][str(Path(r'D:\v42run36')/name)]
        lines=raw35.decode('utf-8-sig').splitlines()
        references[name]=dict(sha256=digest,line_range=[start,end],
            source_text_read_only=[dict(line=i,text=lines[i-1]) for i in range(start,end+1)])
    core=(SOURCE/'source35/v42_m1_anytime/core.py').read_text(encoding='utf-8-sig')
    stage=(SOURCE/'source35/v42_may_campaign_native90/m_stage.py').read_text(encoding='utf-8-sig')
    dw=(SOURCE/'source35/v42_m1_hybrid/dw.py').read_text(encoding='utf-8-sig')
    algo=(SOURCE/'source35/v42_m1_anytime/algorithms.py').read_text(encoding='utf-8-sig')
    method=(SOURCE/'source36/v42_autonomous_b2/rmp_presolve.py').read_text(encoding='utf-8-sig')
    assert "<(2 if k in ('L2','L3') else 1)" in core and "[-3:]" in core
    assert "if rmpdual is None:" in stage and "status='NOT_RUN_NO_FINITE_RMP_PI'));continue" in stage
    assert "except TimeoutError:" in stage and "except Exception as exc:" in stage
    assert "if pi is not None and np.isfinite(pi).all():" in dw and "seconds!=30" in dw
    assert "if model.SolCount:" in dw and "full_original_dual=None" in dw
    assert "PRICE_PRODUCER_AND_INDEPENDENT_BOUND_DIFFER" in algo and "status='NOT_PROVEN'" in algo
    assert "tolerance=1e-9" in method and "candidate_Method=0 if eligible else 1" in method
    dates={}
    for day,expected_count in [('2025-05-01',44),('2025-05-02',36),('2025-05-03',28)]:
        directory=SOURCE/'actual'/day
        saved=read(directory/'ADAPTIVE_SCHEDULER_AUDIT.json')
        request=read(directory/'request.json')
        declared=evidence['actual_saved_days'][day]
        assert request['implementation_SHA']==evidence['Source35_execution_SHA']
        assert request['attempt_id']==declared['attempt_id']
        assert saved['case_sha']==declared['case_sha']
        choices=saved['choices'];history=saved['history']
        assert len(choices)==expected_count==declared['scheduler_choices_snapshot_count']
        assert [row['method'] for row in choices[:8]]==['U1','U2','U3','U4','L1','L2','L3','L4']
        assert all(row['method'].startswith('U') for row in choices[8:])
        counts=Counter(row['method'] for row in history)
        assert all(counts[k]==1 for k in ('L1','L2','L3','L4'))
        rmp_records=[]
        for track,label in [('L2','005_L2_00_MASTER'),('L3','006_L3_00_MASTER')]:
            packet=read(directory/label/'RMP_RESULT.json')
            native=packet['native']
            assert packet['case_sha']==saved['case_sha']
            assert packet['dual_status']=='NO_FINITE_PI_FOLLOWUP_PRICING_NOT_RUN'
            assert packet['full_original_dual'] is None and packet['convexity_duals'] is None
            assert packet['restricted_master_is_Global_LB'] is False
            assert native['entered_native'] is True and native['status']=='FINISHED' and native['error'] is None
            assert native['Native_status']==11 and native['SolCount']==0 and native['effective_TimeLimit']==30.
            row=next(row for row in history if row['method']==track)
            assert row['certified_gain']==0 and row['status']=='NOT_RUN_NO_FINITE_RMP_PI'
            rmp_records.append({key:native[key] for key in ('Native_status','SolCount','Native_Runtime','effective_TimeLimit')})
        l1=read(directory/'004_L1_00/INDEPENDENT_GLOBAL_LB_CERTIFICATE.json')
        l4=read(directory/'007_L4_00/INDEPENDENT_GLOBAL_LB_CERTIFICATE.json')
        l1row=read(directory/'004_L1_00/LB_RESULT.json')
        l4row=read(directory/'007_L4_00/LB_RESULT.json')
        # Literal saved certificate comparison only, never a rational checker replay.
        assert Fraction(l1['exact_Global_LB'])==Fraction(l4['exact_Global_LB'])>0
        dual1=record(directory/'004_L1_00/INDEPENDENT_FULL_ORIGINAL_DUAL_EXACT.json')
        dual4=record(directory/'007_L4_00/INDEPENDENT_FULL_ORIGINAL_DUAL_EXACT.json')
        assert dual1['sha256']==dual4['sha256']==l1['dual_sha256']==l4['dual_sha256']
        assert l4row['adopted'] is False and l4row['certified_gain']==0
        assert l1row['adopted'] is True and l1row['certified_gain']>0
        state=read(directory/'CURRENT_CERTIFIED_STATE.json')
        assert state['LB_certificate_sha256']==record(directory/'004_L1_00/INDEPENDENT_GLOBAL_LB_CERTIFICATE.json')['sha256']
        with (directory/'FRONTIER_EVENTS.csv').open(encoding='utf-8-sig',newline='') as stream:
            events=list(csv.DictReader(stream))
        positive=[row for row in events if row['LB_improved']=='True']
        assert len(positive)==1 and positive[0]['LB_certificate_sha256']==state['LB_certificate_sha256']
        prefix=read(directory/'PRIOR_SAVED_NATIVE_PREFIX.json')
        dates[day]=dict(saved_choices=len(choices),history_counts=dict(counts),RMP=rmp_records,
            saved_missingPi_is_direct_result_not_inferred_from_SolCount=True,
            L1_L4_exact_LB=l1['exact_Global_LB'],L1_L4_exact_dual_SHA=dual1['sha256'],
            L4_not_adopted=True,positive_LB_events=1,saved_frontier_UTC=state['UTC'],
            historical_Native_prefix_UTC=prefix.get('UTC'),
            current_runtime_or_atomic_cross_file_snapshot_claimed=False)
    assert evidence['Source36_usable_Pi_or_certified_improvement_or_performance_observed_by_this_audit'] is False
    report_record=record(SOURCE/'REPORT.md')
    review_path=OUT/'SOURCE35_BOUND_SCHEDULE_INDEPENDENT_READONLY_REVIEW.json'
    review=dict(PASS=True,PASS_scope='source-byte, line-content and saved-artifact consistency; no scientific qualification',
        UTC=datetime.now(timezone.utc).isoformat(),report=report_record,source_inventory=record(SOURCE/'SHA_INVENTORY.json'),
        original9_source_content_references=references,dates=dates,
        findings=['Original L1/L4 eligibility counts and L2/L3 zero gain explain continued UB choices in these saved traces.',
            'Saved RMP missingPi leads to current-track continue, not a whole-attempt TIME_LIMIT abort.',
            'Source36 finite Pi, certified improvement and measured performance remain unobserved here.'],
        limitations=['Different saved file timestamps are not an atomic current-state or final Runtime snapshot.',
            'RMP None packets are direct saved evidence; SolCount0 alone is not a general Pi-availability proof.',
            'No original function execution, scheduler simulation, checker replay, new tests or model/Native calls.',
            'No final Global Gap, FULL, Actual, Fresh or date scientific PASS is certified.'],
        Native_optimize_calls=0,model_constructions=0,science_module_imports=0,
        original_functions_executed=0,checker_replays=0,new_tests=0,
        production_queue_lease_process_or_Git_mutations=0,producer=record(__file__))
    write(review_path,review)
    previous=list(BASE.rglob('SHA_INVENTORY*.json'))
    previous_before={str(path):record(path) for path in previous}
    copies=[(path,Path('ORIGINAL_READONLY_REPORT')/path.relative_to(SOURCE))
        for path in sorted(SOURCE.rglob('*')) if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc']
    copies.extend([(review_path,Path('INDEPENDENT_READONLY_REVIEW')/review_path.name),
        (Path(__file__).resolve(),Path('review_and_package.py'))])
    origins_before={str(origin):record(origin) for origin,_ in copies}
    DEST.mkdir(parents=True)
    provenance={}
    for origin,relative in copies:
        target=DEST/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(origin.read_bytes())
        src,dst=record(origin),record(target)
        assert all(src[key]==dst[key] for key in ('bytes','sha256'))
        provenance[relative.as_posix()]=dict(origin=src,copied=dst)
    (DEST/'.gitattributes').write_bytes(b'* -text\n** -text\n')
    (DEST/'README.md').write_bytes(('''# Source35 bound scheduling: saved-evidence review

The original report is copied byte exactly under ORIGINAL_READONLY_REPORT.
The independent review reads the original nine Source35/36 source pairs,
their line content, all three saved scheduler traces, six RMP result packets,
L1/L4 certificates and dual receipts, saved Frontier state and CSV events.
It verifies source/receipt consistency only; its PASS is not scientific PASS.

The saved RMP status11/missingPi cases skip only that L2/L3 price attempt.
Their original caller records gain0 then continues. Original L1/L4 count caps
exclude them after one completed history entry; zero-gain eligible L2/L3 do
not outrank UB choices. All saved post-pilot choices are UB, with later L4 and
UB work present. This supports the report's count-and-gain scheduling diagnosis,
not a whole-attempt TIME_LIMIT abort. L4 retains the same exact LB and full
dual SHA as L1 and was not adopted.

The original 30-second RMP limit is per feedback-master call. Future Source36
finite Pi remains subject to original price/checker/Frontier gates and bounded
remaining L2/L3 selections. No actual Source36 finite Pi, improved certified LB,
solver performance or final Global Gap/FULL/Actual/Fresh PASS is observed or
asserted by this review. Different saved UTCs and historical Native prefixes
are preserved; they are not atomic current observations or final Native totals.

No source function, scheduler simulation, scientific checker or new test was
executed. Model/Native/scientific-import and production/queue/process/Git
mutation counts are zero. COPY_PROVENANCE and SHA_INVENTORY seal every copy;
local .gitattributes preserves raw bytes. Older documentation packages, original
science1007 and immutable D35/D36 each1111 retain their existing hashes.
''').encode('utf8'))
    write(DEST/'COPY_PROVENANCE.json',dict(schema='V42_SOURCE35_BOUND_SCHEDULE_EXACT_COPY_PROVENANCE',copies=provenance,
        scientific_PASS_claimed=False,production_mutations=0,Native_optimize_calls=0))
    payload={path.relative_to(DEST).as_posix():{key:record(path)[key] for key in ('bytes','sha256')}
        for path in sorted(DEST.rglob('*')) if path.is_file()}
    inv=DEST/'SHA_INVENTORY.json'
    write(inv,dict(schema='V42_SOURCE35_BOUND_SCHEDULE_DIAGNOSIS_DOC_INVENTORY',files=payload,
        payload_file_count=len(payload),payload_bytes=sum(row['bytes'] for row in payload.values()),
        exact_origin_copy_count=len(copies),inventory_excludes_only_itself=True,scientific_PASS_claimed=False))
    current={path.relative_to(DEST).as_posix():{key:record(path)[key] for key in ('bytes','sha256')}
        for path in sorted(DEST.rglob('*')) if path.is_file() and path!=inv}
    assert current==payload and {str(origin):record(origin) for origin,_ in copies}==origins_before
    assert {str(path):record(path) for path in previous}==previous_before
    protected_after=dict(original=hashes(expected_original),frozen={v:hashes(paths) for v,paths in frozen.items()})
    assert protected_after==protected_before
    proof=OUT/'SOURCE35_BOUND_SCHEDULE_DOC_PACKAGE_SEAL_VERIFICATION.json'
    write(proof,dict(PASS=True,PASS_scope='documentation exact-copy and independent saved-artifact consistency only',
        package=str(DEST),inventory=record(inv),review=record(review_path),files=len(payload)+1,
        payload_bytes=sum(row['bytes'] for row in payload.values()),exact_copy_count=len(copies),
        source1007_D35_D36_1111_start_end_exact=True,previous_inventory_count=len(previous),
        previous_inventories_start_end=previous_before,Native_optimize_calls=0,model_constructions=0,
        checker_replays=0,new_tests=0,production_mutations=0,Git_mutations=0,scientific_PASS_claimed=False))
    print(json.dumps(dict(PASS=True,package=str(DEST),inventory=record(inv),review=record(review_path),
        verification=record(proof),files=len(payload)+1,payload_bytes=sum(row['bytes'] for row in payload.values()),
        copies=len(copies),older_inventories=len(previous))))


if __name__=='__main__':main()
