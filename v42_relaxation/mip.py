"""Exactly one gated proof canary and at most one cumulative production."""
import re
from .base import *
from .strengthening import hook,extension_values

def run(kind):
    assert kind in ('canary','production')
    selection=read(OUT/'SELECTED_STRENGTHENING.json')
    assert selection['frozen'] and selection['canary_authorized']
    if kind=='production':assert read(OUT/'PRODUCTION_AUTHORIZATION.json')['authorized']
    label=selection['selected'];prefix='MIP_CANARY' if kind=='canary' else 'M1_PRODUCTION'
    assert not (LOCAL/(prefix+'_STARTED.json')).exists(), 'NO_MIP_RETRY'
    holder={};records=[];rows=[];saved={};limit=600 if kind=='canary' else 1800
    def optimize(m,objectives,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings,evaluate
        from v42_two.contract import mess_groups,passes,P1_EPS,COMPONENT_EPS
        bundle,anchor,prior,sites,initial,routes,battery=data
        values=prior['values'].copy();m.setObjective(objectives[0][1]);m.update();map_bindings(bindings,values)
        values=extension_values(values,holder['context'],holder['G']);matrix_validate(m,values)
        m.setAttr('Start',[values[n] for n in m.getAttr('VarName')]);m.update();matrix=stats(m)
        settings=read(OUT/'PREREGISTRATION.json')['MIP'].copy();settings.pop('GPU')
        for name,value in settings.items():setattr(m.Params,name,value)
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(LOCAL/(prefix+'.log'))
        assert m.Params.NodeLimit>1e90
        chosen=passes(mess_groups(objectives)) if kind=='production' else [('MAX_LINE_LOADING','rho',objectives[0][1])]
        process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event();active={};state={};spent=0.;messages=[]
        def sample():
            while not stop.wait(5):
                peak[0]=max(peak[0],process.memory_info().rss)
                if 'begin' not in active:continue
                elapsed=perf_counter()-active['begin'];observed=state.get('observed_seconds')
                row=dict(component=active['component'],component_seconds=elapsed,optimize_seconds=active['spent']+elapsed,
                    RSS_bytes=process.memory_info().rss,observation_age_seconds=elapsed-observed if observed is not None else None,**state)
                rows.append(row)
                (LOCAL/(prefix+'_PROGRESS.json')).write_text(json.dumps(row,allow_nan=False),encoding='utf8')
        thread=threading.Thread(target=sample,daemon=True);thread.start()
        (LOCAL/(prefix+'_STARTED.json')).write_text(json.dumps(dict(selected=label,seconds=limit)))
        best=None
        try:
            for group,component,obj in chosen:
                if spent>=limit:break
                m.setObjective(obj);m.Params.TimeLimit=limit-spent;m.update();begin=perf_counter();first=[None];errors=[]
                active.update(begin=begin,component=component,spent=spent);state.clear()
                def number(value):return float(value) if abs(value)<1e90 else None
                def callback(model,where):
                    now=perf_counter()-begin
                    try:
                        if where==gp.GRB.Callback.MESSAGE:messages.append(model.cbGet(gp.GRB.Callback.MSG_STRING))
                        elif where in (gp.GRB.Callback.MIP,gp.GRB.Callback.MIPSOL):
                            sol=where==gp.GRB.Callback.MIPSOL
                            inc=number(model.cbGet(gp.GRB.Callback.MIPSOL_OBJBST if sol else gp.GRB.Callback.MIP_OBJBST))
                            bound=number(model.cbGet(gp.GRB.Callback.MIPSOL_OBJBND if sol else gp.GRB.Callback.MIP_OBJBND))
                            nodes=model.cbGet(gp.GRB.Callback.MIPSOL_NODCNT if sol else gp.GRB.Callback.MIP_NODCNT)
                            if sol and first[0] is None:first[0]=dict(seconds=now,objective=number(model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)))
                            state.update(phase='MIPSOL' if sol else 'MIP',observed_seconds=now,incumbent=inc,bound=bound,
                                gap=(inc-bound)/abs(inc) if inc is not None and bound is not None and inc else None,nodes=nodes)
                        elif where==gp.GRB.Callback.BARRIER:state.update(phase='BARRIER',observed_seconds=now)
                        elif where==gp.GRB.Callback.SIMPLEX:state.update(phase='SIMPLEX',observed_seconds=now)
                    except Exception as e:errors.append(str(e));model.terminate()
                m.optimize(callback);wall=perf_counter()-begin;spent+=wall;active.clear()
                assert not errors, errors
                inc=m.ObjVal if m.SolCount else None;bound=m.ObjBound
                gap=(inc-bound)/abs(inc) if inc is not None and inc else 0. if inc==bound==0 else None
                quality=bool(gap is not None and gap<=.005+1e-12)
                records.append(dict(group=group,component=component,status=m.Status,incumbent=inc,bound=bound,gap=gap,
                    quality_PASS=quality,seconds=wall,native_seconds=m.Runtime,nodes=m.NodeCount,first_incumbent=first[0]))
                rows.append(dict(component=component,component_seconds=wall,optimize_seconds=spent,phase='FINAL',
                    observed_seconds=wall,observation_age_seconds=0.,incumbent=inc,bound=bound,gap=gap,nodes=m.NodeCount,RSS_bytes=process.memory_info().rss))
                if m.SolCount:
                    vv=dict(zip(m.getAttr('VarName'),m.getAttr('X')));best=dict(values=vv,
                        objectives=[evaluate(e,vv) for _,_,e in chosen],scientific_objective_count=2)
                    saved.update(values=vv,controls=[[evaluate(e,vv) for e in row] for row in controls])
                if not quality or kind=='canary':break
                if component=='movement_count':
                    from v42_two.contract import integer_certificate
                    records[-1]['integer_exact_certificate']=integer_certificate(inc,bound)
                if len(records)<len(chosen):m.addConstr(obj<=inc+(P1_EPS if component=='rho' else COMPONENT_EPS),name='M1_lock_'+component)
        finally:stop.set();thread.join(1)
        log=''.join(messages);root=re.findall(r'Root relaxation: objective ([\deE+.-]+), (\d+) iterations, ([\d.]+) seconds',log)
        receipt=dict(run=True,kind=kind,selected=label,passes=records,total_optimize_seconds=spent,
            peak_RSS_bytes=peak[0],matrix=matrix,settings=dict(settings,TimeLimit=limit,NodeLimit=None,GPU=False),
            root_LP=dict(bound=float(root[0][0]),iterations=int(root[0][1]),seconds=float(root[0][2])) if root else None,
            complete=kind=='production' and len(records)==3 and all(r['quality_PASS'] for r in records),
            MIP_start_accepted=bool(re.search(r'(Loaded user MIP start|User MIP start produced solution) with objective',log)),
            cuts_by_family=[s.strip() for s in log.splitlines() if re.match(r'\s+(Gomory|MIR|Flow cover|Zero half|RLT|Implied bound|Clique|Cover|StrongCG|Mod-K|Relax-and-lift|Mixing|BQP):',s)])
        dump(prefix+'_OPTIMIZATION.json',receipt)
        fields=sorted(set().union(*(r.keys() for r in rows)));table(prefix+'_PROGRESS.csv',[{k:r.get(k) for k in fields} for r in rows])
        (OUT/(prefix+'_SOLVER.display.txt')).write_text(log,encoding='utf8')
        (OUT/(prefix+'_SOLVER.raw.gz')).write_bytes(gzip.compress(log.encode(),mtime=0))
        return best,receipt
    best,receipt=build(optimize,hook(label,holder,
        compact_energy_bounds=label=='S3' and selection.get('S3_implied_compact_G_bounds',False)))
    assert best is not None, 'VALIDATED_MIP_START_DID_NOT_SURVIVE'
    bundle,anchor,prior,sites,initial,routes,battery=inputs()
    from v42_native.mess import validate
    from v42_bootstrap.attribution import supplemental_physical
    from v42_bootstrap.grid import grid_report
    physical=validate(best,sites,routes,battery,96);extra=supplemental_physical(best,sites,battery)
    physical.update(extra,initial_SOC_PASS=all(abs(best['values'][f'SOC[{u},0]']-battery.initial)<=TOL for u in initial))
    physical['PASS']=physical['PASS'] and extra['charge_mode_and_connection_PASS'] and physical['initial_SOC_PASS']
    grid=grid_report(bundle,saved['controls'],best['values']['rho_max'])
    anchor_pass=all(saved['controls'][t][i]==anchor['controls'][t][i] for t in range(96) for i in anchor['fixed_AIDC_control_columns'])
    assert anchor_pass and best['domain_sha256']==prior['domain_sha256']
    dump(prefix+'_PHYSICAL_VALIDATION.json',physical);dump(prefix+'_ROBUST_VOLTAGE_REPORT.json',grid)
    (LOCAL/(prefix+'_PLAN.json')).write_text(json.dumps(best,allow_nan=False),encoding='utf8')
    qrows=[]
    for u in initial:
        for t in range(96):
            for s in sites:
                if best['values'][f'arc[{u},{sites.index(s)*96+t}]']<.5:continue
                p=best['values'][f'Pdis[{u},{s},{t}]']-best['values'][f'Pch[{u},{s},{t}]'];q=best['values'][f'Q[{u},{s},{t}]']
                qrows.append(dict(MESS=u,time=t,site=s,P=p,Q=q,Q_utilization=abs(q)/np.sqrt(max(battery.pcs_kva**2-p*p,0.)),diagnostic_only=True))
    table(prefix+'_Q_UTILIZATION.csv',qrows)
    if kind=='canary':
        p=receipt['passes'][0];gain=p['bound']-LB
        gate=dict(authorized=gain>=.005 or p['gap']<=.12 or p['quality_PASS'],BestBd_gain=gain,
            relative_gap=p['gap'],certified_P1=p['quality_PASS'],thresholds=dict(bound_gain=.005,gap=.12,certified_gap=.005))
        dump('PRODUCTION_AUTHORIZATION.json',gate)
    else:
        dump('M1_PHYSICAL_VALIDATION.json',physical);dump('M1_ROBUST_VOLTAGE_REPORT.json',grid)
        table('M1_Q_UTILIZATION.csv',qrows)
    print('MIP COMPLETE',kind,receipt,flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['canary','production']);a=p.parse_args();run(a.kind)
