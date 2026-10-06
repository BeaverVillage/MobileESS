"""One preregistered short P1 MILP per arm. No automatic extension."""
import os
os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
import json,re,time,threading,sys
import psutil
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from .common import *
from .build import replay
from .materialize import model

def inventory():
    rows=[]
    ancestors={p.pid for p in psutil.Process().parents()}
    for p in psutil.process_iter(['pid','create_time','cmdline','cpu_times']):
        try:
            cmd=p.info['cmdline'] or [];joined=' '.join(cmd).lower()
            if p.pid==os.getpid() or not cmd:continue
            if 'python' not in Path(cmd[0]).name.lower() and not any(t in Path(cmd[0]).name.lower() for t in ('gurobi','cplex','scip')):continue
            monitor='web_monitor' in joined or 'server.py' in joined
            orchestrator=p.pid in ancestors and 'v42_pr134_sc.benchmark' in joined and '--arm' not in joined
            scientific=not monitor and any(t in joined for t in ('worker','canary','benchmark','coordinator','a1','solve','optimiz','v42_pr134_sc'))
            rows.append(dict(pid=p.pid,created=p.info['create_time'],command=cmd,scientific_candidate=scientific and not orchestrator,monitor_only=monitor,own_orchestrator=orchestrator,cpu_seconds=sum(p.info['cpu_times'][:2])))
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    return rows

def gate():
    identity=json.loads((OUT/'PR134_BASE_IDENTITY.json').read_text())
    for rec in [identity['bundle'],identity['original_data'],identity['original_raw_point'],identity['matrix'],identity['attributes']]+identity['input_sources']:
        assert sha(rec['path'])==rec['sha256'],'FROZEN_PR134_SHA_DRIFT:'+rec['path']
    for rec in identity['executed_source_files']:
        assert sha(ROOT/rec['path'])==rec['sha256'],'PR134_SCIENTIFIC_SOURCE_DRIFT:'+rec['path']
    assert json.loads((OUT/'PR134_ACCEPTED_WITNESS_REPLAY.json').read_text())['BASELINE_FEASIBLE_WITNESS_PASS']
    assert json.loads((OUT/'START_VALIDATION.json').read_text())['PASS']
    assert json.loads((OUT/'A_STAGE_ADVERSARIAL_RESULTS.json').read_text())['PASS']
    assert json.loads((OUT/'A_STAGE_FIXTURE_RESULTS.json').read_text())['PASS']
    assert all(json.loads((OUT/(n+'_INDEPENDENT_VERIFICATION.json')).read_text())['PASS'] for n in ('A1R','A2SC'))
    a=json.loads((OUT/'A0_CENSUS.json').read_text());b=json.loads((OUT/'A2SC_MODEL_CENSUS.json').read_text())
    pa=json.loads((OUT/'A0_PRESOLVE_FORENSIC.json').read_text());pb=json.loads((OUT/'A2SC_PRESOLVE_CENSUS.json').read_text())
    gains={k:1-b[k]/a[k] for k in ('rows','nnz','binaries','continuous')};gains['presolved_nnz']=1-pb['nnz']/pa['nnz']
    inv=inventory();r=dict(PASS=max(gains.values())>=.15 and not any(p['scientific_candidate'] for p in inv),size_gains=gains,
           size_PASS=max(gains.values())>=.15,processes=inv,resource_conflict=any(p['scientific_candidate'] for p in inv),memory_gate=False)
    write('BENCHMARK_GATE.json',r);return r

def arm(name,full=False):
    prereq=gate()
    if not prereq['PASS']:raise PermissionError('BENCHMARK_GATE_NOT_PASS')
    if full and not json.loads((OUT/'ROOT_COMPARISON.json').read_text())['full_comparison_authorized']:
        raise PermissionError('FULL_COMPARISON_ROOT_MEMORY_BENEFIT_REQUIRED')
    out=OUT/(('FULL_' if full else 'SHORT_')+name+'_RESULT.json')
    if out.exists():raise PermissionError('ONE_PREREGISTERED_ARM_NO_RETRY:'+str(out))
    inv=inventory();write(('FULL_' if full else 'SHORT_')+name+'_RESOURCE_GATE.json',dict(processes=inv,memory_gate=False))
    if any(p['scientific_candidate'] for p in inv):raise PermissionError('OTHER_SCIENTIFIC_OPTIMIZER_ACTIVE')
    samples=[];stop=threading.Event();started=time.perf_counter();phase=['setup'];process=psutil.Process()
    def sample():
        while not stop.is_set():
            mem=psutil.virtual_memory();mi=process.memory_info();ct=process.cpu_times()
            samples.append(dict(arm=name,mode='full' if full else 'short',elapsed=time.perf_counter()-started,phase=phase[0],
                 RSS=mi.rss,available_RAM=mem.available,swap_used=psutil.swap_memory().used,cpu_seconds=ct.user+ct.system,
                 memory_telemetry_only=True))
            stop.wait(1)
    thread=threading.Thread(target=sample,daemon=True);thread.start();m=None
    try:
        a=sp.load_npz(LOCAL/'A0_MATRIX.npz');z=attributes()
        m=model(name);x=m.getVars();mapping=None
        if name=='A0':point=np.load(LOCAL/'ACCEPTED_POINT.npz')['values']
        else:mapping=proof_data(name)['mapping'];point=np.load(LOCAL/(name+'_ACCEPTED_POINT.npz'))['values']
        m.setAttr('Start',x,point);m.update();del point
        objective=read_artifact('ACTIVE_OBJECTIVE_HIERARCHY.json') if name=='A0' else read_artifact(name+'_ACTIVE_OBJECTIVES.json')
        settings={k:getattr(m.Params,k) for k in ('Method','Threads','Seed','MIPGap','Presolve','Cuts','Heuristics','NumericFocus','FeasibilityTol','OptimalityTol','IntFeasTol','MemLimit','SoftMemLimit','NodefileStart')}
        assert settings['Method']==1 and settings['Threads']==1 and settings['Seed']==20260929 and settings['MIPGap']==.005
        assert all(settings[k]==v for k,v in dict(Presolve=-1,Cuts=-1,Heuristics=.05,NumericFocus=0).items())
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(LOCAL/(('FULL_' if full else 'SHORT_')+name+'.log'))
        events=[];passes=[];spent=0.;first=[None];errors=[];component=['rho'];last=[-1.]
        if full:
            import gzip,pickle
            from .snapshot import certify
            from v42_integrated.contract import physical_authority
            from v42_bootstrap.grid import coefficients
            with gzip.open(LOCAL/'SCIENTIFIC_INTERFACES.pkl.gz','rb') as f:descriptor=pickle.load(f)
            with (LOCAL/'DATA.pkl').open('rb') as f:scientific_data=pickle.load(f)
            with physical_authority():_,grid_coefficients=coefficients(scientific_data[0])
        def original(y):
            if mapping is None:return y
            raw=np.zeros(a.shape[1]);valid=mapping>=0;raw[valid]=y[mapping[valid]];return raw
        def cb(native,where):
            if where==gp.GRB.Callback.POLLING:return
            try:
                rt=float(native.cbGet(gp.GRB.Callback.RUNTIME))
                if where==gp.GRB.Callback.MESSAGE:
                    line=native.cbGet(gp.GRB.Callback.MSG_STRING).strip()
                    if line.startswith(('Presolve time:','Presolved:','Root relaxation:')):
                        events.append(dict(component=component[0],native_seconds=rt,literal=line))
                if where==gp.GRB.Callback.MIPSOL and first[0] is None:
                    y=np.asarray(native.cbGetSolution(x));certificate=replay(a,z,original(y))
                    if certificate['PASS']:first[0]=dict(component=component[0],native_seconds=rt,original_rows=certificate)
                if rt-last[0]>=1:
                    last[0]=rt;write(('FULL_' if full else 'SHORT_')+name+'_LIVE.json',dict(component=component[0],native_runtime=spent+rt,events=events[-5:]))
            except Exception as e:errors.append(repr(e));native.terminate()
        setup=time.perf_counter()-started
        for e in objective[:4 if full else 1]:
            remaining=(3600 if full else 300)-spent
            if remaining<=0:break
            component[0]=e['name'];phase[0]='solve:'+e['name'];last[0]=-1
            expression=gp.LinExpr(e['coefficients'],[x[j] for j in e['indices']])+e['constant']
            m.setObjective(expression);m.Params.TimeLimit=remaining;m.optimize(cb);spent+=m.Runtime
            point=np.asarray(m.getAttr('X')) if m.SolCount else None
            cert=replay(a,z,original(point)) if point is not None else None
            physical=None
            if full and cert and cert['PASS']:
                with physical_authority():physical,_,_,_=certify(descriptor,scientific_data,original(point),cert,grid_coefficients)
            def attr(n):
                try:return float(getattr(m,n))
                except (gp.GurobiError,AttributeError):return None
            r=dict(component=e['name'],status=m.Status,native_runtime=m.Runtime,native_Work=attr('Work'),node_count=attr('NodeCount'),
                objective=attr('ObjVal') if m.SolCount else None,BestBd=attr('ObjBound'),gap=attr('MIPGap') if m.SolCount else None,
                incumbent_original_row_validation=cert,valid_UB=m.ObjVal if cert and cert['PASS'] else None,
                valid_LB=attr('ObjBound'),physical=physical,root_completion=any(v['component']==e['name'] and v['literal'].startswith('Root relaxation:') and 'interrupted' not in v['literal'].lower() for v in events))
            passes.append(r)
            if not full or m.Status!=gp.GRB.OPTIMAL or not cert or not cert['PASS'] or not physical or not physical['PASS'] or errors:break
            m.addConstr(expression<=m.ObjVal+(1e-7 if e['name']=='rho' else 1e-8),name='single_thread_A1_lock_'+e['name']);m.update()
        result=dict(arm=name,mode='full' if full else 'short',native_optimization_calls=len(passes),solver_settings=settings,
            setup_wall_seconds=setup,total_native_runtime=spent,total_wall_seconds=time.perf_counter()-started,passes=passes,
            full_four_pass_native_row_acceptance=full and len(passes)==4 and all(p['status']==2 and p['incumbent_original_row_validation']['PASS'] and p['physical']['PASS'] for p in passes),
            first_valid_incumbent=first[0],events=events,callback_errors=errors,accepted_start_used=True,parameter_sweep=False,
            memory_guards=False,cap_seconds=3600 if full else 300,observed_peak_RSS=max(s['RSS'] for s in samples),
            observed_peak_solve_RSS=max((s['RSS'] for s in samples if s['phase'].startswith('solve')),default=None),
            sampled_peak_not_exact=True,one_hour_solvability_claim=False)
        write(out.name,result);np.savez_compressed(LOCAL/(('FULL_' if full else 'SHORT_')+name+'_POINT.npz'),values=point if point is not None else [])
        print('BENCHMARK_ARM_DONE',name,result['total_native_runtime'],flush=True)
    finally:
        stop.set();thread.join();table(('FULL_' if full else 'SHORT_')+name+'_RESOURCE_LEDGER.csv',samples)
        if m is not None:m.dispose()

def comparison():
    rows=[json.loads((OUT/('SHORT_'+n+'_RESULT.json')).read_text()) for n in ('A0','A2SC')]
    def root(r):
        for e in r['events']:
            if e['literal'].startswith('Root relaxation:'):
                match=re.search(r'([0-9.]+) seconds \(([0-9.]+) work units\)',e['literal'])
                if match:return dict(seconds=float(match[1]),Work=float(match[2]),completed='interrupted' not in e['literal'].lower(),literal=e['literal'])
        return None
    roots=[root(r) for r in rows];gains={}
    if all(roots) and all(r['completed'] for r in roots):gains.update(root_time=1-roots[1]['seconds']/roots[0]['seconds'],root_Work=1-roots[1]['Work']/roots[0]['Work'])
    gains['peak_RSS']=1-rows[1]['observed_peak_RSS']/rows[0]['observed_peak_RSS']
    gains['model_setup']=1-rows[1]['setup_wall_seconds']/rows[0]['setup_wall_seconds']
    if all(r['first_valid_incumbent'] for r in rows):
        gains['first_valid_incumbent']=1-rows[1]['first_valid_incumbent']['native_seconds']/rows[0]['first_valid_incumbent']['native_seconds']
    comparable_root_memory=(gains.get('root_time',-1)>=.15 or gains.get('root_Work',-1)>=.15 or gains['peak_RSS']>=.15)
    targets=[r['passes'][0] for r in rows]
    same_target=(all(p['status']==2 and p['incumbent_original_row_validation']['PASS'] and p['gap']<=.005 for p in targets) and targets[0]['objective']==targets[1]['objective'])
    if same_target:gains['same_P1_objective_gap_target_runtime']=1-rows[1]['total_native_runtime']/rows[0]['total_native_runtime']
    selected=(comparable_root_memory or gains.get('same_P1_objective_gap_target_runtime',-1)>=.15 or
        gains['model_setup']>=.15 and rows[0]['setup_wall_seconds']-rows[1]['setup_wall_seconds']>=10 or
        gains.get('first_valid_incumbent',-1)>=.15 and rows[0]['first_valid_incumbent']['native_seconds']-rows[1]['first_valid_incumbent']['native_seconds']>=1)
    result=dict(arms=rows,root_metrics=roots,relative_improvements=gains,practical_benefit=selected,
          same_P1_objective_and_gap_authority=same_target,clear_root_memory_benefit=comparable_root_memory,full_comparison_authorized=comparable_root_memory,
          root_interruption_does_not_prove_completed_LP_speedup=True,
          no_claim_from_size_alone=True)
    write('ROOT_COMPARISON.json',result)
    return result

def run():
    g=gate()
    if not g['PASS']:print('BENCHMARK_DEFERRED',g,flush=True);return
    # New processes avoid accumulated native memory/cache from prior arms.
    import subprocess
    for n in ('A0','A2SC'):
        subprocess.run([sys.executable,'-X','utf8','-m','v42_pr134_sc.benchmark','--arm',n],cwd=ROOT,check=True)
    comparison()

if __name__=='__main__':
    if '--arm' in sys.argv:arm(sys.argv[sys.argv.index('--arm')+1],full='--full' in sys.argv)
    else:run()
