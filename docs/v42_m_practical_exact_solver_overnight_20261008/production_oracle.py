"""Production original-domain LP oracle, forked from registered M0 without modifying M0."""
from practical_support import *
from fractions import Fraction as F
OUT=OUT/"external_production"
raw_table=table
def table(n,rows,fields=None):return raw_table(OUT/n,rows)
def write(n,value):return atomic(OUT/n,value)
verify=verifier.verify
core=module("production_exact_core",OLD/"bb_controller.py")
ExactBB=core.ExactBB;history_hash=core.history_hash;digest=core.digest
import argparse,re,threading,traceback

class LPOracle:
    def __init__(self):
        import gurobipy as gp
        from v42_redundancy.model import build
        from v42_integrated.matrix import arrays
        self.gp=gp;self.A,self.d,_=hc.load();self.CSC=self.A.tocsc();self.binary=np.flatnonzero(self.d['types']=='B');self.reader=None
        assert np.isfinite(self.d['lower']).all() and np.isfinite(self.d['upper']).all()
        assert np.all(self.d['lower'][self.binary]==0) and np.all(self.d['upper'][self.binary]==1)
        e=dict(self.d,types=np.full(self.A.shape[1],'C'));self.m=build(self.A,e);self.variables=self.m.getVars();self.rows=self.m.getConstrs()
        for k,v in SETTINGS.items():self.m.setParam(k,v)
        self.m.Params.TimeLimit=bounded_limit(1800);self.m.Params.InfUnbdInfo=1;self.m.Params.DualReductions=0;self.m.Params.LogToConsole=0;self.m.Params.OutputFlag=1
        B,transport=arrays(self.m);assert (B!=self.A).nnz==0 and B.shape==self.A.shape
        assert all(np.array_equal(e[k],transport[k]) for k in e)
        objective_check=verify(ROOT,transport,int(self.m.ModelSense));assert objective_check['PASS']
        self.identity=dict(scientific=SCIENTIFIC,A_SHA256=sha(hc.PARENT/'C3A_A.npz'),DATA_SHA256=sha(hc.PARENT/'C3A_DATA.npz'),objective=objective_check['source_objective_SHA256'],binary_columns_SHA256=hashlib.sha256(self.binary.tobytes()).hexdigest(),rows=self.A.shape[0],columns=self.A.shape[1],nnz=self.A.nnz,root_relaxation='Only original B types relaxed to C',node_changes='Only inherited original B LB=UB=0/1',pruning_tolerance='0')
        write('EXTERNAL_MODEL_AUTHORITY.json',dict(PASS=True,identity=self.identity,native_types_all_C=True,original_matrix_and_all_other_fields_identical=True,T1_rows=0,added_rows=0,all_original_bounds_finite=True))
        self.model_signature=self.identity.copy();self.original_optimize=gp.Model.optimize;self.calls=[]
        def guarded(model,*args,**kwargs):
            assert model is self.m and self.active is not None
            marker=OUT/'external_nodes'/f'{self.active:04d}'/'OPTIMIZE_ONCE.json';marker.parent.mkdir(parents=True,exist_ok=True)
            with marker.open('x',encoding='utf-8') as f:json.dump(dict(node_id=self.active,UTC=stamp(),LP_only=True,source_commit=git('rev-parse','HEAD'),optimize_calls=1),f,indent=2)
            self.calls.append(self.active);return self.original_optimize(model,*args,**kwargs)
        gp.Model.optimize=guarded;self.active=None
    def objective_identity(self):
        return verify(ROOT,dict(names=np.array(self.m.getAttr('VarName')),objective=np.array(self.m.getAttr('Obj')),constant=np.array(self.m.ObjCon)),int(self.m.ModelSense))
    def solve(self,node):
        n=node['id'];folder=OUT/'external_nodes'/f'{n:04d}';folder.mkdir(parents=True,exist_ok=True);receipt=folder/'RESULT.json'
        # Completed results are replayed on checkpoint recovery; no repeated LP.
        if receipt.exists():
            r=read(receipt);assert r['identity']==self.identity and r['fixing_hash']==node['fixing_hash'];return r
        assert not (folder/'OPTIMIZE_ONCE.json').exists(),'INTERRUPTED_NODE_REQUIRES_EXPLICIT_RECOVERY_NO_SILENT_RESOLVE'
        t0=time.perf_counter();m=self.m;gp=self.gp;self.active=n;m.reset();d=dict(self.d,lower=self.d['lower'].copy(),upper=self.d['upper'].copy())
        for j,v in node['fixings']:
            assert self.d['types'][j]=='B';d['lower'][j]=d['upper'][j]=v
        m.setAttr('LB',self.variables,d['lower'].tolist());m.setAttr('UB',self.variables,d['upper'].tolist());m.update()
        assert np.array_equal(np.asarray(m.getAttr('LB')),d['lower']) and np.array_equal(np.asarray(m.getAttr('UB')),d['upper'])
        basis_supplied=False;basis_source=None
        if node['parent'] is not None:
            basis_source=OUT/'external_nodes'/f"{node['parent']:04d}"/'BASIS.npz'
            with np.load(basis_source) as z:
                assert z['VBasis'].shape==(self.A.shape[1],) and z['CBasis'].shape==(self.A.shape[0],)
                m.setAttr('VBasis',self.variables,z['VBasis'].tolist());m.setAttr('CBasis',self.rows,z['CBasis'].tolist())
            m.Params.Method=1;m.Params.LPWarmStart=1;basis_supplied=True
        else:m.Params.Method=1;m.Params.Crossover=2;m.Params.LPWarmStart=1 # Registered cold dual-simplex recovery after M0 crossover failure.
        m.Params.TimeLimit=bounded_limit(1800 if node['parent'] is None else 900)
        m.Params.LogFile=str(folder/'LP.log');m.update();identity=self.objective_identity();assert identity['PASS'],'OBJECTIVE_IDENTITY_FAILED_STOP_NODE_OPTIMIZE_0'
        settings=parameters(m);setup=time.perf_counter()-t0
        import psutil
        process=psutil.Process();rss=[];stop=threading.Event()
        def monitor():
            while not stop.is_set():rss.append(process.memory_info().rss);stop.wait(.5)
        monitor_thread=threading.Thread(target=monitor,daemon=True);monitor_thread.start();live=-30.;errors=[];phases=[];self.last_checkpoint=0
        def cb(model,where):
            nonlocal live
            if where==gp.GRB.Callback.POLLING:return
            try:
                t=float(model.cbGet(gp.GRB.Callback.RUNTIME))
                if remaining(900)<=0:model.terminate()
                if hasattr(self,"checkpoint_hook") and t-getattr(self,"last_checkpoint",0)>=300:
                    self.checkpoint_hook();self.last_checkpoint=t
                if where==gp.GRB.Callback.MESSAGE:
                    line=model.cbGet(gp.GRB.Callback.MSG_STRING).strip()
                    if line.startswith(('Presolve time:','Barrier solved model','Crossover time:','Optimal objective','Solved in')):phases.append(dict(Runtime=t,literal=line))
                if t-live>=30:live=t;write('EXTERNAL_LIVE.json',dict(node_id=n,depth=node['depth'],LP_Runtime=t,phase='OPTIMIZE',fixing_hash=node['fixing_hash']));print('EXTERNAL_LP_PROGRESS',n,node['depth'],round(t,3),flush=True)
            except BaseException:errors.append(traceback.format_exc());model.terminate()
        print('EXTERNAL_LP_START',n,node['depth'],node['fixing_hash'],flush=True);exception=None
        try:m.optimize(cb)
        except BaseException:exception=traceback.format_exc()
        finally:stop.set();monitor_thread.join(timeout=2);rss.append(process.memory_info().rss)
        status=int(m.Status);assert parameters(m)==settings
        result=dict(identity=self.identity,fixing_hash=node['fixing_hash'],node_id=n,fixings=node['fixings'],LP_status={2:'OPTIMAL',3:'INFEASIBLE'}.get(status,'UNRESOLVED'),native_status=status,LP_objective=float(m.ObjVal) if status==2 else None,certified_LB=None,optimal_LP_certificate_PASS=False,exact_infeasibility_PASS=False,proof_checked=True,Runtime=float(m.Runtime),Work=float(m.Work),IterCount=float(m.IterCount),BarIterCount=int(m.BarIterCount),setup_wall_seconds=setup,peak_RSS=max(rss),basis_supplied=basis_supplied,basis_source=basis_source.relative_to(OUT).as_posix() if basis_source else None,branch_variable=None,branch_is_original_binary=False,raw_fractional_branch_value=None,fractional_binary_count=None,witness=None,receipt=receipt.relative_to(OUT).as_posix(),parameters=settings,objective_identity=identity,phases=phases,callback_errors=errors,exception=exception,bounds_SHA256=hashlib.sha256(d['lower'].tobytes()+d['upper'].tobytes()).hexdigest())
        assert not errors and exception is None,'LP_CALLBACK_OR_NATIVE_EXCEPTION_RETAIN_IN_FLIGHT'
        proof_start=time.perf_counter()
        if status==2:
            x=np.asarray(m.getAttr('X'));pi=np.asarray(m.getAttr('Pi'));rc=np.asarray(m.getAttr('RC'))
            certificate,clipped,residual,terms=hc.exact_bounded_lagrangian(self.CSC,d,pi)
            np.savez_compressed(folder/'LP_POINT_PROOF.npz',x=x,Pi=pi,RC=rc,clipped_Pi=clipped,exact_residual_display=residual,exact_bound_terms_display=terms)
            certificate.update(PASS=True,LP_status='OPTIMAL',original_model_identity=self.identity,fixing_hash=node['fixing_hash'],bounds_SHA256=result['bounds_SHA256'],proof_vector_SHA256=sha(folder/'LP_POINT_PROOF.npz'))
            write(receipt.relative_to(OUT).parent/'LB_CERTIFICATE.json',certificate)
            result.update(certified_LB=certificate['exact_rational'],optimal_LP_certificate_PASS=True,LP_primal_replay=hc.replay(self.A,dict(d,types=np.full(len(self.variables),'C')),x,False),LB_certificate_SHA256=sha(folder/'LB_CERTIFICATE.json'))
            np.savez_compressed(folder/'BASIS.npz',VBasis=np.asarray(m.getAttr('VBasis'),dtype=np.int8),CBasis=np.asarray(m.getAttr('CBasis'),dtype=np.int8))
            result['basis_output_SHA256']=sha(folder/'BASIS.npz')
            values=x[self.binary];distance=np.minimum(np.abs(values),np.abs(1-values));result['fractional_binary_count']=int(np.count_nonzero(distance>1e-8));result['raw_noninteger_binary_count']=int(np.count_nonzero((values!=0)&(values!=1)))
            fixed={j for j,v in node['fixings']};eligible=[int(j) for j in self.binary if int(j) not in fixed and x[j] not in (0,1)]
            if eligible:
                j=self.choose_branch(eligible,x) if hasattr(self,'choose_branch') else min(eligible,key=lambda j:(-min(abs(float(x[j])),abs(1-float(x[j]))),j))
                result.update(branch_variable=j,branch_name=str(self.d['names'][j]),branch_is_original_binary=True,raw_fractional_branch_value=float(x[j]))
            elif np.all((values==0)|(values==1)):
                if self.reader is None:self.reader=hc.physical_reader()
                replay=full_replay(self.A,self.d,x,self.reader);write(receipt.relative_to(OUT).parent/'INTEGER_REPLAY.json',replay)
                if replay['PASS']:
                    result['witness']=dict(PASS=True,full_original_replay_PASS=True,raw_vector_unchanged=True,objective_exact=str(F.from_float(float(x[239826]))),point=(folder/'LP_POINT_PROOF.npz').relative_to(OUT).as_posix(),replay=(folder/'INTEGER_REPLAY.json').relative_to(OUT).as_posix(),replay_SHA256=sha(folder/'INTEGER_REPLAY.json'))
        elif status==3:
            ray=np.asarray(m.getAttr('FarkasDual'));zero=dict(d,objective=np.zeros_like(d['objective']),constant=np.array(0.))
            # Zero coefficients are used ONLY in this solver-free contradiction
            # calculation. The native scientific objective stays minimize rho.
            certificate,clipped,residual,terms=hc.exact_bounded_lagrangian(self.CSC,zero,-ray)
            positive=F(certificate['exact_rational'])>0
            np.savez_compressed(folder/'FARKAS_PROOF.npz',FarkasDual=ray,clipped_Pi=clipped)
            certificate.update(PASS=positive,proof_kind='Exact positive lower bound for mathematical zero on feasible set; contradiction',native_objective_unchanged=True,original_model_identity=self.identity,fixing_hash=node['fixing_hash'])
            write(receipt.relative_to(OUT).parent/'INFEASIBILITY_CERTIFICATE.json',certificate);result.update(exact_infeasibility_PASS=positive,infeasibility_certificate_SHA256=sha(folder/'INFEASIBILITY_CERTIFICATE.json'))
        result['proof_wall_seconds']=time.perf_counter()-proof_start
        log=(folder/'LP.log').read_text(encoding='utf-8',errors='replace');basis_lines=[l for l in log.splitlines() if re.search(r'warm.start|basis',l,re.I)]
        result.update(basis_evidence=basis_lines,basis_accepted=basis_supplied and any('LP warm-start: use basis' in l for l in basis_lines) and not any(re.search(r'ignored|invalid|discard',l,re.I) for l in basis_lines),warnings=[l for l in log.splitlines() if re.search(r'warning|numerical trouble|unscaled.*violation|quad precision',l,re.I)],total_node_wall_seconds=time.perf_counter()-t0)
        assert self.objective_identity()['PASS'];write(receipt.relative_to(OUT),result);self.active=None
        print('EXTERNAL_LP_COMPLETE',n,result['LP_status'],round(result['Runtime'],3),result['LP_objective'],result['basis_accepted'],flush=True);return result
    def close(self):self.gp.Model.optimize=self.original_optimize;self.m.dispose()
