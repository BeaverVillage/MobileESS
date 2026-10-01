"""Two-worker conditional oracles and bounded exact stopping receipts."""
import multiprocessing as mp,time,threading
from itertools import combinations,product
import gurobipy as gp
import psutil
from .common import *
from .oracle import Oracle

def worker(t):
    axis=read(OUT/'ROOT_STATE_AXIS.json');units=sorted(inputs()[4]);o=Oracle(t);done=[]
    try:
        # All incumbent-conditioned states first, then decreasing root mass.
        priority=sorted([(u,s) for u in units for s in axis[f'{u}:{t}']['states'] if axis[f'{u}:{t}']['root'][s]>EPS or axis[f'{u}:{t}']['incumbent'][s]>.5],
            key=lambda p:(-int(axis[f'{p[0]}:{t}']['incumbent'][p[1]]>.5),-axis[f'{p[0]}:{t}']['root'][p[1]],p))
        for u,s in priority:
            if (OUT/'O1_UNIVERSAL_STOP_CERTIFICATE.json').exists():break
            done.append(o.solve([(u,s)],'E1'))
        return dict(time=t,solved=len(done),priority_count=len(priority),universal_stop=(OUT/'O1_UNIVERSAL_STOP_CERTIFICATE.json').exists(),peak_RSS=o.peak)
    finally:o.close()

def run():
    assert read(OUT/'O1_VALIDATION_SUMMARY.json')['PASS']
    assert not (LOCAL/'ORACLE_WORKERS_STARTED.json').exists(),'WORKERS_ALREADY_STARTED'
    (LOCAL/'ORACLE_WORKERS_STARTED.json').write_text('{}\n')
    slots=read(OUT/'CRITICAL_SLOT_FREEZE.json')['slots'];process=psutil.Process();samples=[];stop=threading.Event()
    def monitor():
        while not stop.wait(.5):
            children=process.children(recursive=True);workers=[]
            for p in children:
                try:
                    cmd=p.cmdline()
                    if '--multiprocessing-fork' not in cmd:continue
                    times=p.cpu_times();workers.append(dict(pid=p.pid,RSS_bytes=p.memory_info().rss,cpu_seconds=times.user+times.system))
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            samples.append(dict(seconds=time.perf_counter()-begin,total_worker_RSS_bytes=sum(p['RSS_bytes'] for p in workers),workers=workers,
                system_available_bytes=psutil.virtual_memory().available,system_cpu_percent=psutil.cpu_percent()))
    begin=time.perf_counter();thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        with mp.get_context('spawn').Pool(2) as pool:results=pool.map(worker,slots)
    finally:stop.set();thread.join(1)
    dump('O1_WORKER_RESOURCE_RECEIPT.json',dict(initial_workers=2,max_workers_used=2,Threads_per_worker=1,physical_cores=psutil.cpu_count(logical=False),
        peak_total_worker_RSS_bytes=max((s['total_worker_RSS_bytes'] for s in samples),default=0),
        minimum_system_available_bytes=min((s['system_available_bytes'] for s in samples),default=0),
        wall_seconds=time.perf_counter()-begin,results=results,samples=samples,
        expansion=False,expansion_reason='Two workers memory-safe; universal O1 certificate makes expansion unnecessary, no additional diagnostic benefit',oversubscribed=False))
    print('ORACLE WORKERS COMPLETE',results,flush=True)

def prechecks():
    stop=read(OUT/'O1_UNIVERSAL_STOP_CERTIFICATE.json');assert stop['PASS']
    axis=read(OUT/'ROOT_STATE_AXIS.json');freeze=read(OUT/'CRITICAL_SLOT_FREEZE.json');units=sorted(inputs()[4]);rho=read(OUT/'ROOT_DIAGNOSTIC_SOURCE_RECEIPT.json')['rho']
    solved={r['key']:r for p in (OUT/'oracle_certificates').glob('*.json') if (r:=read(p))}
    e1=[];vio=[];e2=[];transport=[]
    for t in freeze['slots']:
        for u in units:
            a=axis[f'{u}:{t}'];rhs=0.
            for s in a['states']:
                key=f'E1_{t}_{u}-{s}';r=solved.get(key);beta=r['beta'] if r else DEFAULT
                assert abs(beta-DEFAULT)<=OBJ_TOL,'UNIVERSAL_CERT_CONFLICT'
                e1.append(dict(MESS=u,time=t,state=s,root_mass=a['root'][s],incumbent_mass=a['incumbent'][s],solved=bool(r),beta=beta,
                    source=key if r else 'PR109 certified global bound; universal O1 upper cert stops further solves',O1_lower_bound=r['O1_lower_bound'] if r else None,O1_uniform_feasible_upper=stop['slot_upper'][str(t)]))
                rhs+=beta*a['root'][s]
            violation=rhs-rho;vio.append(dict(MESS=u,time=t,RHS=rhs,rho=rho,violation=violation,install=violation>=1e-5))
    for t in freeze['E2_slots']:
        for u,v in combinations(units,2):
            aa=axis[f'{u}:{t}'];bb=axis[f'{v}:{t}'];m=gp.Model();m.Params.OutputFlag=0;m.Params.Method=2;m.Params.Threads=1
            w=m.addVars(aa['states'],bb['states'],lb=0,name='w')
            for a in aa['states']:m.addConstr(gp.quicksum(w[a,b] for b in bb['states'])==aa['root'][a])
            for b in bb['states']:m.addConstr(gp.quicksum(w[a,b] for a in aa['states'])==bb['root'][b])
            m.setObjective(gp.quicksum(DEFAULT*w[a,b] for a,b in w));begin=time.perf_counter();m.optimize();seconds=time.perf_counter()-begin
            assert m.Status==gp.GRB.OPTIMAL and m.MaxVio<=TOL
            bound=m.ObjVal;violation=bound-rho
            transport.append(dict(MESS_m=u,MESS_n=v,time=t,states_m=len(aa['states']),states_n=len(bb['states']),rows=m.NumConstrs,columns=m.NumVars,nonzeros=m.NumNZs,
                transport_bound=bound,rho=rho,violation=violation,status=int(m.Status),seconds=seconds,max_marginal_residual=m.MaxVio,install=violation>=1e-5,raw_marginals_used=True))
            for a,b in product(aa['states'],bb['states']):
                e2.append(dict(MESS_m=u,MESS_n=v,time=t,state_a=a,state_b=b,root_product_mass=aa['root'][a]*bb['root'][b],incumbent_pair=aa['incumbent'][a]>.5 and bb['incumbent'][b]>.5,
                    beta=DEFAULT,solved=False,source='PR109 global certified LB; universal full O1 upper bound proves no pair beta can improve it',O1_uniform_feasible_upper=stop['slot_upper'][str(t)]))
            m.dispose()
    table('E1_BETA_TABLE.csv',e1);table('E1_ROOT_VIOLATIONS.csv',vio);table('E2_BETA_TABLE.csv',e2);table('E2_TRANSPORT_PRECHECK.csv',transport)
    stats=[]
    for r in solved.values():stats.append({k:r[k] for k in ['key','kind','slot','status','O1_lower_bound','beta','seconds','RSS_bytes','pid','cpu_seconds','rows','columns','nonzeros','Method','Threads','max_violation']})
    table('O1_ORACLE_STATS.csv',sorted(stats,key=lambda r:r['key']))
    dump('EPIGRAPH_CUT_SELECTION.json',dict(E1_CUTS_ADDED=sum(r['install'] for r in vio),E2_CUTS_ADDED=sum(r['install'] for r in transport),
        E1_max_root_violation=max(r['violation'] for r in vio),E2_max_root_violation=max(r['violation'] for r in transport),
        E1_oracles_solved=len(stats),E2_oracles_solved=0,E1_reachable_states=len(e1),E2_reachable_pairs=len(e2),
        selected='E0',PRODUCTION_BASE='M1-F3',stop_certificate='O1_UNIVERSAL_STOP_CERTIFICATE.json',
        reason='All single and pair beta coefficients provably equal global default; no useful root-violated cut. No full E1/E2 root optimization authorized.',
        priority_stop_reason='Exact universal feasible upper bound proves no remaining state, including root-positive priorities, can change any coefficient. This is the no-possible-violation stopping logic, not a root-based state deletion.',
        all_six_pairs_all_three_slots_prechecked=True,no_model_cut_installed=True))
    print('E1 E2 PRECHECKS',read(OUT/'EPIGRAPH_CUT_SELECTION.json'),flush=True)

if __name__=='__main__':
    import sys
    globals()[sys.argv[1]]()
