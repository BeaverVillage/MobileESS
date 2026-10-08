"""Exact original-row invariant histogram swaps, followed by physical replay.

The old scientific matrix and point remain immutable. No native solve, domain
bound, candidate deletion, or approximate coupling cancellation is used.
"""
import gzip,pickle,zipfile,subprocess
from pathlib import Path
from fractions import Fraction
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_lexcases.policy import ROOT,OUT,STATIC
from v42_a_stage_practical.physical import Physical
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_optimality_certificate
from v42_a_stage_lexfull.runner import objective_value
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_compact_rowgen.resources import sample
from .freeze import verify as parent_verify

def exact_null(matrix,changes):
    sub=matrix[:,list(changes)].tocoo();values={}
    for r,c,v in zip(sub.row,sub.col,sub.data):values[int(r)]=values.get(int(r),Fraction(0))+Fraction(float(v))*changes[list(changes)[c]]
    return all(v==0 for v in values.values())

def enumerate_swaps(state,s,x,target):
    obj=s.objective('shift_magnitude').coefficients();need=objective_value(s,x,'shift_magnitude')-Fraction(target)
    groups={};answer=[];seen=set()
    for u in state['reference_descriptor']['units']:
        if not u.get('stay_count') or u.get('optional') or u.get('retained_mixed_flow'):continue
        job=state['data'][1][u['uid']];ys=u['v']['y']
        for (site,start),e in ys.items():
            if e[0]=='v' and s.vtypes[e[1]] in ('B','I') and x[e[1]]>=1-1e-5:
                groups.setdefault((site,job.gpu,job.service_slots),[]).append((u,int(start),int(e[1])))
    for group,occupied in sorted(groups.items()):
        site,gpu,duration=group
        for i,(a,sa,ja) in enumerate(occupied):
            for b,sb,jb in occupied[i+1:]:
                if a['class_key']==b['class_key'] or sa==sb:continue
                ea=a['v']['y'].get((site,sb));eb=b['v']['y'].get((site,sa))
                if ea is None or eb is None or ea[0]!='v' or eb[0]!='v':continue
                ka,kb=int(ea[1]),int(eb[1]);delta={ja:-1,jb:-1,ka:1,kb:1}
                if len(delta)!=4 or any(s.vtypes[j] not in ('B','I') or x[j]+v<s.lower[j] or x[j]+v>s.upper[j] for j,v in delta.items()):continue
                change=sum((obj.get(j,Fraction(0))*v for j,v in delta.items()),Fraction(0))
                if change!=-need:continue
                ident=tuple(sorted(delta.items()))
                if ident in seen:continue
                seen.add(ident);answer.append(dict(changes=delta,class_ids=[a['class_key'],b['class_key']],site=site,GPU=gpu,
                    service_slots=duration,starts=[sa,sb],exact_shift_delta=str(change),scientific_feasibility_claimed=False))
    return sorted(answer,key=lambda p:tuple(sorted(p['changes'].items())))

def run():
    parent=parent_verify();budget=Budget();budget.remaining();resources=sample()
    if resources['unsafe'] or resources['available_RAM_bytes']<4*1024**3:raise RuntimeError('STATIC_SWAP_MEMORY_RESERVE_REQUIRED')
    if (OUT/'EXACT_SWAP_RESULT.json').exists():raise PermissionError('EXACT_SWAP_ALREADY_EXECUTED')
    source=Path(__file__);head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    blob=subprocess.check_output(['git','hash-object',str(source)],cwd=ROOT,text=True).strip()
    tracked=subprocess.check_output(['git','rev-parse',head+':'+source.relative_to(ROOT).as_posix()],cwd=ROOT,text=True).strip()
    if blob!=tracked:raise PermissionError('UNCOMMITTED_EXACT_SWAP_SOURCE')
    archive=STATIC/('EXACT_SWAP_STATIC_SOURCE_'+head+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:z.write(source,'repo/'+source.relative_to(ROOT).as_posix())
    atomic(OUT/'EXACT_SWAP_SOURCE.json',dict(PASS=True,git_head=head,source=record(source),source_archive=record(archive),
        inherited_dependencies=record(OUT/'PRIMAL_V2_SOURCE_FREEZE.json'),native_solve_calls=0,deadline=budget.record))
    build=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')
    if record(build['state']['path'])!=build['state']:raise ValueError('ORIGINAL_FULL_STATE_DRIFT')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    s=p['snapshot'];state=p['state'];oldpoint=read(OUT/'P2_CASE_CHECKPOINT.json')['incumbent']['point']
    if record(oldpoint['path'])!=oldpoint:raise ValueError('PRESERVED_POINT_DRIFT')
    x=np.load(oldpoint['path'])['X'];physical=Physical(state,s)
    if not physical.verify(x)['PASS']:raise ValueError('PREVIOUS_FULL_PHYSICAL_POINT_REQUIRED')
    inc=read(OUT/'VALIDATED_INTEGER_INCUMBENT.json');mig=read(OUT/'P2_MIGRATION_PROBE_RESULT.json')
    locks=[LexLock('rho',Fraction(inc['exact_UB']),True,sha(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),
        LexLock('migration_count',Fraction(0),True,mig['certificate']['sha256'])]
    locked,_=rebuild_locked_snapshot(s,locks);candidates=enumerate_swaps(state,s,x,948);checked=[];result=dict(accepted=False,native_solve_calls=0,proposed=len(candidates))
    for i,c in enumerate(candidates):
        budget.remaining();delta=c['changes'];null=exact_null(locked.matrix,delta);r=dict(proposal=c,exact_all_original_rows_null=null)
        if null:
            y=x.copy()
            for j,v in delta.items():y[j]+=v
            rows=primal_replay(locked,y);integral=np.max(abs(y[s.vtypes!='C']-np.rint(y[s.vtypes!='C'])))<=1e-5
            phys=dict(PASS=False)
            if rows['PASS'] and integral:
                try:phys=physical.verify(y)
                except Exception as e:phys=dict(PASS=False,reason=repr(e))
            r.update(rows=rows,physical=phys,integral=bool(integral))
            if rows['PASS'] and phys['PASS'] and integral:
                val=objective_value(s,y,'shift_magnitude');cert=integer_optimality_certificate('shift_magnitude',float(val),948.,
                    bound_independently_validated=True,primal_independently_validated=True,integrality_proven=True)
                cert.update(scope='FULL_SCIENTIFIC_RELEVANT_INTEGER_DOMAIN_UNDER_CERTIFIED_PRIOR_LOCKS',
                    prior_full_domain_bound=record(OUT/'INTERRUPTED_BOUND_RECOVERY.json'),exact_row_null_transfer=True,
                    native_solve_calls=0,independent_rational_MIP_dual_certificate=False)
                if not cert['PASS']:raise ValueError('EXACT_SWAP_PRIMAL_DOES_NOT_CLOSE_SHIFT')
                folder=OUT/'M19/P2/EXACT_SWAP'/('C'+str(i));folder.mkdir(parents=True,exist_ok=True)
                atomic(folder/'FULL_ORIGINAL_A1_REPLAY.json',phys);atomic(folder/'LOCKED_ROWS_REPLAY.json',rows)
                cp=folder/'INTEGER_CERTIFICATE.json';atomic(cp,cert);path=STATIC/'EXACT_SWAP_VALIDATED_POINT.npz';np.savez_compressed(path,X=y)
                result.update(accepted=True,component='shift_magnitude',value=cert['incumbent_integer'],valid_LB=948.,
                    certificate=record(cp),point=record(path),rho=float(objective_value(s,y,'rho')),
                    prestart_relocation=float(objective_value(s,y,'prestart_relocation')))
        checked.append(r)
        if result['accepted']:break
    result.update(checked=checked,source=record(OUT/'EXACT_SWAP_SOURCE.json'),wall_accounted=budget.accounted(),deadline=budget.record)
    atomic(OUT/'EXACT_SWAP_RESULT.json',result);print('EXACT_SWAP_RESULT',result['accepted'],len(candidates),flush=True)
    return result
if __name__=='__main__':run()
