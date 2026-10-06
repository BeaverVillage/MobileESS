"""Opt-in development adapter: early exhaustive original-space branching.

No root closure requirement. Restricted infeasibility is inconclusive, never a
fathoming proof. Unfinished RMP objectives and restricted MIP bounds are not LBs.
"""
from pathlib import Path
from dataclasses import asdict
from types import SimpleNamespace
from fractions import Fraction as F
import time,json,hashlib,subprocess,os,threading
import numpy as np
import psutil
import gurobipy as gp
from scipy import sparse
from .state import Tree,NodeResult,BranchDecision
from .adapter import native_projections
from v42_degen.identity import inputs
from v42_dw_root.partition import axes
from v42_dw_root.models import Block,hash_column
from v42_dw_resume.audit import Block as CheckedBlock,prototypes,corrected_rows,pure_binary_equalities
from v42_m_stage_root.dual_authority import capture
from v42_m_stage_root.conservative_authority import numerical_zero_sign,free_rc_consistency
from v42_dw_bound.certificate import global_dual,corrected
from v42_disjunctive.certificate import down
from revalidate_rmp43 import canonical_rebuild
from run_restricted_1841 import ROOT,OUT,RAW,read,write,sha,pool_point

def column_key(h):
    return str(int(h['MESS'][-2:])-1)+':'+h['column_SHA']

class FileRegistry:
    """Immutable compressed column references; no dense coupling tuple copies."""
    def __init__(self,pool,axis):
        self.columns={};self.axis=axis
        for h in pool:
            key=column_key(h);self.columns[key]=SimpleNamespace(mess=int(h['MESS'][-2:])-1,h=h,sha=h['column_SHA'])
    def point(self,key):return pool_point(self.columns[key].h)
    def partition(self,keys,decisions):
        active=[];inactive=[]
        for key in keys:
            m=self.columns[key].mess;ds=[d for d in decisions if d.variable.mess==m]
            good=not ds or all(d.compatible(m,self.point(key)) for d in ds)
            (active if good else inactive).append(key)
        return tuple(active),tuple(inactive)

class FullScaleEarlyBAP:
    def __init__(self,wall_cap=600.):
        self.start=time.perf_counter();self.deadline=self.start+wall_cap
        self.native_spent=0.;self.calls=[];self.prices=[];self.trajectory=[];self.telemetry=[];self.last_sample=0.
        self.A,self.d,self.B,self.e,*_=inputs();self.owner,self.row_owner=axes()
        self.gcols=np.flatnonzero(self.owner<0);self.grows=np.flatnonzero(self.row_owner<0)
        with np.load(ROOT/'docs/v42_m1_exact_dw_cg_root_pilot/DW_NATIVE_ROW_NAMES.npz') as z:self.native=z['names']
        self.original=prototypes(self.B,self.e,self.owner,self.row_owner,self.native)
        self.pool=read(ROOT/'docs/v42_m_stage_exact_completion/DW_CHECKPOINT_LATEST.json')['pool']
        self.registry=FileRegistry(self.pool,self.owner)
        self.tree=Tree(self.registry,tuple(column_key(h) for h in self.pool),tolerance=1e-8,allow_early_branching=True)
        gate=read(OUT/'certificate/SPLIT_DUAL_GATES.json');assert gate['EXACT_DUAL_AUTHORITY_FOR_BAP']
        self.floor=gate['current_certified_conservative_global_LB']
        self.tree.nodes[0].lower_bound=self.floor
        self.tree.nodes[0].bound_certificate=dict(PASS=True,node_id=0,source='frozen inherited/full-domain conservative certificate',LB=self.floor)
        rim=read(OUT/('RESTRICTED_INCUMBENT_SEARCH_RESULT.json' if (OUT/'RESTRICTED_INCUMBENT_SEARCH_RESULT.json').exists() else 'RESTRICTED_INTEGER_MASTER_RESULT.json'));assert rim['integer_UB'] is not None
        self.tree.incumbent=dict(objective=rim['integer_UB'],node_id=-1,validation=rim['independent_audit'])
        self.projections=native_projections(self.original)
        with np.load(RAW) as z:self.rootpoint=z['point'].copy()
        self.root_pending=True;self.blocks={};self.new=[]
        self.model,self.v,self.meta=canonical_rebuild(RAW)
        self.basevars=self.model.getVars();self.constraints=self.model.getConstrs();self.offset=len(self.gcols)
        source=ROOT/'docs/v42_m1_dw_certified_dual_bound/PROVEN_COORDINATE_ENCLOSURES.npz'
        assert sha(source)==read(source.with_name('COORDINATE_ENCLOSURE_PROOF.json'))['artifact_SHA']
        with np.load(source) as z:self.lo=z['lower'];self.hi=z['upper']
        self.global_A=self.B[self.grows][:,self.gcols]
        self.global_d=dict(objective=self.e['objective'][self.gcols],constant=self.e['constant'],rhs=self.e['rhs'][self.grows],sense=self.e['sense'][self.grows])
    def remaining(self):return max(0.,self.deadline-time.perf_counter())
    def sample(self):
        now=time.perf_counter()
        if now-self.last_sample>=1:
            self.last_sample=now;vm=psutil.virtual_memory();pm=psutil.Process().memory_info()
            self.telemetry.append(dict(wall=now-self.start,RAM_available=vm.available,RSS=pm.rss,commit=getattr(pm,'pagefile',None)))
    def optimize(self,m,label,cap):
        if self.remaining()<=0:raise TimeoutError('MICROBENCHMARK_WALL_EXHAUSTED')
        for k,v in dict(Threads=1,FeasibilityTol=1e-8,IntFeasTol=1e-8,OptimalityTol=1e-8,Seed=20260929,LogToConsole=0,TimeLimit=min(cap,self.remaining())).items():m.setParam(k,v)
        m.Params.LogFile=str(OUT/(label.replace('/','_')+'.log'))
        start=time.perf_counter();print('NATIVE_START '+label,flush=True)
        # Wall authority only; never resource/RAM based. Covers native routines
        # that do not invoke callbacks frequently enough near the deadline.
        timer=threading.Timer(min(cap,self.remaining()),m.terminate);timer.daemon=True;timer.start()
        try:m.optimize(lambda m,w:self.sample())
        finally:timer.cancel()
        self.native_spent+=m.Runtime
        r=dict(label=label,start=start-self.start,end=time.perf_counter()-self.start,native_runtime=m.Runtime,status=m.Status,
            objective=m.ObjVal if m.SolCount else None,ObjBound=m.ObjBound if m.IsMIP and abs(m.ObjBound)<1e90 else None,
            nodes=m.NodeCount if m.IsMIP else 0,threads=1,cap=m.Params.TimeLimit)
        self.calls.append(r);write('NATIVE_CALL_LEDGER.json',self.calls);print(json.dumps(r),flush=True)
    def projection(self,x):
        points=[np.zeros(len(b.columns)) for b in self.original]
        for j,h in enumerate(self.pool+self.new):
            weight=x[self.offset+j]
            if weight:points[int(h['MESS'][-2:])-1]+=weight*pool_point(h)
        return tuple(points),x[:self.offset]
    def validate_projection(self,points,z,decisions):
        x=np.zeros(self.A.shape[1]);x[self.gcols]=z
        for m,b in enumerate(self.original):x[b.columns]=points[m]
        raw=corrected_rows(self.A,self.d,x,True,pure_binary_equalities(self.A,self.d))
        physical=[b.validate(points[m],True) for m,b in enumerate(self.original)]
        passed=raw['PASS'] and all(p['PASS'] for p in physical) and all(d.compatible(d.variable.mess,points[d.variable.mess]) for d in decisions)
        if passed:np.savez_compressed(OUT/f'VALID_BAP_INCUMBENT_{len(self.calls):04d}.npz',point=x)
        return dict(PASS=passed,objective=float(self.d['objective']@x+float(self.d['constant'])),raw=raw,physical=physical,repairs=0)
    def update_columns(self,node):
        keys=list(node.column_ids)
        active=set(self.registry.partition(keys,node.decisions)[0])
        for j,h in enumerate(self.pool+self.new):self.basevars[self.offset+j].UB=gp.GRB.INFINITY if column_key(h) in active else 0.
        self.model.update()
    def native_price(self,node,pi,alpha,m):
        if m not in self.blocks:self.blocks[m]=CheckedBlock(self.B,self.e,self.owner,self.row_owner,self.native,m)
        b=self.blocks[m];model=b.model
        old=[c for c in model.getConstrs() if c.ConstrName.startswith('EARLY_BAP_branch[')]
        if old:model.remove(old)
        for i,d in enumerate(node.decisions):
            if d.variable.mess==m:model.addConstr(gp.LinExpr([w for j,w in d.variable.terms],[b.vars[j] for j,w in d.variable.terms])==d.value,name=f'EARLY_BAP_branch[{i}]')
        model.update();cost=b.price(pi,alpha[m])
        for j in np.flatnonzero(np.diff(b.CSC.indptr)):
            k=b.CSC.indptr[j];assert F(float(cost[j]))==F(float(b.d['objective'][j]))-F(float(b.CSC.data[k]))*F(float(pi[b.CSC.indices[k]]))
        model.Params.MIPGap=0.;model.Params.MIPGapAbs=0.
        self.optimize(model,f'node{node.node_id}/price{m}',20.)
        bound=model.ObjBound if model.Status in (2,9,11) and abs(model.ObjBound)<1e90 else None
        record=dict(node=node.node_id,unit=m,status=model.Status,full_original_domain_plus_exact_branch_equalities=True,
            decisions=[asdict(d) for d in node.decisions],bound=bound,candidate_valid=False,rc=None)
        if model.SolCount:
            x=np.asarray(model.getAttr('X'));valid=b.validate(x,True)['PASS'] and all(d.compatible(m,x) for d in node.decisions)
            exact=F(-float(alpha[m]))+sum((F(float(c))*F(float(y)) for c,y in zip(cost,x) if c and y),F(0))
            valid=valid and abs(float(exact)-model.ObjVal)<=1e-8
            record.update(candidate_valid=valid,rc=float(exact))
            if bound is not None and valid and bound>float(exact)+1e-8:raise ValueError('PRICING_BOUND_CONTRADICTION')
            if valid and exact<-F(1e-8):
                a,c,column_sha=b.column(x);key=str(m)+':'+column_sha
                _,coupling_error=b.exact_coupling(x,a)
                if coupling_error>1e-12:raise ValueError('PRICING_ORIGINAL_COUPLING_TRANSPORT_FAILED')
                if key not in self.registry.columns:
                    name=f'columns/NEW_{len(self.new):04d}_{b.unit}.npz';p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
                    np.savez_compressed(p,x=x,a=a,c=c,axis=b.columns)
                    h=dict(file=p.relative_to(ROOT).as_posix(),file_SHA=sha(p),column_SHA=column_sha,MESS=b.unit)
                    self.new.append(h);self.registry.columns[key]=SimpleNamespace(mess=m,h=h,sha=column_sha)
                    ix=np.flatnonzero(a);column=gp.Column(a[ix].tolist()+[1.],[self.constraints[i] for i in ix]+[self.constraints[len(self.grows)+m]])
                    self.basevars.append(self.model.addVar(lb=0.,obj=c,name=f'lambda[{b.unit},new{len(self.new)-1}]',column=column));self.model.update()
                    record['added_column']=key
        self.prices.append(record);write('PRICING_LEDGER.json',self.prices)
        return bound
    def node_solve(self,node,registry):
        keys=tuple(node.column_ids)
        if self.root_pending:
            self.root_pending=False;p,z=self.projection(self.rootpoint)
            return NodeResult('FROZEN_ROOT_EARLY_BRANCH',keys,float(self.v['objective']@self.rootpoint+self.v['constant']),self.floor,False,p,z,certificate=node.bound_certificate)
        self.update_columns(node);self.model.Params.Method=2;self.model.Params.Crossover=1
        self.optimize(self.model,f'node{node.node_id}/rmp',150.)
        if self.model.Status!=2:return NodeResult('RMP_INCONCLUSIVE',keys)
        rmp_objective=self.model.ObjVal
        rmp_cost=np.asarray(self.model.getAttr('Obj'))
        active_upper=np.asarray(self.model.getAttr('UB'))
        x=np.asarray(self.model.getAttr('X'));p,z=self.projection(x)
        # Original affine/physical thresholds, no node infeasibility claim.
        matrix=self.model.getA().tocsr();rhs=np.asarray(self.model.getAttr('RHS'));sense=np.asarray(self.model.getAttr('Sense'))
        r=matrix@x-rhs;vio=np.where(sense=='=',abs(r),np.where(sense=='<',np.maximum(r,0),np.maximum(-r,0)))
        if np.max(vio,initial=0)>1e-6:return NodeResult('PRIMAL_AUDIT_INCONCLUSIVE',keys)
        file=OUT/f'NODE_{node.node_id:04d}_BEFORE_GATE.npz';capture(self.model,file)
        pi,trace=numerical_zero_sign(np.asarray(self.model.getAttr('Pi')),sense)
        rc=np.asarray(self.model.getAttr('Obj'))-matrix.T@pi
        try:free_rc_consistency(rc,np.asarray(self.model.getAttr('LB')),np.asarray(self.model.getAttr('UB')))
        except ValueError:
            return NodeResult('INHERITED_BOUND_ONLY_FREE_RC_DIAGNOSTIC',keys,self.model.ObjVal,node.lower_bound,False,p,z,certificate=node.bound_certificate)
        globalpi=pi[:len(self.grows)];alpha=pi[-4:];bounds=[]
        for m in range(4):
            if self.remaining()<=0:break
            bounds.append(self.native_price(node,globalpi,alpha,m))
        proof=dict(node.bound_certificate);lb=node.lower_bound
        if len(bounds)==4 and all(b is not None for b in bounds):
            value,gproof=global_dual(self.global_A,self.global_d,globalpi,self.lo[self.gcols],self.hi[self.gcols])
            candidate,exact,beta,delta=corrected(value,alpha,bounds)
            # Reconstruct full corrected theorem independently by CSC coordinates.
            C=self.global_A.tocsc();independent=F(float(self.global_d['constant']))+sum((F(float(pi))*F(float(b)) for pi,b in zip(globalpi,self.global_d['rhs']) if pi),F(0))
            for j,c in enumerate(self.global_d['objective']):
                a,b=C.indptr[j:j+2];q=F(float(c))-sum((F(float(globalpi[int(i)]))*F(float(w)) for i,w in zip(C.indices[a:b],C.data[a:b]) if globalpi[int(i)]),F(0))
                if q:independent+=q*F(float(self.lo[self.gcols[j]] if q>=0 else self.hi[self.gcols[j]]))
            assert independent==value
            terms=[F(float(a))+min(F(0),F(down(F(float(b))-F(1e-8)))) for a,b in zip(alpha,bounds)]
            rebuilt=independent+sum(terms,F(0))
            assert rebuilt==exact and F(candidate)<=exact
            # All retained RCs with corrected convexity dual, paid native safety.
            M=matrix.tocsc();minimum=None
            for j in range(self.offset,matrix.shape[1]):
                if active_upper[j]==0:continue  # fixed zero has zero bound support;
                # incompatible trajectories are outside this node's pricing domain.
                a,b=M.indptr[j:j+2];q=F(float(rmp_cost[j]))-sum((F(float(pi[int(i)]))*F(float(w)) for i,w in zip(M.indices[a:b],M.data[a:b]) if pi[int(i)]),F(0))
                unit=(self.pool+self.new)[j-self.offset]['MESS'];q-=delta[int(unit[-2:])-1]
                minimum=q if minimum is None else min(minimum,q)
            if minimum is not None and minimum>=0 and candidate<=rmp_objective:
                proof=dict(PASS=True,node_id=node.node_id,LB=max(lb,candidate),candidate_LB=candidate,exact_numerator=str(exact.numerator),exact_denominator=str(exact.denominator),
                    independent_CSC_corrected_formula_PASS=True,all_retained_corrected_RC_min=float(minimum),pricing_bounds=bounds,
                    pi_SHA=hashlib.sha256(pi.tobytes()).hexdigest(),rmp_objective_not_used_as_bound=True,global_residual_paid_in_proven_original_enclosures=True)
                lb=max(lb,candidate);write(f'NODE_{node.node_id:04d}_BOUND_CERTIFICATE.json',proof)
        newkeys=tuple(k for k,c in registry.columns.items() if k not in keys and all(d.compatible(c.mess,registry.point(k)) for d in node.decisions))
        return NodeResult('EARLY_BRANCH_PRICING_OPEN',keys+newkeys,rmp_objective,lb,False,p,z,certificate=proof)
    def close(self):
        self.model.dispose()
        for b in self.blocks.values():b.model.dispose()
    def checkpoint(self,status):
        tree=self.tree
        self.trajectory.append(dict(wall=time.perf_counter()-self.start,UB=tree.incumbent['objective'],LB=tree.global_lb,gap=tree.gap,nodes=len(tree.nodes),open_nodes=len(tree.open_ids),pricing_calls=len(self.prices),RMP_calls=sum('/rmp' in c['label'] for c in self.calls),status=status))
        write('EARLY_BAP_GAP_TRAJECTORY.json',self.trajectory)
        write('EARLY_BAP_NODE_LEDGER.json',[dict(node_id=n.node_id,parent=n.parent_id,depth=n.depth,decisions=[asdict(d) for d in n.decisions],LB=n.lower_bound,rmp_objective=n.rmp_objective,
            bound_certificate=n.bound_certificate,pricing_status=n.pricing_status,fathom_reason=n.fathom_reason,column_ids=n.column_ids) for n in tree.nodes.values()])
        write('EARLY_BAP_RESOURCE_LEDGER.json',self.telemetry)

def run():
    with (OUT/'EARLY_BAP_ONCE.json').open('x',encoding='utf8') as f:json.dump(dict(pid=os.getpid(),creation=psutil.Process().create_time(),wall_cap=600.,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),f)
    solver=FullScaleEarlyBAP();solver.checkpoint('START')
    try:
        while solver.remaining()>0 and solver.tree.open_ids:
            state=solver.tree.step(solver.node_solve,solver.projections,solver.validate_projection);solver.checkpoint(state)
            if state=='INCONCLUSIVE' or solver.tree.accepted(.005):break
        start,end=solver.trajectory[0],solver.trajectory[-1]
        elapsed=time.perf_counter()-solver.start;reduction=max(0,start['gap']-end['gap'])/max(elapsed,1e-12)
        # Historical continuation kept the same certified floor throughout.
        history=read(ROOT/'docs/v42_m_stage_exact_completion/DW_CONTINUATION_FINAL_RESULT.json')
        assert history['best_certified_LB']==solver.floor
        selected=(start['gap']-end['gap']>1e-8 or end['gap']<=.005) and end['gap']<=start['gap']
        write('EARLY_BAP_MICROBENCHMARK.json',dict(EXACT_DUAL_AUTHORITY_FOR_BAP=True,starting=start,ending=end,wall_seconds=elapsed,native_runtime=solver.native_spent,
            gap_reduction_per_wall_second=reduction,EARLY_BAP_SELECTED=selected,historical_root_CG_certified_global_gap_reduction_per_wall_second=0.,
            historical_comparison_scope='Same inherited global floor and current fixed integer UB; historical restricted-LP improvement is not global gap progress',
            retained_new_columns=len(solver.new),native_calls=len(solver.calls),pricing_calls=len(solver.prices),BAP_nodes=len(solver.tree.nodes),
            P1_accepted=solver.tree.accepted(.005),P2='NOT_RUN',development7200='NOT_RUN_PENDING_SELECTION' if selected else 'NOT_RUN_NOT_SELECTED',
            original_space_exhaustive_branching=True,root_CG_convergence_required=False,heuristic_only_pruning=False))
    finally:solver.close()

if __name__=='__main__':run()
