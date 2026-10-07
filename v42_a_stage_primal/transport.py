"""Primal-only optimization within the exact original-row histogram fiber."""
import gzip,pickle,subprocess,zipfile
from pathlib import Path
from fractions import Fraction
import numpy as np
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_lexcases.policy import ROOT,OUT,STATIC
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_compact_rowgen.resources import sample
from v42_a_stage_practical.physical import Physical
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot,integer_optimality_certificate
from v42_a_stage_lexfull.runner import objective_value
from .mincost import transport
from .swap import exact_null
from .freeze import verify as parent_verify

def optimize(state,s,x,budget_check):
    groups={};obj=s.objective('shift_magnitude').coefficients();changes={};proofs=[]
    for u in state['reference_descriptor']['units']:
        if not u.get('stay_count') or u.get('optional') or u.get('retained_mixed_flow'):continue
        job=state['data'][1][u['uid']]
        for (site,start),e in u['v']['y'].items():
            if e[0]!='v':continue
            j=int(e[1])
            if s.vtypes[j] not in ('B','I') or s.lower[j]!=0 or not np.isfinite(s.upper[j]) or s.upper[j]!=np.rint(s.upper[j]) or x[j]!=np.rint(x[j]):raise ValueError('EXACT_NATIVE_HISTOGRAM_BOX_AND_INTEGER_POINT_REQUIRED')
            c=obj.get(j,Fraction(0))
            if c.denominator!=1 or c<0:raise ValueError('ORIGINAL_NONNEGATIVE_INTEGER_SHIFT_REQUIRED')
            groups.setdefault((site,job.gpu,job.service_slots),{}).setdefault(u['class_key'],{})[int(start)]=(j,int(s.upper[j]),int(c))
    for group,classes in sorted(groups.items()):
        budget_check();supply={c:sum(int(x[j]) for j,cap,cost in options.values()) for c,options in classes.items()}
        supply={c:n for c,n in supply.items() if n};demand={}
        for c in supply:
            for t,(j,cap,cost) in classes[c].items():demand[t]=demand.get(t,0)+int(x[j])
        demand={t:n for t,n in demand.items() if n}
        if len(supply)<2 or len(demand)<2:continue
        edges={(c,t):(cap,cost) for c in supply for t,(j,cap,cost) in classes[c].items() if t in demand}
        flow,newcost=transport(supply,demand,edges);oldcost=sum(int(x[j])*cost for c in supply for j,cap,cost in classes[c].values())
        if newcost>oldcost:raise ValueError('OLD_ASSIGNMENT_FEASIBLE_TRANSPORT_CANNOT_WORSEN')
        if newcost==oldcost:continue
        delta={}
        for c in supply:
            for t,(j,cap,cost) in classes[c].items():
                d=flow.get((c,t),0)-int(x[j])
                if d:delta[j]=d
        null=exact_null(s.matrix,delta);proofs.append(dict(group=group,old_cost=oldcost,new_cost=newcost,exact_all_original_rows_null=null,changes=delta))
        if null:changes.update(delta)
    y=x.copy()
    for j,d in changes.items():y[j]+=d
    return y,dict(PASS=True,primal_query_only=True,conditional_transport_bound_not_global=True,
        groups=proofs,changes=changes,exact_original_all_row_null=exact_null(s.matrix,changes),integer_arithmetic=True,native_solve_calls=0)

def run():
    parent_verify();budget=Budget();budget.remaining();r=sample()
    if r['unsafe'] or r['available_RAM_bytes']<8*1024**3:raise RuntimeError('STATIC_TRANSPORT_RESOURCE_RESERVE_REQUIRED')
    if (OUT/'EXACT_TRANSPORT_RESULT.json').exists():raise PermissionError('EXACT_TRANSPORT_ALREADY_EXECUTED')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();sources=[Path(__file__),ROOT/'v42_a_stage_primal/mincost.py',ROOT/'v42_a_stage_primal/swap.py',ROOT/'tests/test_v42_a_stage_integer_transport.py']
    archive=STATIC/('EXACT_TRANSPORT_STATIC_SOURCE_'+head+'.zip')
    for p in sources:
        if subprocess.check_output(['git','hash-object',str(p)],cwd=ROOT,text=True).strip()!=subprocess.check_output(['git','rev-parse',head+':'+p.relative_to(ROOT).as_posix()],cwd=ROOT,text=True).strip():raise PermissionError('UNCOMMITTED_TRANSPORT_SOURCE')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sources:z.write(p,'repo/'+p.relative_to(ROOT).as_posix())
    atomic(OUT/'EXACT_TRANSPORT_SOURCE.json',dict(PASS=True,git_head=head,sources=[record(p) for p in sources],source_archive=record(archive),
        inherited_dependencies=record(OUT/'PRIMAL_V2_SOURCE_FREEZE.json'),native_solve_calls=0,deadline=budget.record))
    build=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    s=p['snapshot'];state=p['state'];point=read(OUT/'P2_CASE_CHECKPOINT.json')['incumbent']['point'];x=np.load(point['path'])['X'];physical=Physical(state,s)
    if record(build['state']['path'])!=build['state'] or record(point['path'])!=point or not physical.verify(x)['PASS']:raise ValueError('PRESERVED_ORIGINAL_POINT_AND_STATE_REQUIRED')
    y,proof=optimize(state,s,x,budget.remaining);atomic(OUT/'EXACT_TRANSPORT_PROOF.json',proof)
    inc=read(OUT/'VALIDATED_INTEGER_INCUMBENT.json');mig=read(OUT/'P2_MIGRATION_PROBE_RESULT.json')
    locked,_=rebuild_locked_snapshot(s,[LexLock('rho',Fraction(inc['exact_UB']),True,sha(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),LexLock('migration_count',Fraction(0),True,mig['certificate']['sha256'])])
    val=objective_value(s,y,'shift_magnitude');row=primal_replay(locked,y);phys=dict(PASS=False);integral=np.max(abs(y[s.vtypes!='C']-np.rint(y[s.vtypes!='C'])))<=1e-5
    if proof['exact_original_all_row_null'] and row['PASS'] and integral:
        try:phys=physical.verify(y)
        except Exception as e:phys=dict(PASS=False,reason=repr(e))
    accepted=proof['exact_original_all_row_null'] and row['PASS'] and integral and phys['PASS'] and val<objective_value(s,x,'shift_magnitude')
    result=dict(primal_accepted=bool(accepted),shift_certified=False,shift=float(val),old_shift=float(objective_value(s,x,'shift_magnitude')),
        native_solve_calls=0,source=record(OUT/'EXACT_TRANSPORT_SOURCE.json'),proof=record(OUT/'EXACT_TRANSPORT_PROOF.json'),
        row_replay=row,physical=phys,integer_residual_validated=bool(integral),deadline=budget.record)
    if accepted:
        path=STATIC/'EXACT_TRANSPORT_VALIDATED_POINT.npz';np.savez_compressed(path,X=y);result['point']=record(path)
        cert=integer_optimality_certificate('shift_magnitude',float(val),948.,bound_independently_validated=True,primal_independently_validated=True,integrality_proven=True)
        if cert['PASS']:
            cert.update(prior_full_domain_bound=record(OUT/'INTERRUPTED_BOUND_RECOVERY.json'),repair_query_bound_used=False,independent_rational_MIP_dual_certificate=False)
            cp=OUT/'EXACT_TRANSPORT_INTEGER_CERTIFICATE.json';atomic(cp,cert);result.update(shift_certified=True,certificate=record(cp),valid_LB=948.)
    atomic(OUT/'EXACT_TRANSPORT_RESULT.json',result);print('EXACT_TRANSPORT_RESULT',accepted,float(val),result['shift_certified'],flush=True)
    return result
if __name__=='__main__':run()
