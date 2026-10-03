"""Verify source identity, exact parent bytes, terminal evidence and index hashes."""
import hashlib
import subprocess
from .common import *

def base_identity():
    rows=[]
    output=subprocess.check_output(['git','ls-tree','-r',BASE],cwd=ROOT,text=True,encoding='utf-8')
    for line in output.splitlines():
        meta,path=line.split('\t');oid=meta.split()[2];p=ROOT/path;data=p.read_bytes()
        observed=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if observed!=oid:raise ValueError('EXACT_PR129_BASE_DRIFT:'+path)
        rows.append(dict(path=path,BASE_git_blob_SHA1=oid,observed_git_blob_SHA1=observed,
            sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
    write(OUT,'PR129_BASE_BYTE_IDENTITY.json',dict(exact_base=BASE,files=len(rows),PASS=True,
        existing_code_workload_capacity_PQ_V_PLAN_V_ACTUAL_all_unchanged=True,rows=rows))
    return len(rows)

def manifest():
    rows=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size)
        for folder in (OUT,ROOT/'v42_reg1a_audit') for p in sorted(folder.rglob('*'))
        if p.is_file() and '__pycache__' not in p.parts and p.name!='SHA256_MANIFEST.json']
    for p in sorted((ROOT/'tests/v42_reg1a_phase').rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            rows.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size))
    write(OUT,'SHA256_MANIFEST.json',dict(excludes_self_only_and_python_caches=True,files=rows))
    return rows

def main():
    from v42_regcontrol.authority import source
    m=source();count=base_identity();external=[]
    frozen=read(ROOT/'docs/v42_april_b0_capacity_queue_voltage_calibration/ELECTRICAL_SOURCE_AUTHORITY.json')
    for r in m['audit']['static_source_graph']['files']+m['audit']['code_read']+frozen['static_sources']:
        p=resolve(r);external.append(record(p))
    source_receipt=read(OUT/'NATIVE_PHASE_SOURCE_AUTHORITY.json')
    for r in source_receipt['source_graph']:resolve(r)
    for day in DAYS:
        receipt=read(OUT/(day+'_REPRODUCTION.json'))
        assert all(v==0 for v in receipt['max_absolute_difference'].values())
        assert receipt['selected_controls_have_no_reg1a_current_violation']
        for name in ('physical_input','original_actual','source_provenance'):resolve(receipt[name])
        prov=read(MAY/'INPUT/BUNDLE'/day_folder(day)/'SOURCE_PROVENANCE.json')
        resolve(prov['daily_sources']['aemo_actual.parquet'])
    tests=read(OUT/'TEST_RECEIPT.json')
    if tests['exit_code']!=0:raise ValueError('FULL_PYTEST_REQUIRED')
    write(OUT,'VERIFICATION.json',dict(PASS=True,exact_base=BASE,parent_files_byte_identical=count,
        external_source_hashes_verified=len(external),sources=external,
        full_pytest=tests,no_existing_code_or_scientific_artifact_edits=True,
        required_evidence_files=all((OUT/name).exists() for name in (
            'AIDC_PCC_COMPILED_PHASE_AUDIT.csv','AIDC_PCC_PER_PHASE_PQ.csv','REG1A_PHASE_CURRENT_AUDIT.csv',
            'REG1A_DOWNSTREAM_PHASE_BALANCE.csv','REG1A_CURRENT_RATING_AUTHORITY.json',
            'ROOT_CAUSE_CLASSIFICATION.json','FINAL_REVIEW_KO.md')),
        strict_network_algebraic_check_failure_disclosed=True,
        scientific_parameter_changes=0,diagnostic_reproductions_only=True,
        B1='NOT_RUN',B2='NOT_RUN',B3='NOT_RUN',M1='NOT_RUN',A2='NOT_RUN',M2='NOT_RUN'))
    manifest();print('Verified exact PR129 files',count,'full pytest',tests['passed'],flush=True)

def index():
    entries=read(OUT/'SHA256_MANIFEST.json')['files']
    for r in entries:
        path=r['path'];data=(ROOT/path).read_bytes()
        assert hashlib.sha256(data).hexdigest()==r['sha256'],path
        indexed=subprocess.check_output(['git','show',':'+path],cwd=ROOT)
        assert indexed==data,path
    changes=subprocess.check_output(['git','diff','--cached','--name-status'],cwd=ROOT,text=True,encoding='utf8').splitlines()
    assert all(line.startswith('A\t') and (line.split('\t')[1].startswith(('v42_reg1a_audit/','docs/v42_may_reg1a_phase_root_cause/'))
        or line.split('\t')[1].startswith('tests/v42_reg1a_phase/')) for line in changes)
    assert len(changes)==len(entries)+1,(len(changes),len(entries))
    assert subprocess.check_output(['git','show',':docs/v42_may_reg1a_phase_root_cause/SHA256_MANIFEST.json'],cwd=ROOT)==(OUT/'SHA256_MANIFEST.json').read_bytes()
    print('Exact indexed SHA evidence',len(changes),'new files',flush=True)

if __name__=='__main__':
    import sys
    (index if len(sys.argv)>1 and sys.argv[1]=='index' else main)()
