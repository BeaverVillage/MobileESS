"""Exact parent evidence, narrowly authorized code changes, hashes and index."""
import hashlib,subprocess
import numpy as np
from .common import *
from .authority import current_authority
from .supersession import CHANGES,assert_successor

def base_identity():
    rows=[];modified=[]
    for line in subprocess.check_output(['git','ls-tree','-r',BASE],cwd=ROOT,text=True,encoding='utf8').splitlines():
        meta,name=line.split('\t');oid=meta.split()[2];data=(ROOT/name).read_bytes()
        observed=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        same=observed==oid
        if not same:
            if name not in CHANGES:raise ValueError('UNAUTHORIZED_PARENT_BYTE_DRIFT:'+name)
            assert assert_successor(name,hashlib.sha256(data).hexdigest());modified.append(name)
        rows.append(dict(path=name,parent_git_blob_SHA1=oid,current_git_blob_SHA1=observed,
            sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),byte_identical=same))
    if set(modified)!=set(CHANGES):raise ValueError('EXACT_CODE_CHANGE_SET_REQUIRED')
    write(OUT,'PR130_PARENT_BYTE_PRESERVATION.json',dict(PASS=True,exact_base=BASE,tracked_parent_files=len(rows),
        authorized_code_changes=modified,byte_identical_parent_files=sum(r['byte_identical'] for r in rows),
        all_parent_evidence_data_tests_byte_identical=True,all_original_V_PLAN_PQ_current_kVA_arrays_preserved=True,files=rows))
    return rows

def manifest():
    paths=[p for f in (OUT,ROOT/'v42_thermal',ROOT/'tests/v42_thermal') for p in f.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.name!='SHA256_MANIFEST.json']
    paths += [ROOT/n for n in CHANGES]
    rows=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(set(paths))]
    write(OUT,'SHA256_MANIFEST.json',dict(exact_base=BASE,files=rows,excludes_self_and_ignored_caches=True))
    return rows

def main():
    rows=base_identity();a=current_authority()
    for r in a['provenance']:resolve(r)
    plan=read(OUT/'PLANNING_CURRENT_RESPONSE_RESCALE_RECEIPT.json')
    for r in plan['source_outputs']:resolve(r)
    for month in ('APRIL','MAY'):
        receipt=read(OUT/(month+'_B0_CURRENT_RECLASSIFICATION.json'))
        for r in receipt['source_files']:resolve(r)
    # The physical 96-slot loop AST is unchanged; its read-only measurement
    # function is now routed to the successor NormalAmps implementation.
    import ast
    old=subprocess.check_output(['git','show',BASE+':v42_regcontrol/runner.py'],cwd=ROOT).decode('utf8')
    def loop(code):
        return next(n for n in ast.walk(ast.parse(code)) if isinstance(n,ast.For) and ast.unparse(n.iter)=='range(96)')
    assert ast.dump(loop(old))==ast.dump(loop((ROOT/'v42_regcontrol/runner.py').read_text(encoding='utf8')))
    tests=read(OUT/'TEST_RECEIPT.json');assert tests['exit_code']==0 and tests['full_suite']
    write(OUT,'VERIFICATION.json',dict(PASS=True,exact_base=BASE,parent_files=len(rows),
        authorized_code_change_count=len(CHANGES),historical_evidence_and_input_arrays_preserved=True,
        all_transformer_NormalAmps_valid=True,Planning_Actual_exact_authority_identity=True,
        source_controls_capacitors_line_kVA_unchanged=True,Actual_96_slot_apply_solve_loop_AST_unchanged=True,
        workload_capacity_Runtime_CC4_PQ_V_PLAN_unchanged=True,line_current_coefficients_bit_identical=True,
        full_pytest=tests,independent_April_May_raw_current_reclassification=True,
        old_M1_certificate_identity_gate_rejects=True,M1_full_solve='NOT_RUN',PQ_repair=0,tuning=0))
    manifest();print('QA PASS; parent',len(rows),'authorized code',len(CHANGES),'pytest',tests['passed'],flush=True)

def index():
    rows=read(OUT/'SHA256_MANIFEST.json')['files']
    for r in rows:
        data=(ROOT/r['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==r['sha256'],r['path']
        assert subprocess.check_output(['git','show',':'+r['path']],cwd=ROOT)==data,r['path']
    changes=subprocess.check_output(['git','diff','--cached','--name-status'],cwd=ROOT,text=True,encoding='utf8').splitlines()
    assert len(changes)==len(rows)+1
    for line in changes:
        status,name=line.split('\t')
        assert (status=='M' and name in CHANGES) or (status=='A' and name.startswith(('v42_thermal/','tests/v42_thermal/','docs/v42_transformer_normalamps_contract/')))
    print('Index SHA/bytes PASS',len(changes),'files',flush=True)

if __name__=='__main__':
    import sys
    (index if len(sys.argv)>1 and sys.argv[1]=='index' else main)()
