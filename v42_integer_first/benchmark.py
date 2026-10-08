from .common import *
from .certificates import cut,known_witnesses,exact_value
import psutil,re,threading
def parameters(m,label,limit=120):
    for k,v in dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,DegenMoves=0,BarConvTol=1e-8,TimeLimit=limit,DualReductions=0,InfUnbdInfo=1).items():m.setParam(k,v)
    m.Params.LogFile=str(WORK/'logs'/f'{label}.log');m.Params.NodefileDir=str(WORK/'tmp');m.Params.LogToConsole=0;m.Params.OutputFlag=1
class Monitor:
    def __init__(self):self.stop=threading.Event();self.peak=0;self.thread=threading.Thread(target=self.run,daemon=True)
    def run(self):
        proc=psutil.Process()
        while not self.stop.wait(.1):self.peak=max(self.peak,proc.memory_info().rss)
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):self.stop.set();self.thread.join();self.peak=max(self.peak,psutil.Process().memory_info().rss)
def log_phases(path):
    text=path.read_text(encoding='utf-8',errors='replace');lines=text.splitlines()
    def number(pattern):
        m=re.search(pattern,text);return float(m[1]) if m else None
    return dict(presolve_seconds=number(r'Presolve time: ([\d.]+)s'),barrier_seconds=number(r'Barrier solved model in.*?([\d.]+) seconds'),crossover_seconds=number(r'Crossover time: ([\d.]+) seconds'),presolved=[l for l in lines if 'Presolved:' in l],factor_memory=[l for l in lines if any(k in l for k in ('Factor NZ','Factor Ops','memory'))],warnings=[l for l in lines if 'Warning' in l or 'Numerical' in l])
def main():
    import gurobipy as gp
    from v42_redundancy.model import build
    t0=time.perf_counter();A,d,_=hc.load();B=np.flatnonzero(d['types']=='B');reader=hc.physical_reader()
    assignments=sorted((WORK/'artifacts/assignments').glob('*.npz'));assert 20<=len(assignments)<=50
    assert json.loads((REPORTS/'ROUTE_PROJECTION_AUDIT.json').read_text(encoding='utf-8-sig'))['PASS']
    prior.objective_identity(A,d);paths_audit('benchmark_build')
    f=dict(d,types=np.full(A.shape[1],'C'),lower=d['lower'].copy(),upper=d['upper'].copy())
    m=build(A,f);variables=m.getVars();bv=[variables[j] for j in B]
    rows=[];certs=[];best=UB;best_id=None
    for i,path in enumerate(assignments):
        label=f'recourse_{i:03d}';start=time.perf_counter()
        with np.load(path) as z:center=z['x'];zval=z['z']
        assert hc.replay(A,d,center,True)['PASS']
        m.reset();m.setAttr('LB',bv,zval.tolist());m.setAttr('UB',bv,zval.tolist());parameters(m,label);m.update()
        assert np.asarray(m.getAttr('Obj')).tobytes()==d['objective'].tobytes() and np.float64(m.ObjCon).tobytes()==d['constant'].tobytes()
        paths_audit(label,m)
        token=WORK/'checkpoints'/f'{label}_ONCE.json';assert not token.exists();write(token,dict(optimize_calls=1,fixed_original_binaries=len(B),fixed_route_flow_variables=0,TimeLimit=120,objective='minimize rho'))
        print('RECOURSE_START',i,flush=True)
        with Monitor() as monitor:m.optimize()
        rec=dict(assignment=path.stem,Status=int(m.Status),Runtime=float(m.Runtime),Work=float(m.Work),iterations=float(m.IterCount),barrier_iterations=int(m.BarIterCount),peak_RSS=monitor.peak,rows=m.NumConstrs,cols=m.NumVars,nnz=m.NumNZs,primal_available=bool(m.SolCount),replay_PASS=False,dual_certificate_PASS=False)
        if m.SolCount:
            x=np.array(m.getAttr('X'));pi=np.array(m.getAttr('Pi'));rc=np.array(m.getAttr('RC'));slack=np.array(m.getAttr('Slack'))
            save(WORK/'artifacts'/f'{label}_RAW.npz',x=x,pi=pi,rc=rc,slack=slack,z=zval,B=B)
            replay=prior.prior.full_replay(A,d,x,reader);write(WORK/'artifacts'/f'{label}_REPLAY.json',replay)
            rec.update(replay_PASS=replay['PASS'],objective=float(d['objective']@x),row_violation=replay['original_C3A']['max_constraint_violation'],bound_violation=replay['original_C3A']['max_bound_violation'],int_violation=replay['original_C3A']['max_integrality_violation'],stationarity_vs_RC_max=float(abs(d['objective']-A.T@pi-rc).max()))
            print('RECOURSE_NATIVE_DONE',i,rec['Runtime'],'replay',rec['replay_PASS'],flush=True)
            cc=cut(A,d,B,pi,WORK/'artifacts'/f'cut_{i:03d}')
            if cc['PASS']:
                known=known_witnesses(cc,d,assignments);cc['known_witness_validation']=known;cc['PASS']=known['PASS'];cc['source_exact_lower']=float(exact_value(cc,zval));cc['source_objective']=rec['objective'];cc['certificate_loss']=rec['objective']-cc['source_exact_lower'];cc.pop('beta')
            rec['dual_certificate_PASS']=cc['PASS'];certs.append(dict(assignment=path.stem,**cc))
            if replay['PASS'] and rec['objective']<best:best=rec['objective'];best_id=path.stem;save(WORK/'artifacts/BEST_VALID_POINT.npz',x=x);write(REPORTS/'BEST_FULL_REPLAY.json',replay)
        elif m.Status==gp.GRB.INFEASIBLE:
            pi=-np.array(m.getAttr('FarkasDual'));save(WORK/'artifacts'/f'{label}_FARKAS.npz',pi=pi,z=zval)
            cc=cut(A,d,B,pi,WORK/'artifacts'/f'cut_{i:03d}',kind='feasibility')
            if cc['PASS']:
                known=known_witnesses(cc,d,assignments);cc['source_separation']=float(exact_value(cc,zval));cc['PASS']=known['PASS'] and cc['source_separation']>1e-8;cc['known_witness_validation']=known;cc.pop('beta')
            certs.append(dict(assignment=path.stem,**cc));rec['dual_certificate_PASS']=cc['PASS']
        rec.update(log_phases(WORK/'logs'/f'{label}.log'));rec['wall_seconds']=time.perf_counter()-start;rows.append(rec)
        table(REPORTS/'RECOURSE_BENCHMARK.csv',rows);write(REPORTS/'BENDERS_CUT_CERTIFICATES.json',dict(certificates=certs,accepted=sum(c['PASS'] for c in certs),rejected=sum(not c['PASS'] for c in certs),fullscale_master_added=0));print('RECOURSE_DONE',i,'certificate',rec['dual_certificate_PASS'],flush=True)
    rt=[r['Runtime'] for r in rows];valid=sum(r['replay_PASS'] for r in rows)
    audit=dict(count=len(rows),median_Runtime=float(np.median(rt)),p90_Runtime=float(np.quantile(rt,.9)),max_Runtime=max(rt),native_Runtime=sum(rt),native_Work=sum(r['Work'] for r in rows),wall_seconds=time.perf_counter()-t0,peak_RSS=max(r['peak_RSS'] for r in rows),feasible_replay_PASS=valid,infeasible=sum(r['Status']==3 for r in rows),unknown=len(rows)-valid-sum(r['Status']==3 for r in rows),certificates_accepted=sum(c['PASS'] for c in certs),certificates_rejected=sum(not c['PASS'] for c in certs),performance_PASS=np.median(rt)<=10 and np.quantile(rt,.9)<=60,old_UB=UB,new_valid_UB=best,best_assignment=best_id,historical=dict(Runtime=.679999828338623,fixed_route_flow=True,fixed_binaries=True,Method=2,Crossover=0,comparison_confounded_by_fixing_and_crossover=True),bounds_finite=True,native_zero_objectives=0)
    write(REPORTS/'RECOURSE_NUMERICAL_AUDIT.json',audit);m.dispose();print('BENCHMARK_FINISHED',json.dumps(clean(audit)),flush=True)
if __name__=='__main__':main()
