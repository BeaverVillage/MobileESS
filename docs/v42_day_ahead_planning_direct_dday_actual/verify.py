"""Read-only byte/call audit and evidence publication; never executes a model."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE='e2d4779685fff6d0cf022c649733b2ca41fdfc08'


def sha(data):return hashlib.sha256(data).hexdigest()
def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)


def preservation():
    rows=[]
    for item in git('ls-tree','-rz',BASE).split(b'\0'):
        if not item:continue
        info,path=item.split(b'\t',1)
        name=path.decode('utf-8')
        if name.startswith('docs/'):
            rows.append((name,info.split()[2]))
    # Batch reads retain exact Git blob bytes, including CRLF and binary evidence.
    raw=subprocess.check_output(['git','cat-file','--batch'],cwd=ROOT,
        input=b'\n'.join(blob for _,blob in rows)+b'\n')
    position=0;checked=[];changed=[]
    for path,blob in rows:
        end=raw.index(b'\n',position);header=raw[position:end].split()
        size=int(header[2]);data=raw[end+1:end+1+size];position=end+size+2
        local=ROOT/path;observed=sha(local.read_bytes()) if local.is_file() else None
        checked.append(dict(path=path,git_blob=blob.decode(),base_sha256=sha(data),observed_sha256=observed))
        if observed!=sha(data):changed.append(path)
    snapshot=OUT/'V41_EXTERNAL_SOURCE_BASELINE.json'
    if not snapshot.exists():
        sources={}
        for manifest in ROOT.glob('docs/**/SOURCE_MANIFEST.json'):
            value=json.loads(manifest.read_text(encoding='utf-8-sig'))
            rows=value.get('files',[]) if isinstance(value,dict) else value
            for row in rows:
                if not isinstance(row,dict):continue
                p=Path(row.get('path',''))
                if 'MobileESS_v41' in str(p) and p.is_file():sources[str(p)]=p
        historical=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
        for folder in historical.glob('dayahead/v41*'):
            for p in folder.rglob('*.py'):sources[str(p)]=p
        for suffix in ('dayahead/v28r2/opendss_backend.py','dayahead/v41/execution.py'):
            p=historical/suffix
            if p.is_file():sources[str(p)]=p
        write(snapshot.name,dict(provenance='Read-only initial raw-byte snapshot, not a new V41 authority',
            files=[dict(path=name,sha256=sha(p.read_bytes())) for name,p in sorted(sources.items())]))
    external=[]
    for row in json.loads(snapshot.read_text(encoding='utf-8'))['files']:
        p=Path(row['path']);observed=sha(p.read_bytes()) if p.is_file() else None
        external.append(dict(path=row['path'],baseline_sha256=row['sha256'],observed_sha256=observed,
                             PASS=observed==row['sha256']))
    passed=not changed and bool(external) and all(r['PASS'] for r in external)
    write('V41_PRESERVATION_AUDIT.json',dict(PASS=passed,baseline_sha=BASE,
        V41_DAYAHEAD_AC_VALIDATION='HISTORICAL',
        V42_DAYAHEAD_AC_VALIDATION='REMOVED_FROM_OPERATIONAL_CHAIN',
        scope='All baseline tracked docs/evidence byte-for-byte; locally available referenced V41 source files and V41 Python namespaces. External runtime/campaign archives are untouched and not exhaustively rehashed.',
        changed_historical_paths=changed,baseline_evidence_count=len(checked),
        baseline_evidence=checked,external_sources=external))
    assert passed,'HISTORICAL_BYTES_CHANGED'


def call_audit():
    hits=[];calls=[];kernel=[]
    pattern=re.compile(r'fresh_ac|require_fresh_ac|OpenDSS|Day.?Ahead.*AC|FINAL_RESPONSE_KERNEL|require_kernel|KernelAnchor',re.I)
    for name in git('ls-tree','-r','--name-only',BASE).decode().splitlines():
        p=ROOT/name
        if p.suffix not in ('.py','.md','.json'):continue
        if not (name.startswith('v42') or name.startswith('docs/')):continue
        for number,line in enumerate(p.read_text(encoding='utf-8-sig').splitlines(),1):
            if pattern.search(line):
                hits.append(dict(path=name,line=number,text=line[:400],
                    classification='PRESERVED_PRIOR_EVIDENCE_OR_REPORT' if name.startswith('docs/')
                    else 'RUNTIME_CONTRACT_OR_SOURCE_REFERENCE'))
    for folder in ROOT.glob('v42*'):
        if not folder.is_dir():continue
        for p in folder.rglob('*.py'):
            for node in ast.walk(ast.parse(p.read_text(encoding='utf-8-sig'))):
                if isinstance(node,ast.Call):
                    name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ''
                    row=dict(path=p.relative_to(ROOT).as_posix(),line=node.lineno,call=name)
                    if name in ('fresh_ac','require_fresh_ac'):calls.append(row)
                    if name in ('require_kernel','KernelAnchor'):kernel.append(row)
    producers=[r for r in calls if r['call']=='fresh_ac']
    assert len(producers)==1 and producers[0]['path']=='v42_native/actual.py'
    before=git('show',BASE+':v42_native/coordinator.py').decode()
    write('V42_DAYAHEAD_AC_CALL_AUDIT.json',dict(PASS=True,baseline_sha=BASE,
        baseline_coordinator_calls=[line.strip() for line in before.splitlines() if 'fresh_ac' in line],
        planning_fresh_ac_calls=0,actual_fresh_ac_calls=1,
        call_sites=calls,kernel_contract_sites=kernel,repository_text_hits=hits,
        direct_OpenDSS_engine_producer_in_this_checkout=False,
        external_historical_producer='MobileESS_v41r3_scale_rebalance/dayahead/v41/execution.py + dayahead/v28r2/opendss_backend.py',
        final_kernel_audit='No final response/event kernel generation call exists in this checkout. v42_final.gates.require_kernel is the legacy acceptance predicate; v42_native.actual.require_dday_kernel adds full Actual input and upstream identity checks. KernelAnchor validates an existing causal-policy anchor; it does not generate or freeze a final kernel. Report/verify modules only record absence/readiness.',
        old_report_statements='Preserved prior evidence. Superseded operational statements are governed by ARCHITECTURE_BEFORE_AFTER.md.'))


def supersession():
    from sys import path
    path.insert(0,str(ROOT))
    from v42_voltage.preservation import ARCHITECTURE_CHANGES,baseline_blobs
    historical={name:set() for name in ARCHITECTURE_CHANGES}
    def collect(value):
        if isinstance(value,list):
            for row in value:collect(row)
        elif isinstance(value,dict):
            name=value.get('path')
            if isinstance(name,str) and name in historical:
                for key in ('sha256','current_sha256','base_sha256'):
                    s=value.get(key)
                    if isinstance(s,str) and re.fullmatch('[0-9a-f]{64}',s):historical[name].add(s)
                historical[name].update(value.get('historical_sha256',[]))
            for row in value.values():
                if isinstance(row,(dict,list)):collect(row)
    for p in ROOT.glob('docs/**/*.json'):
        if p.parent==OUT:continue
        collect(json.loads(p.read_text(encoding='utf-8-sig')))
    blobs=baseline_blobs();files=[]
    for name in sorted(ARCHITECTURE_CHANGES):
        base=blobs[name];lf=base.replace(b'\r\n',b'\n')
        historical[name].update(sha(v) for v in (base,lf,lf.replace(b'\n',b'\r\n')))
        files.append(dict(path=name,base_sha256=sha(base),current_sha256=sha((ROOT/name).read_bytes()),
                          historical_sha256=sorted(historical[name])))
    write('AUTHORIZED_ARCHITECTURE_SUPERSESSION.json',dict(base_head=BASE,
        authorization='User-requested V42 architecture supersession; source/test/format declarations only; historical evidence unchanged',
        production_execution_authorized=False,files=files))


def verification():
    xml=OUT/'TEST_RESULTS.xml'
    if not xml.exists():return
    tree=ET.parse(xml)
    suites=list(tree.getroot().iter('testsuite'))
    summary={k:sum(int(s.get(k,'0')) for s in suites) for k in ('tests','failures','errors','skipped')}
    assert not summary['failures'] and not summary['errors'],'TESTS_NOT_PASSING'
    assert json.loads((OUT/'V41_PRESERVATION_AUDIT.json').read_text(encoding='utf8'))['PASS']
    diff=subprocess.run(['git','diff','--check','HEAD'],cwd=ROOT,capture_output=True,text=True)
    assert diff.returncode==0,diff.stdout+diff.stderr
    names=('.gitattributes','README.md','v42_native/coordinator.py','v42_native/planning.py','v42_native/actual.py',
           'v42_final/gates.py','v42_voltage/preservation.py','tests/test_v42_dayahead_actual.py',
           'tests/test_v42_may01.py','tests/test_v42_final.py',
           'tests/v42_benders_fullscale/test_fullscale_orchestration.py',
           'tests/v42_benders_v2/test_v42_native_recourse.py',
           'tests/v42_certificate/test_native_evidence.py','tests/v42_threshold/test_native.py',
           'tests/v42_threshold/test_completion.py')
    paths=[ROOT/n for n in names]+sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='VERIFICATION.json')
    write('VERIFICATION.json',dict(PASS=True,baseline_sha=BASE,tests=summary,
        test_command='python -m pytest tests contract_tests -q --junitxml=docs/v42_day_ahead_planning_direct_dday_actual/TEST_RESULTS.xml',
        git_diff_check='PASS (staged and unstaged against HEAD)',historical_byte_verification='PASS',hash_algorithm='SHA256_RAW_BYTES',
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p.read_bytes())) for p in paths],
        downstream='NOT_RUN',production_Fresh_OpenDSS='NOT_RUN',M1_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False))


if __name__=='__main__':
    import sys
    preservation();call_audit();supersession()
    if '--audit-only' not in sys.argv:verification()
    print('Byte preservation / AC call audit / available test evidence: PASS')
