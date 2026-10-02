"""Reusable native/auxiliary LPs with durable raw input before validation."""
import gzip, hashlib, json, math, time
from pathlib import Path
import numpy as np
from scipy import sparse
import gurobipy as gp
from v42_benders.engine import configure
from v42_benders.canonical import digest_arrays
from .common import sha

class Recourse:
    def __init__(self,n,env,directory,threads=1,phase=False,objective=True):
        self.n=n;self.phase=phase;self.objective=objective;self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True);self.calls=0
        self.model=gp.Model('V2_PHASE_I' if phase else 'V2_NATIVE_RECOURSE',env=env)
        m=self.model;configure(m,threads,60,self.directory/'raw_solver.log')
        self.weights=None;self.slack_columns=[]
        matrix=n.A;lower=n.lower;upper=n.upper
        c=n.c if objective else np.zeros(len(n.yi))
        if phase:
            rowmax=np.asarray(abs(sparse.hstack([n.A,n.B],format='csr')).max(axis=1).toarray()).ravel()
            scale=np.maximum(1.,np.maximum(abs(n.b),rowmax))
            self.weights=np.exp2(-np.ceil(np.log2(scale)))
            data=[];rows=[];cost=[]
            for i,s in enumerate(n.sense):
                if s in ['<','=']:rows.append(i);data.append(-1.);cost.append(self.weights[i])
                if s in ['>','=']:rows.append(i);data.append(1.);cost.append(self.weights[i])
            aux=sparse.csr_matrix((data,(rows,np.arange(len(rows)))),shape=(len(n.b),len(rows)))
            matrix=sparse.hstack([n.A,aux],format='csr');self.slack_columns=rows
            lower=np.r_[n.lower,np.zeros(len(rows))];upper=np.r_[n.upper,np.full(len(rows),np.inf)]
            c=np.r_[np.zeros(len(n.yi)),cost]
        self.z=m.addMVar(matrix.shape[1],lb=lower,ub=upper,vtype='C',name='native_y_aux' if phase else 'native_y')
        self.rows=m.addMConstr(matrix,self.z,n.sense,n.b,name='original_native_row')
        m.setObjective(c@self.z+(0. if phase or not objective else n.objective_constant));m.update()
        self.matrix=matrix;self.cost=c
        self.axis_hash=digest_arrays(n.rownames,n.sense,n.lower,n.upper,n.xi,n.yi)
        axis=self.directory/'axis.npz'
        np.savez_compressed(axis,row_names=n.rownames,row_senses=n.sense,lower=n.lower,upper=n.upper,
            original_names=n.names,xi=n.xi,yi=n.yi,weights=np.array([]) if self.weights is None else self.weights,
            auxiliary_source_rows=np.array(self.slack_columns),matrix_indptr=matrix.indptr,
            matrix_indices=matrix.indices,matrix_data=matrix.data,b=n.b,B_indptr=n.B.indptr,B_indices=n.B.indices,B_data=n.B.data)
        self.axis_sha=sha(axis);self.build_seconds=None

    def solve(self,x,seconds=60):
        m=self.model;self.calls+=1;rhs=self.n.rhs(x);self.rows.RHS=rhs;m.Params.TimeLimit=max(.001,seconds)
        warnings=[];start=time.perf_counter()
        def callback(model,where):
            if where==gp.GRB.Callback.MESSAGE:
                msg=model.cbGet(gp.GRB.Callback.MSG_STRING).strip()
                if any(k in msg.lower() for k in ['warning','kappa','numerical','quad precision','dropped']):warnings.append(msg)
        m.optimize(callback)
        def attr(name):
            try:
                v=float(getattr(m,name));return v if math.isfinite(v) else None
            except (gp.GurobiError,AttributeError):return None
        raw=dict(status=m.Status,seconds=m.Runtime,wall_seconds=time.perf_counter()-start,iterations=m.IterCount,
            source_x=np.asarray(x).tolist(),solver_rhs=rhs.tolist(),source_hash=self.n.source_hash,
            row_axis_hash=self.axis_hash,axis_npz_sha256=self.axis_sha,axis_npz=str(self.directory/'axis.npz'),
            farkas_proof=attr('FarkasProof') if m.Status==3 else None,
            objective=attr('ObjVal') if m.Status==2 else None,Kappa=attr('Kappa'),KappaExact=None,
            warnings=warnings,phase1=self.phase,weights=None if self.weights is None else self.weights.tolist(),
            tolerances=dict(FeasibilityTol=m.Params.FeasibilityTol,OptimalityTol=m.Params.OptimalityTol,IntFeasTol=m.Params.IntFeasTol),
            Method=m.Params.Method,Seed=m.Params.Seed,InfUnbdInfo=m.Params.InfUnbdInfo,DualReductions=m.Params.DualReductions,
            multipliers=None,reduced_costs=None,primal=None,basis=None)
        if m.Status==3:
            try:raw['multipliers']=self.rows.FarkasDual.tolist()
            except gp.GurobiError:raw['certificate_unavailable']=True
        elif m.Status==2:
            raw['multipliers']=self.rows.Pi.tolist();raw['reduced_costs']=self.z.RC.tolist();raw['primal']=self.z.X.tolist()
            try:raw['basis']=dict(VBasis=self.z.VBasis.tolist(),CBasis=self.rows.CBasis.tolist())
            except gp.GurobiError:pass
        w=raw['multipliers']
        if w is not None:
            arr=np.asarray(w);raw.update(vector_sha256=digest_arrays(arr),multiplier_min=float(arr.min()),multiplier_max=float(arr.max()),
                sign_distribution=dict(negative=int(np.sum(arr<0)),zero=int(np.sum(arr==0)),positive=int(np.sum(arr>0))))
        # Flush a complete journal record BEFORE any certificate validator is called.
        payload=json.dumps(raw,sort_keys=True,allow_nan=False,separators=(',',':')).encode()
        journal=self.directory/'raw_certificates.jsonl.gz'
        with gzip.open(journal,'ab') as f:f.write(payload+b'\n')
        raw['persistence']=dict(journal=str(journal),record=self.calls,payload_sha256=hashlib.sha256(payload).hexdigest(),
            persisted_before_validation=True,raw_log=str(self.directory/'raw_solver.log'))
        return raw

    def primal_valid(self,raw):
        if raw['status']!=2 or raw['primal'] is None:return False
        z=np.asarray(raw['primal']);r=self.matrix@z-np.asarray(raw['solver_rhs'])
        v=np.where(self.n.sense=='=',abs(r),np.where(self.n.sense=='<',r,-r))
        bounds=max(0.,float(np.max(np.asarray(self.z.LB)-z,initial=0)),float(np.max(z-np.asarray(self.z.UB),initial=0)))
        return bool(np.isfinite(z).all() and np.max(v,initial=0)<=1e-7 and bounds<=1e-7)

    def close(self):self.model.dispose()
