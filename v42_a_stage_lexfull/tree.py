"""Deterministic full-finite-domain best-bound LP branching continuation.

All relevant columns and original rows are already present and independently
qualified. Their coverage supplies analytic pricing/separation closure at
every node. Numeric LP bounds are separately replayed by interval arithmetic.
Both children are solved before selecting the next best closed node. Unknown
LP outcomes remain OPEN and cannot support a global bound or pruning.
"""
from dataclasses import replace
from fractions import Fraction
from time import time
import math
import numpy as np
from v42_pr134_b1.common import atomic,record
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention,interval_box_bound
from v42_a_stage_bnp.queue import Queue
from .policy import OUT,STATIC

def continue_tree(native,root,rootraw,rootLB,candidate,incumbent,physical,certificate_upper,folder,integer_snapshot,name):
    from .runner import bound,objective_value
    q=Queue();r=q.add(None);q.close_lp(r.id,Fraction(rootLB),row_closed=True,column_closed=True)
    states={r.id:rootraw};processed=0;last=time();started=time();trace=[];best=candidate;point=incumbent
    integer_cols=np.flatnonzero(integer_snapshot.vtypes!='C')
    def checkpoint():
        atomic(folder/'BEST_BOUND_CHECKPOINT.json',dict(PASS=True,queue=q.document(),incumbent=best,
            valid_global_LB=None if q.global_bound() is None else float(q.global_bound()),processed_nodes=processed,
            source_freeze=record(OUT/'LEX_FULL_SOURCE_FREEZE.json'),deadline=native.budget.record,
            full_row_column_coverage=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),checkpoint_unix=time()))
    def certify_child(child,parentraw):
        lo=root.lower.copy();hi=root.upper.copy()
        for col,kind,v in child.restrictions:
            if kind=='LOWER':lo[col]=max(lo[col],v)
            else:hi[col]=min(hi[col],v)
        cf=folder/'TREE'/('N'+str(child.id));cf.mkdir(parents=True,exist_ok=True)
        if np.any(lo>hi):
            child.status='PRUNED_INFEASIBLE';atomic(cf/'EXACT_BOX_INFEASIBILITY.json',dict(PASS=True,columns=np.flatnonzero(lo>hi).tolist()));return
        s=replace(root,lower=lo,upper=hi);native.warm_point=None
        native.warm_basis=(parentraw['VBasis'],parentraw['CBasis']) if all(k in parentraw for k in ('VBasis','CBasis')) else None
        rec,raw=native.solve(s,cf,'NODE_LP')
        if rec['status']!=2 or not all(a in raw for a in ('X','Pi','RC')):
            if rec['status']==3 and 'FarkasDual' in raw:
                y=raw['FarkasDual'];legal=not np.any((s.senses=='<')&(y<0)) and not np.any((s.senses=='>')&(y>0))
                proof=interval_box_bound(s.matrix,np.zeros(s.matrix.shape[1]),-y,s.lower,np.minimum(hi,certificate_upper),s.rhs) if legal else None
                atomic(cf/'INDEPENDENT_INFEASIBILITY.json',dict(PASS=proof is not None and proof>0,contradiction_LB=proof))
                if proof is not None and proof>0:child.status='PRUNED_INFEASIBLE';return
            raise RuntimeError('UNRESOLVED_NODE_NOT_PRUNED:'+str(child.id))
        replay=primal_replay(s,raw['X']);sign=verify_sign_convention(s,raw['Pi'],raw['RC'])
        L=bound(s,raw,np.minimum(hi,certificate_upper)) if replay['PASS'] and sign['PASS'] else None
        atomic(cf/'INDEPENDENT_NODE_CLOSURE.json',dict(PASS=L is not None,valid_LB=L,rows=replay,sign=sign,
            full_original_rows_present=True,full_relevant_domain_present=True,branch_restrictions=child.restrictions))
        if L is None:raise RuntimeError('NODE_LB_NOT_VALID:'+str(child.id))
        q.close_lp(child.id,Fraction(L),row_closed=True,column_closed=True);states[child.id]=raw
    try:
        while True:
            native.remaining();L=q.global_bound()
            if L is not None and math.ceil(float(L)-1e-6)>=round(best['value']):break
            node=q.best()
            if node is None:
                if all(n.status in ('BRANCHED','PRUNED_INFEASIBLE','PRUNED_BOUND','INTEGER_FEASIBLE') for n in q.nodes.values()):
                    L=Fraction(round(best['value']));break
                raise RuntimeError('OPEN_NODE_MISSING_VALID_BOUND')
            raw=states[node.id];x=raw['X'];processed+=1
            if math.ceil(float(Fraction(node.lower_bound))-1e-6)>=round(best['value']):node.status='PRUNED_BOUND';continue
            distance=abs(x[integer_cols]-np.rint(x[integer_cols]));fractional=integer_cols[distance>1e-5]
            if not len(fractional):
                replay=physical.verify(x);atomic(folder/'TREE'/('N'+str(node.id))/'FULL_A1_PRIMAL_REPLAY.json',replay)
                if not replay['PASS']:raise RuntimeError('INTEGER_RAW_POINT_FAILS_FULL_PHYSICS')
                val=float(objective_value(integer_snapshot,x,name));node.status='INTEGER_FEASIBLE'
                if val<best['value']:
                    path=STATIC/'M19/P2/TREE_INTEGERS'/name/('N'+str(node.id)+'.npz');path.parent.mkdir(parents=True,exist_ok=True)
                    np.savez_compressed(path,X=x);best=dict(value=val,point=record(path));point=x
            else:
                col=min(map(int,fractional),key=lambda j:(-min(x[j]-math.floor(x[j]),math.ceil(x[j])-x[j]),j))
                children=q.split(node.id,col,Fraction(float(x[col])))
                checkpoint()
                for child in children:certify_child(child,raw)
            trace.append(dict(node=node.id,unix=time(),valid_LB=None if q.global_bound() is None else float(q.global_bound()),UB=best['value']))
            if processed%10==0 or time()-last>=300:checkpoint();last=time()
    finally:
        checkpoint();atomic(folder/'BEST_BOUND_TRACE.json',dict(trace=trace,processed_nodes=processed,generated_nodes=len(q.nodes),
            elapsed_seconds=time()-started,nodes_per_hour=processed*3600/max(time()-started,1e-9)))
    return dict(candidate=best,point=point,valid_LB=float(L),processed_nodes=processed,queue=q.document())
