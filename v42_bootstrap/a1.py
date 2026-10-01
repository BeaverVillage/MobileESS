"""Isolated complete-May A1, exactly two scientific objective groups."""
import gc,re,sys,threading
from time import perf_counter
import gurobipy as gp,numpy as np,psutil
from v42_root.common import *
from v42_root.data import prepare
from v42_root.native import build
from v42_root.certify import certificate as old_certificate,dense_value
from v42_two.contract import *
from v42_native.voltage import Stage
from v42_two.reporting import reserve_metrics

def certificate(m,units,data,controls,bindings,legacy,dense,maxvio):
    cert,plan,ctrl,snap=old_certificate(m,units,data,controls,bindings,legacy,dense,maxvio)
    old=cert.pop('model_defined_scientific_objective_snapshot')
    cert['scientific_objective_snapshot']=dict(MAX_LINE_LOADING=old['rho'],MIN_INTERVENTION=dict(migration_count=old['migration_count'],shift_magnitude=sum(abs(o['start']-data[1][u].reference_start) for u,o in plan.items()),prestart_relocation=old['prestart_changes']))
    cert['report_only_metrics']=dict(raw_reserve_shortfall=old['reserve_shortfall'],CC4_reference_deviation=old['CC4_reference_deviation'])
    cert['reserve_shortfall_semantics']='Unoptimized soft reliability auxiliary; not an objective, a zero-shortfall hard constraint, or an electrical certificate'
    return cert,plan,ctrl,snap


def check_sources():
    frozen()
    manifest=read(OUT/'SOURCE_MANIFEST.json')
    for row in manifest['sources']:
        if sha(ROOT/row['path'])!=row['sha256']:raise ValueError('FINAL_SOURCE_DRIFT:'+row['path'])
    if sha(OUT/'PREREGISTRATION.json')!=manifest['preregistration_sha256']:raise ValueError('PREREGISTRATION_DRIFT')


def run(mode):
    check_sources()
    folder=LOCAL/mode;folder.mkdir(parents=True,exist_ok=True)
    marker=folder/'STARTED.json'
    if marker.exists():raise ValueError('NO_RETRY:'+mode)
    atomic(marker,dict(mode=mode,one_run=True))
    print('FULL MAY BUILD',mode,flush=True)
    class CaseContext(Context):
        def __init__(self):self.folder=folder
    data=prepare()
    m,units,legacy,controls,bindings=build(CaseContext(),data,'F2-CRA');m.update();m._two_caps=data[3].capacities
    dump('A1_BOOTSTRAP_MODEL_STATS.json',read(OUT/'F2-CRA_MODEL_STATS.json'))
    before=dict(columns=m.NumVars,rows=m.NumConstrs,nonzeros=m.NumNZs,binaries=m.NumBinVars,integers=m.NumIntVars-m.NumBinVars,fingerprint=hex(m.Fingerprint))
    groups=aidc_groups(legacy,units,data);m.update()
    after=dict(columns=m.NumVars,rows=m.NumConstrs,nonzeros=m.NumNZs,binaries=m.NumBinVars,integers=m.NumIntVars-m.NumBinVars,fingerprint=hex(m.Fingerprint))
    expected=read(ROOT/'docs/v42_root_lp_sparse_compression/F2-CRA_MODEL_STATS.json')
    assert before==after and all(before[k]==expected[v] for k,v in [('columns','columns'),('rows','constraints'),('nonzeros','nonzeros'),('binaries','binaries'),('integers','integers')])
    assert len(data[1])==1499 and not any([m.NumQConstrs,m.NumQNZs,m.NumSOS,m.NumGenConstrs])
    starts=[s-data[1][unit['uid']].reference_start for unit in units for site,s in unit['v']['y']]
    dump('PHYSICAL_DOMAIN_REGRESSION.json',dict(PASS=True,before=before,after=after,PR103_counts_match=True,authorized_stage_authority_change=True,jobs=1499,classes=len(data[-1]['classes']),input_cache_sha256=sha(LOCAL/'DATA.pkl'),voltage_RHS_only_change=True,minimum_start_displacement=min(starts),magnitude_equals_inherited_signed_shift=min(starts)>=0,non_voltage_rows_bounds_types_unchanged=True))
    dump('P1_FORMULATION_RECEIPT.json',dict(PASS=True,formulation='F2-CRA',P1_same_scalar_object=groups[0].components[0][1].sameAs(legacy[0][1]),domain=before,voltage_stage='A1',hard_voltage_transformer_preserved=True))
    reference=None
    # Inherited validation completes the source on a separate model copy. It
    # never fixes or restricts the production model's integer decisions.
    import v42_root.start as start_module
    start_module.LOCAL=folder;start_module.certificate=certificate
    source=read(ROOT.parent/'V42_ROOT_SPARSE_LOCAL/P1_ACCEPTED_A1.json')['physical'] if mode=='diagnostic' else read(ROOT.parent/'V42_ROOT_SPARSE_LOCAL/REFERENCE_PLAN.json')
    atomic(folder/'REFERENCE_PLAN.json',source)
    start_receipt=start_module.validate_source(m,units,data,controls,bindings,legacy)
    start_receipt['authority']='PR103 certified P1 physical plan' if mode=='diagnostic' else 'PR103 native reference plan'
    start_receipt['source_plan_sha256']=sha(folder/'REFERENCE_PLAN.json')
    dump('A1_MIP_START_RECEIPT.json',start_receipt);check_sources()
    chosen=passes(groups)
    m.Params.Threads=1;m.Params.Seed=20260929;m.Params.MIPGap=.005;m.Params.OutputFlag=1
    logfile=folder/'GUROBI.log';m.Params.LogFile=str(logfile)
    spent=0.;rows=[];telemetry=[];first_per={};peak=[psutil.Process().memory_info().rss]
    stop=threading.Event()
    def sample():
        proc=psutil.Process()
        while not stop.wait(.5):peak[0]=max(peak[0],proc.memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start();cert=None;report=None
    try:
        for group,component,expr in chosen:
            if 3600-spent<=0:break
            m.setObjective(expr);m.Params.TimeLimit=3600-spent;m.update();begin=perf_counter();last=[-10.];messages=[]
            atomic(folder/'ACTIVE.json',dict(group=group,component=component,spent_seconds=spent,remaining=3600-spent))
            def cb(model,where):
                elapsed=perf_counter()-begin;state={}
                if where==gp.GRB.Callback.MESSAGE:
                    messages.append(model.cbGet(gp.GRB.Callback.MSG_STRING));return
                if where==gp.GRB.Callback.MIPSOL:
                    if component not in first_per:first_per[component]=elapsed
                    state=dict(phase='INCUMBENT',incumbent=clean(model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)),bound=clean(model.cbGet(gp.GRB.Callback.MIPSOL_OBJBND)),nodes=model.cbGet(gp.GRB.Callback.MIPSOL_NODCNT))
                elif where==gp.GRB.Callback.MIP:state=dict(phase='MIP',incumbent=clean(model.cbGet(gp.GRB.Callback.MIP_OBJBST)),bound=clean(model.cbGet(gp.GRB.Callback.MIP_OBJBND)),nodes=model.cbGet(gp.GRB.Callback.MIP_NODCNT))
                elif where==gp.GRB.Callback.SIMPLEX:state=dict(phase='SIMPLEX',iterations=model.cbGet(gp.GRB.Callback.SPX_ITRCNT),simplex_objective=model.cbGet(gp.GRB.Callback.SPX_OBJVAL),primal_infeasibility=model.cbGet(gp.GRB.Callback.SPX_PRIMINF),dual_infeasibility=model.cbGet(gp.GRB.Callback.SPX_DUALINF))
                elif where==gp.GRB.Callback.PRESOLVE:state=dict(phase='PRESOLVE')
                if state and (elapsed-last[0]>=5 or where==gp.GRB.Callback.MIPSOL):
                    row=clean(dict(scientific_group=group,component=component,elapsed_component_seconds=elapsed,elapsed_optimize_seconds=spent+elapsed,RSS_bytes=psutil.Process().memory_info().rss,**state));telemetry.append(row);atomic(folder/'PROGRESS.json',row);last[0]=elapsed
            m.optimize(cb);wall=perf_counter()-begin;spent+=wall
            log=''.join(messages);root=re.search(r'Root relaxation: objective ([\deE+.-]+), (\d+) iterations, ([\d.]+) seconds',log)
            presolve=re.search(r'Presolve time: ([\d.]+)s',log);presolved=re.search(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
            inc=m.ObjVal if m.SolCount else None;bound=m.ObjBound
            row=clean(dict(scientific_group=group,component=component,status=m.Status,incumbent=inc,bound=bound,
                relative_gap=relative_gap(inc,bound),solver_gap=m.MIPGap if m.SolCount else None,integer_exact_certificate=integer_certificate(inc,bound) if group==P2_NAME else None,
                native_runtime_seconds=m.Runtime,optimize_wall_seconds=wall,nodes=m.NodeCount,first_incumbent_seconds=first_per.get(component),
                presolve_seconds=float(presolve[1]) if presolve else None,
                presolved=dict(rows=int(presolved[1]),columns=int(presolved[2]),nonzeros=int(presolved[3])) if presolved else None,
                root=dict(objective_rounded=float(root[1]),iterations=int(root[2]),seconds=float(root[3])) if root else None,
                start_messages=[line.strip() for line in log.splitlines() if 'MIP start' in line],warnings=[line.strip() for line in log.splitlines() if 'Warning' in line]))
            rows.append(row);atomic(folder/'PARTIAL_RESULT.json',dict(passes=rows,total_optimize_seconds=spent))
            if not m.SolCount:break
            # Independent validation and reporting lie outside optimize budget.
            dense=np.asarray(m.getAttr('X'),dtype=float)
            cert,plan,ctrl,snap=certificate(m,units,data,controls,bindings,legacy,dense,m.MaxVio)
            atomic(folder/'PHYSICAL_VALIDATION.json',cert);atomic(folder/'SELECTED_PHYSICAL.json',plan);atomic(folder/'CONTROLS.json',ctrl)
            np.save(folder/'FINAL_X.npy',dense)
            report=reserve_metrics(m,dense);atomic(folder/'RESERVE_REPORT.json',report)
            from .grid import grid_report
            dump('A1_BOOTSTRAP_VOLTAGE_REPORT.json',grid_report(data[0],ctrl,cert['P1_rho'],stage=Stage.A1))
            if not cert['PASS'] or m.Status!=gp.GRB.OPTIMAL:break
            if component=='rho':
                reference=inc
                lock=m.addConstr(expr<=inc+P1_EPS,name='current_margin_A1_P1_lock');m.update()
                assert m.getRow(lock).size()==1
            elif len(rows)<len(chosen):m.addConstr(expr<=inc+COMPONENT_EPS,name='P2_component_lock_'+component)
    finally:stop.set();th.join(timeout=1)
    complete=len(rows)==len(chosen) and all(row['status']==gp.GRB.OPTIMAL for row in rows) and bool(cert and cert['PASS'])
    receipt=dict(mode=mode,A1_BOOTSTRAP_ACCEPTED=complete,FINAL_ROBUST_PLANNING_ACCEPTED=False,voltage_band=[.95,1.05],scientific_objective_count=2,scientific_groups=[P1_NAME,P2_NAME],passes=rows,
        total_optimize_seconds=spent,complete=complete,physical_PASS=bool(cert and cert['PASS']),peak_RSS_bytes=peak[0],
        settings=read(OUT/'PREREGISTRATION.json')['solver'],start=start_receipt,
        P1_lock=reference+P1_EPS if reference is not None else None,P1_lock_tolerance=P1_EPS,P1_replayed=mode=='replay',
        reserve_optimized=False,CC4_deviation_optimized=False,deterministic_rank_optimized=False,
        reporting={k:v for k,v in (report or {}).items() if k!='rows'},CC4_deviation=cert['report_only_metrics']['CC4_reference_deviation'] if cert else None)
    filename='A1_BOOTSTRAP_OPTIMIZATION.json'
    dump(filename,receipt)
    if mode=='replay':
        dump('A1_BOOTSTRAP_PHYSICAL_VALIDATION.json',cert or dict(PASS=False,status='NO_INCUMBENT'))
        if telemetry:
            keys=sorted(set().union(*(row.keys() for row in telemetry)));table('A1_PROGRESS.csv',[{k:r.get(k) for k in keys} for r in telemetry])
        if report:table('RESERVE_SITE_TIME_REPORT.csv',report['rows'])
    if complete:
        from .handoff import materialize
        materialize(m,data,bindings,controls,plan,cert,receipt)
    else:
        dump('A1_TO_M1_HANDOFF.json',dict(accepted=False,status='A1_NOT_ACCEPTED',M1_RUN=False))
    if rows and rows[-1]['status']==gp.GRB.INFEASIBLE:
        dump('A1_INFEASIBILITY_DIAGNOSIS.json',dict(status='PROVEN_INFEASIBLE',band=[.95,1.05],margin_relaxed=False,job_domain_reduced=False,solver_log=str(logfile),IIS_RUN=False))
    atomic(folder/'FINISHED.json',dict(complete=complete,spent_seconds=spent));m.dispose();check_sources();print('BOOTSTRAP A1 RESULT',complete,rows,flush=True)

if __name__=='__main__':
    if len(sys.argv)!=1:raise ValueError('One tightened A1 only')
    run('replay')
