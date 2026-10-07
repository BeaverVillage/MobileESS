"""Continue only open fixed-assignment LPs using qualified parent basis reuse."""
import gzip,pickle,subprocess,zipfile,hashlib,traceback
from pathlib import Path
from fractions import Fraction
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_lexcases.policy import ROOT,OUT,STATIC
from v42_a_stage_cg.native import Native as CGNative
from v42_a_stage_cg.execution import verify as cg_verify
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_bnp.budget import Allocation
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_optimality_certificate
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_practical.physical import Physical
from v42_a_stage_lexfull.runner import objective_value
from .query import fixed_query

def verify():
    f=read(OUT/'PRIMAL_DUAL_SOURCE_FREEZE.json')
    if not f.get('PASS'):raise PermissionError('PRIMAL_DUAL_SOURCE_REQUIRED')
    for p,h in f['execution_sources'].items():
        if sha(p)!=h:raise PermissionError('PRIMAL_DUAL_SOURCE_DRIFT:'+p)
    for r in f['gate_receipts']:
        if record(r['path'])!=r or not read(r['path']).get('PASS'):raise PermissionError('PRIMAL_DUAL_GATE_DRIFT')
    cg_verify();return f

def freeze():
    if (OUT/'PRIMAL_DUAL_SOURCE_FREEZE.json').exists():raise PermissionError('PRIMAL_DUAL_SOURCE_ALREADY_FROZEN')
    parent=cg_verify();old=read(OUT/'PRIMAL_REPAIR_V2_RESULT.json');budget=Budget();budget.remaining()
    if old.get('accepted'):raise PermissionError('SHIFT_ALREADY_CERTIFIED_SKIP_REPAIR_CONTINUATION')
    sources=[Path(r['path']) for r in parent['source_files']]+[Path(__file__),ROOT/'v42_a_stage_primal/query.py']
    sources=list(dict.fromkeys(p.resolve() for p in sources));head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tree=subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True);blobs={l.split('\t',1)[1]:l.split()[2] for l in tree.splitlines()}
    for p in sources:
        if p.is_relative_to(ROOT):
            b=p.read_bytes();h=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest();rel=p.relative_to(ROOT).as_posix()
            if h!=blobs.get(rel):h=subprocess.check_output(['git','hash-object',str(p)],cwd=ROOT,text=True).strip()
            if h!=blobs.get(rel):raise PermissionError('UNCOMMITTED_PRIMAL_DUAL_SOURCE:'+rel)
    gates=[Path(r['path']) for r in parent['gate_receipts']]+[OUT/'PRIMAL_PARENT_BASIS_QUALIFICATION.json',OUT/'PRIMAL_DUAL_ENTRY_GATE.json']
    archive=STATIC/('PRIMAL_DUAL_EXECUTED_SOURCE_'+head+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(sources):z.write(p,'repo/'+p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name)
    atomic(OUT/'PRIMAL_DUAL_SOURCE_FREEZE.json',dict(PASS=True,git_head=head,execution_sources={str(p):sha(p) for p in sources},
        source_files=[record(p) for p in sources],source_archive=record(archive),gate_receipts=[record(p) for p in gates],deadline=budget.record,
        native_processes=1,Threads=1,component_allocation_seconds=180,architecture_change='QUALIFIED_PARENT_BASIS_DUAL_SIMPLEX_REUSE'))
    verify();print('PRIMAL_DUAL_SOURCE_FROZEN',head,len(sources),flush=True)

class Native(CGNative):
    def __init__(self,budget):super().__init__(budget);self.freeze_path=OUT/'PRIMAL_DUAL_SOURCE_FREEZE.json'
    def verify(self):return verify()

def run():
    verify();budget=Budget();budget.remaining();old=read(OUT/'PRIMAL_REPAIR_V2_RESULT.json')
    if (OUT/'PRIMAL_DUAL_STARTED.json').exists():raise PermissionError('PRIMAL_DUAL_ALREADY_STARTED')
    atomic(OUT/'PRIMAL_DUAL_STARTED.json',dict(PASS=True,source=record(OUT/'PRIMAL_DUAL_SOURCE_FREEZE.json'),deadline=budget.record))
    build=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    s=p['snapshot'];physical=Physical(p['state'],s);prep=read(OUT/'PRIMAL_PROPOSALS.json');x=np.load(prep['preserved_incumbent']['path'])['X']
    if not physical.verify(x)['PASS']:raise ValueError('PRESERVED_ORIGINAL_PRIMAL_REQUIRED')
    basis=read(OUT/'PRIMAL_PARENT_BASIS_QUALIFICATION.json')['parent_basis']
    if record(basis['path'])!=basis:raise ValueError('QUALIFIED_BASIS_BYTE_DRIFT')
    br=np.load(basis['path']);vb=br['VBasis'];cb=br['CBasis']
    inc=read(OUT/'VALIDATED_INTEGER_INCUMBENT.json');mig=read(OUT/'P2_MIGRATION_PROBE_RESULT.json')
    locked,_=rebuild_locked_snapshot(s,[LexLock('rho',Fraction(inc['exact_UB']),True,sha(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),LexLock('migration_count',Fraction(0),True,mig['certificate']['sha256'])])
    unknown=[a['candidate'] for a in old['attempts'] if a['native_status']!=3];native=Native(budget);attempts=[];result=dict(accepted=False,primal_only=True,open_queries=unknown)
    try:
        for i in unknown:
            if budget.remaining()<=360:raise RuntimeError('FINAL_PRIMARY_CONTINUATION_RESERVE')
            f=OUT/'M19/P2/PRIMAL_DUAL'/('C'+str(i));f.mkdir(parents=True,exist_ok=True);q,proof=fixed_query(locked,x,prep['proposals'][i])
            oldid=read(OUT/'M19/P2/PRIMAL_REPAIR_V2'/('C'+str(i))/'MODEL_IDENTITY.json')
            if q.fingerprint()!=oldid['original_snapshot_sha256']:raise ValueError('OPEN_QUERY_MUST_MATCH_OLD_EXACT_QUERY')
            atomic(f/'PRIMAL_QUERY_PROOF.json',proof);native.warm_point=None;native.warm_basis=(vb,cb);native.budget=Allocation(180)
            try:r,raw=native.solve(q,f,'NODE_LP')
            finally:native.budget=budget
            attempt=dict(candidate=i,status=r['status'],accepted=False,prior_open_query=record(OUT/'M19/P2/PRIMAL_REPAIR_V2'/('C'+str(i))/'NATIVE_RESULT.json'))
            if 'X' in raw:
                y=raw['X'];rows=primal_replay(q,y);integ=np.max(abs(y[s.vtypes!='C']-np.rint(y[s.vtypes!='C'])))<=1e-5;phys=dict(PASS=False)
                if rows['PASS'] and integ:
                    try:phys=physical.verify(y)
                    except Exception as e:phys=dict(PASS=False,reason=repr(e))
                atomic(f/'RAW_QUERY_REPLAY.json',rows);atomic(f/'FULL_ORIGINAL_A1_REPLAY.json',phys);val=float(objective_value(s,y,'shift_magnitude'))
                if rows['PASS'] and integ and phys['PASS'] and abs(val-948)<=1e-5:
                    path=STATIC/f.relative_to(OUT)/'VALIDATED_POINT.npz';np.savez_compressed(path,X=y)
                    cert=integer_optimality_certificate('shift_magnitude',val,948,bound_independently_validated=True,primal_independently_validated=True,integrality_proven=True)
                    cert.update(prior_full_domain_bound=record(OUT/'INTERRUPTED_BOUND_RECOVERY.json'),repair_query_bound_used=False,independent_rational_MIP_dual_certificate=False)
                    if not cert['PASS']:raise ValueError('SHIFT_CERTIFICATE_REQUIRED')
                    cp=f/'INTEGER_CERTIFICATE.json';atomic(cp,cert);result.update(accepted=True,component='shift_magnitude',value=948,valid_LB=948,certificate=record(cp),point=record(path));attempt['accepted']=True
            attempts.append(attempt);atomic(OUT/'PRIMAL_DUAL_CHECKPOINT.json',dict(attempts=attempts,result=result,deadline=budget.record));print('PRIMAL_DUAL',i,attempt['status'],attempt['accepted'],flush=True)
            if result['accepted']:break
    except Exception as e:result.update(stop_reason=repr(e),traceback=traceback.format_exc())
    finally:
        result.update(attempts=attempts,native_seconds=native.native_seconds,Work=sum(c.get('Work') or 0 for c in native.calls),peak_RSS_bytes=max((c.get('peak_RSS_bytes') or 0 for c in native.calls),default=0))
        atomic(OUT/'PRIMAL_DUAL_NATIVE_CALLS.json',dict(calls=native.calls));atomic(OUT/'PRIMAL_DUAL_RESULT.json',result);print('PRIMAL_DUAL_RESULT',result['accepted'],result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':
    import sys
    freeze() if len(sys.argv)>1 and sys.argv[1]=='freeze' else run()
