"""One native M1 with constant AIDC controls and an optimize-only budget."""
import gzip,re,threading
from collections import Counter
from dataclasses import asdict
from time import perf_counter
import gurobipy as gp
import psutil
from v42_root.common import *
from v42_root.data import prepare
from v42_native.contracts import require
from v42_native.mess import Battery,RouteArc
from v42_native.solver import assert_milp
from v42_native.voltage import authority_sha,Stage
from v42_two.contract import mess_groups,passes,P1_EPS,COMPONENT_EPS,relative_gap,integer_certificate
from .grid import frozen_grid,grid_report
from .handoff import validate_handoff


class OptimizeOnlyBudget:
    stage='M1'
    seconds=1800.
    spent=0.
    @property
    def remaining(self):return max(0.,self.seconds-self.spent)
    def check(self):require(self.remaining>0,'M1_OPTIMIZE_BUDGET_EXHAUSTED')


def native_inputs(bundle):
    expected=bundle['route_table'];path=Path(expected['path'])
    require(path.is_file() and sha(path)==expected['sha256'],'NATIVE_ROUTE_SHA_MISMATCH_OR_MISSING')
    table=json.loads(gzip.decompress(path.read_bytes()));routes=[];excluded=Counter()
    for r in table['routes']:
        require(r['traffic_forecast_sha']==bundle['traffic_forecast_sha'],'NATIVE_ROUTE_FORECAST_DRIFT')
        s,d,t=r['origin_service_id'],r['destination_service_id'],r['departure_slot_15']
        arrive=t+r['travel_slots_15min'];connect=t+r['connection_ready_slots_15min']
        if s==d:excluded['same_site_represented_by_stay']+=1;continue
        if not 0<=t<arrive<=connect<96:excluded['outside_inherited_RouteArc_time_contract']+=1;continue
        routes.append(RouteArc(f'{s}:{d}:{t}',s,d,t,arrive,connect,r['energy_safe_kwh'],digest(r)))
    b=Battery(**bundle['battery']);b.validate()
    require(len(bundle['initial_MESS_sites'])==4 and len(table['service_ids'])==24,'NATIVE_MESS_CASE_STUDY_AXIS')
    receipt=dict(route_file=expected,excluded=dict(excluded),accepted_routes=len(routes),
                 battery=asdict(b),initial_MESS_sites=bundle['initial_MESS_sites'],sites=table['service_ids'],
                 native=True,synthetic=False,PR101_head='f536e65fc7fb968c52e99e4a5b017953edc53744',
                 PR101_wholesale_merge=False,PR101_code_ported=False,
                 audit='Current PR104 constructor already preserves joint route/P/Q/SOC, exact forward reachability, inner16, travel energy and terminal SOC. PR101 native route reduction not material; no extra prescreen port needed for one M1.',
                 M1_MIP_START_AVAILABLE=False,M1_start_reason='No accepted MESS plan bound to this new A1 anchor and voltage authority; old A1 zero P/Q is not a MESS reference plan')
    return tuple(table['service_ids']),bundle['initial_MESS_sites'],tuple(routes),b,receipt


def run():
    from .a1 import check_sources
    check_sources();anchor=read(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json');handoff=read(OUT/'A1_TO_M1_HANDOFF.json')
    validate_handoff(handoff,anchor)
    folder=LOCAL/'M1';folder.mkdir(exist_ok=True)
    if (folder/'STARTED.json').exists():raise ValueError('NO_RETRY:M1')
    data=prepare();bundle=data[0];sites,initial,routes,battery,input_receipt=native_inputs(bundle)
    from .preflight import preflight
    gate=preflight(data,anchor,sites,initial,routes,battery)
    if not gate["PASS"]:
        print("M1 STOP: EXACT NECESSARY CONDITION FAILED",flush=True);return
    dump('M1_PREFLIGHT.json',dict(**gate,A1_accepted=True,A1_anchor_digest=digest(anchor),
                                M1_AIDC_decision_variables=0,route_P_Q_SOC_joint=True,voltage_authority_sha256=authority_sha(),**input_receipt))
    atomic(folder/'STARTED.json',dict(one_native_M1=True,optimize_budget=1800,anchor_digest=digest(anchor)))
    budget=OptimizeOnlyBudget();control_handles=[];telemetry=[];receipts=[];first={};model_stats={};chosen_values=None
    process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event()
    def sample():
        while not stop.wait(.5):peak[0]=max(peak[0],process.memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start()
    def builder(m,p,q):
        levels,ctrl=frozen_grid(m,bundle,anchor,p,q);control_handles.extend(ctrl)
        return levels
    def optimizer(m,legacy,deadline,incumbent=None,**kwargs):
        nonlocal chosen_values
        require(incumbent is None,'UNVALIDATED_M1_START');stats=assert_milp(m)
        families=Counter(v.VarName.split('[')[0] for v in m.getVars())
        require(set(families)<= {'arc','charge_mode','Pch','Pdis','Q','SOC','rho_max'},'AIDC_DECISION_VARIABLES_IN_M1')
        model_stats.update(stats,family_columns=dict(families),AIDC_decision_variables=0,
                           grid_rows=sum(n for k,n in stats['constraint_families'].items() if k.startswith(('voltage_','line_thermal','transformer_'))),
                           voltage_rows=sum(n for k,n in stats['constraint_families'].items() if k.startswith('voltage_')),
                           PCS_rows=stats['constraint_families'].get('PCS16',0),peak_RSS_bytes=peak[0])
        stay_limit=len(sites)*96
        model_stats.update(stay_columns=sum(int(v.VarName.split(',')[-1][:-1])<stay_limit for v in m.getVars() if v.VarName.startswith('arc[')),
                           route_columns=sum(int(v.VarName.split(',')[-1][:-1])>=stay_limit for v in m.getVars() if v.VarName.startswith('arc[')),
                           flow_rows=stats['constraint_families'].get('flow',0),SOC_rows=sum(stats['constraint_families'].get(k,0) for k in ('initial_SOC','terminal_SOC','energy_balance')))
        dump('M1_MODEL_STATS.json',model_stats)
        dump('M1_VOLTAGE_AUTHORITY_RECEIPT.json',dict(PASS=True,authority_sha256=authority_sha(),voltage_rows=model_stats['voltage_rows'],
                                                  stage='M1',A1_anchor_authority_sha256=authority_sha(Stage.A1),AIDC_anchor_digest=digest(anchor)))
        m.Params.Threads=1;m.Params.Seed=20260929;m.Params.MIPGap=.005;m.Params.OutputFlag=1;m.Params.LogFile=str(folder/'GUROBI.log')
        groups=mess_groups(legacy);chosen=passes(groups);best=None;next_snapshot=[60]
        for group,component,expr in chosen:
            if deadline.remaining<=0:break
            m.setObjective(expr);m.Params.TimeLimit=deadline.remaining;m.update();begin=perf_counter();messages=[];last=[-10.]
            atomic(folder/'ACTIVE.json',dict(component=component,spent_seconds=deadline.spent,remaining_seconds=deadline.remaining))
            def callback(model,where):
                elapsed=perf_counter()-begin;state={}
                if where==gp.GRB.Callback.MESSAGE:messages.append(model.cbGet(gp.GRB.Callback.MSG_STRING));return
                if where==gp.GRB.Callback.MIPSOL:
                    first.setdefault(component,elapsed)
                    state=dict(phase='INCUMBENT',incumbent=clean(model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)),bound=clean(model.cbGet(gp.GRB.Callback.MIPSOL_OBJBND)),nodes=model.cbGet(gp.GRB.Callback.MIPSOL_NODCNT))
                elif where==gp.GRB.Callback.MIP:state=dict(phase='MIP',incumbent=clean(model.cbGet(gp.GRB.Callback.MIP_OBJBST)),bound=clean(model.cbGet(gp.GRB.Callback.MIP_OBJBND)),nodes=model.cbGet(gp.GRB.Callback.MIP_NODCNT))
                elif where==gp.GRB.Callback.SIMPLEX:state=dict(phase='SIMPLEX',iterations=model.cbGet(gp.GRB.Callback.SPX_ITRCNT),primal_infeasibility=model.cbGet(gp.GRB.Callback.SPX_PRIMINF),dual_infeasibility=model.cbGet(gp.GRB.Callback.SPX_DUALINF))
                elif where==gp.GRB.Callback.PRESOLVE:state=dict(phase='PRESOLVE')
                if state and (elapsed-last[0]>=5 or where==gp.GRB.Callback.MIPSOL):
                    row=clean(dict(group=group,component=component,component_seconds=elapsed,optimize_seconds=deadline.spent+elapsed,RSS_bytes=process.memory_info().rss,**state))
                    telemetry.append(row);atomic(folder/'PROGRESS.json',row);last[0]=elapsed
                    if row['optimize_seconds']>=next_snapshot[0]:
                        atomic(folder/f'SNAPSHOT_{next_snapshot[0]}.json',row)
                        next_snapshot[0]=next((s for s in [60,300,600,1200,1800] if s>row['optimize_seconds']),float('inf'))
            m.optimize(callback);wall=perf_counter()-begin;deadline.spent+=wall;log=''.join(messages)
            root=re.search(r'Root relaxation: objective ([\deE+.-]+), (\d+) iterations, ([\d.]+) seconds',log)
            presolve=re.search(r'Presolve time: ([\d.]+)s',log);presolved=re.search(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
            inc=m.ObjVal if m.SolCount else None;bound=m.ObjBound
            row=clean(dict(group=group,component=component,status=m.Status,incumbent=inc,bound=bound,relative_gap=relative_gap(inc,bound),
                           integer_exact_certificate=integer_certificate(inc,bound) if component=='movement_count' else None,
                           optimize_wall_seconds=wall,native_runtime_seconds=m.Runtime,nodes=m.NodeCount,first_incumbent_seconds=first.get(component),
                           presolve_seconds=float(presolve[1]) if presolve else None,
                           presolved=dict(rows=int(presolved[1]),columns=int(presolved[2]),nonzeros=int(presolved[3])) if presolved else None,
                           root=dict(bound_rounded=float(root[1]),iterations=int(root[2]),seconds=float(root[3])) if root else None,
                           warnings=[x.strip() for x in log.splitlines() if 'Warning' in x]))
            receipts.append(row);atomic(folder/'PARTIAL_RESULT.json',dict(passes=receipts,total_optimize_seconds=deadline.spent))
            if not m.SolCount:break
            chosen_values=m.getAttr('X');names=m.getAttr('VarName');vals=dict(zip(names,chosen_values))
            best=dict(values=vals,objectives=[value(x) for _,_,x in chosen],scientific_objective_count=2)
            atomic(folder/'INCUMBENT.json',best)
            ctrl=[[value(x) for x in r] for r in control_handles]
            fixed_error=max(abs(ctrl[t][i]-anchor['controls'][t][i]) for t in range(96) for i in anchor['fixed_AIDC_control_columns'])
            require(fixed_error==0,'M1_AIDC_ANCHOR_CHANGED');dump('M1_ROBUST_VOLTAGE_REPORT.json',grid_report(bundle,ctrl,vals['rho_max'],stage=Stage.M1))
            atomic(folder/'CONTROLS.json',ctrl)
            if m.Status!=gp.GRB.OPTIMAL:break
            if len(receipts)<len(chosen):m.addConstr(expr<=inc+(P1_EPS if component=='rho' else COMPONENT_EPS),name='M1_lock_'+component)
        receipt=dict(passes=receipts,complete=len(receipts)==3 and all(r['status']==gp.GRB.OPTIMAL for r in receipts),
                     total_optimize_seconds=deadline.spent,peak_RSS_bytes=peak[0],settings=dict(Threads=1,Seed=20260929,MIPGap=.005,TimeLimit=1800,GPU=False,optimize_only=True),
                     MIP_start_available=False,scientific_objective_count=2,scientific_groups=['MAX_LINE_LOADING','MIN_INTERVENTION'],
                     reserve_optimized=False,CC4_optimized=False,tie_optimized=False)
        return best,receipt
    import v42_native.mess as native
    original=native.optimize;native.optimize=optimizer
    try:best,receipt=native.solve('M1',budget,sites,initial,routes,battery,96,builder)
    finally:native.optimize=original;stop.set();th.join(timeout=1)
    require(digest(read(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json'))==handoff['anchor_digest'],'M1_AIDC_ANCHOR_CHANGED')
    receipt['peak_RSS_bytes']=peak[0];model_stats.update(model_build_seconds=receipt['model_build_seconds'],peak_RSS_bytes=peak[0]);dump('M1_MODEL_STATS.json',model_stats)
    physical=best['physical_audit'] if best else dict(PASS=False,violations=['NO_INCUMBENT'])
    grid=read(OUT/'M1_ROBUST_VOLTAGE_REPORT.json') if best else dict(PASS=False)
    physical.update(grid_PASS=grid['PASS'],AIDC_anchor_unchanged=True,AIDC_decision_variables=0,initial_SOC_independently_checked=bool(best and all(abs(best['values'][f'SOC[{u},0]']-battery.initial)<=1e-5 for u in initial)))
    physical['PASS']=physical['PASS'] and grid['PASS'] and physical['initial_SOC_independently_checked']
    if best:
        from .attribution import supplemental_physical
        extra=supplemental_physical(best,sites,battery);physical.update(extra);physical['PASS']=physical['PASS'] and extra['charge_mode_and_connection_PASS']
    receipt.update(M1_ROBUST_ACCEPTED=receipt['complete'] and physical['PASS'],physical_PASS=physical['PASS'],accepted=receipt['complete'] and physical['PASS'],AIDC_anchor_digest=handoff['anchor_digest'])
    dump('M1_OPTIMIZATION.json',receipt);dump('M1_PHYSICAL_VALIDATION.json',physical)
    if telemetry:
        keys=sorted(set().union(*(r.keys() for r in telemetry)));table('M1_PROGRESS.csv',[{k:r.get(k) for k in keys} for r in telemetry])
    if best:
        atomic(folder/'FINAL_PLAN.json',best)
        values=best['values'];qvalues=[abs(v) for n,v in values.items() if n.startswith('Q[')]
        ratio=[v/battery.pcs_kva for v in qvalues]
        grid.update(Q_max_abs_kvar=max(qvalues),Q_near_PCS_fraction=sum(v>=.95 for v in ratio)/len(ratio),
                    Q_near_PCS_count=sum(v>=.95 for v in ratio),Q_column_count=len(qvalues))
        dump('M1_ROBUST_VOLTAGE_REPORT.json',grid)
    atomic(folder/'FINISHED.json',dict(accepted=receipt['accepted'],optimize_seconds=budget.spent,STOP_before_A2=True))
    from .attribution import analyze
    analyze(bundle,anchor,best,sites,routes,battery)
    check_sources();print('ONE NATIVE M1 FINISHED',receipt['accepted'],receipt['passes'],flush=True)


if __name__=='__main__':run()
