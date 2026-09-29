"""Read-only authority checks; no prediction, label scoring, or reserve replay."""
import subprocess
import xml.etree.ElementTree as ET
from .common import *
from .native import canonical_jobs
from .resource_certificate import bounds


def protected_tree(repo,head,prefixes):
    listing=subprocess.check_output(['git','ls-tree','-r',head],cwd=repo).decode().splitlines()
    rows=[]
    for line in listing:
        meta,name=line.split('\t',1)
        if not name.startswith(prefixes) or not (repo/name).is_file():continue
        raw=(repo/name).read_bytes();blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        expected=meta.split()[2];require(blob==expected,'PROTECTED_GIT_BLOB_CHANGED:'+name)
        rows.append(dict(path=name,git_blob=blob,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
    require(rows,'PROTECTED_SCOPE_EMPTY')
    return rows


def all_records(value):
    if isinstance(value,dict):
        if 'path' in value and 'sha256' in value:yield value
        for item in value.values():yield from all_records(item)
    elif isinstance(value,list):
        for item in value:yield from all_records(item)


def main():
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=RUNTIME).decode().strip()==RUNTIME_HEAD,'PR95_HEAD_DRIFT')
    old=protected_tree(ROOT,BASE,('v42_','docs/v42_','tests/test_v42'))
    runtime=protected_tree(RUNTIME,RUNTIME_HEAD,('docs/runtime_final_duration_calibration/',
        'docs/runtime_q50_calibration_audit/','docs/runtime_vnext10_tail_calibrated_hazard/',
        'docs/runtime_vnext9_distributional_runtime/','docs/runtime_vnext8_trace_feature_total/'))
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,PR93_head=BASE,PR95_head=RUNTIME_HEAD,
        PR93_files=len(old),PR94_PR95_and_used_lineage_files=len(runtime),
        comparison='Raw worktree bytes -> Git blob SHA1 and independently recorded SHA256; no line-ending normalization',
        PR93=old,PR94_PR95_lineage=runtime,prior_NONE_conclusions_rewritten=False))
    excluded={'SOURCE_MANIFEST.json','DELIVERY_MANIFEST.json','VERIFICATION.json','LOCAL_EVIDENCE_MANIFEST.json','LEGACY_PRESERVATION_AUDIT.json'}
    expected={}
    for p in OUT.glob('*.json'):
        if p.name in excluded:continue
        for r in all_records(read(p)):
            source=Path(r['path'])
            require(source.is_file(),'MISSING_EVIDENCE:'+str(source))
            key=str(source.resolve());previous=expected.get(key)
            require(previous is None or previous==r['sha256'],'CONFLICTING_SOURCE_HASH:'+key)
            expected[key]=r['sha256']
    sources=[]
    for path,h in sorted(expected.items()):
        require(sha(path)==h,'SOURCE_SHA_CHANGED:'+path);sources.append(rec(path))
    dump('SOURCE_MANIFEST.json',dict(PASS=True,files=sources,implementation_base=BASE,runtime_evidence_head=RUNTIME_HEAD))
    b=read(OUT/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json');jobs=canonical_jobs(b)
    physical={s:sum(r['current_physical_GPU'] for r in jobs if r['site']==s) for s in b['capacities']}
    require(all(physical[s]<=b['capacities'][s] for s in physical),'CURRENT_RUNNING_PHYSICAL_CAPACITY')
    br=bounds([j for j in b['known_population'] if j['planning_eligible']],b['unknown_nominal_GPU'],b['capacities'])
    worst=max(br,key=lambda r:r['excess_GPU']);require(worst==read(OUT/'MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json')['worst'],'NECESSARY_PROOF_REPRODUCTION')
    holdout=read(OUT/'RUNTIME_RESERVE_HOLDOUT_RECEIPT.json')
    require(holdout['calibration_sha_before']==holdout['calibration_sha_after']==sha(OUT/'RUNTIME_RESERVE_CALIBRATION.json'),'GAMMA_NOT_RESEALED')
    require(not (OUT/'FINAL_RESPONSE_KERNEL_AUTHORITY.json').exists(),'UNVALIDATED_FINAL_KERNEL')
    xml=ET.parse(LOCAL/'pytest.xml').getroot();suites=xml.findall('testsuite')
    tests=sum(int(s.attrib['tests']) for s in suites);failures=sum(int(s.attrib['failures'])+int(s.attrib['errors']) for s in suites)
    require(tests>=245 and failures==0,'TEST_SUITE_NOT_PASS')
    dump('LOCAL_EVIDENCE_MANIFEST.json',dict(files=[rec(p) for p in sorted(LOCAL.iterdir()) if p.is_file()],
        purpose='Native necessary-LP diagnostics, frozen once-only OOF replay arrays and test receipt; no new raw dataset upload'))
    dump('VERIFICATION.json',dict(PASS=True,tests=tests,failures=failures,test_receipt=rec(LOCAL/'pytest.xml'),
        command='python -m pytest tests/test_v42_final.py tests/test_v42_native.py tests/test_v42_may01.py tests/test_v42_job_capability.py -q',
        source_hashes_verified=len(sources),legacy_PR93_bytes_verified=len(old),legacy_Runtime_lineage_bytes_verified=len(runtime),
        current_assigned_RUNNING_physical_GPU=physical,physical_capacity_PASS=True,
        analytic_resource_proof_reproduced=True,native_resource_feasible=False,
        runtime_retraining=False,calibration_map_refitting=False,May_Actual_labels_read=False,
        fold5_reserve_validation_repeated=False,gamma_changed_after_holdout=False,
        warning='Frozen ProbabilityMap inverse may emit numpy log1p warning on an unused np.where branch; finite outputs and exact reproduction verified',
        native_A1_M1_A2_M2_executed=False,Fresh_AC_PASS=False))
    paths=list((ROOT/'v42_final').rglob('*'))+list(OUT.rglob('*'))+[ROOT/'tests/test_v42_final.py',ROOT/'tests/.gitattributes']
    files=[dict(relative=str(p.relative_to(ROOT)).replace('\\','/'),sha256=sha(p),bytes=p.stat().st_size)
           for p in sorted(paths) if p.is_file() and '__pycache__' not in str(p) and p.name!='DELIVERY_MANIFEST.json']
    dump('DELIVERY_MANIFEST.json',dict(files=files,excludes_self=True,base=BASE,scope='Only new V42 package, docs and test; prior evidence unchanged'))
    print(json.dumps(dict(PASS=True,tests=tests,PR93_bytes=len(old),Runtime_bytes=len(runtime),sources=len(sources)),indent=2))


if __name__=='__main__':main()
