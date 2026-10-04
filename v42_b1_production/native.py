"""Per-day namespaces around the accepted PR133 A1 equations/certificates."""
import ast
import inspect
import types
from pathlib import Path
from types import SimpleNamespace
from .common import *


def date_route(function):
    source = ast.parse(inspect.getsource(function))
    class Route(ast.NodeTransformer):
        def visit_Constant(self, node):
            if node.value == '2025-05-01T00:00:00+10:00':
                return ast.copy_location(ast.parse("bundle['day']+'T00:00:00+10:00'", mode='eval').body, node)
            return node
    tree = Route().visit(source); ast.fix_missing_locations(tree)
    ns = dict(function.__globals__)
    exec(compile(tree, inspect.getfile(function), 'exec'), ns)
    return ns[function.__name__]


def bind(bundle, output):
    import pandas as pd
    import numpy as np
    from v42_b0_production.c1_binding import bind_frozen_c1
    from v42_holdout.common import source_freeze
    bind_frozen_c1(source_freeze())
    import v42_root.common as common
    common.OUT = output; common.LOCAL = output
    import v42_root.data as data
    import v42_root.native as native
    import v42_root.certify as certify
    import v42_boundary.model as boundary
    import v42_temporal.native as temporal
    import v42_exact.validation as validation
    import v42_bootstrap.grid as grid
    import v42_may01.prepare as original
    common.OUT = data.OUT = native.OUT = certify.OUT = output
    common.LOCAL = data.LOCAL = native.LOCAL = output
    if not hasattr(original,'_v42_b1_original_native_coefficients'):
        original._v42_b1_original_native_coefficients=original.native_coefficients
    pristine=original._v42_b1_original_native_coefficients
    function = types.FunctionType(pristine.__code__, dict(pristine.__globals__, DAY=bundle['day']))
    cert = read(bundle['electrical_certificate']['path']); coefficients = function(cert)
    folder = Path(bundle['current_day_folder'])
    table = pd.read_csv(folder / 'C1_PLANNING_COEFFICIENTS.csv')
    power = {(r.aidc_id,int(r.slot)): SimpleNamespace(slope=float(r.slope), intercept_kw=float(r.intercept_kw))
             for r in table.itertuples(index=False)}
    authority = read(folder / 'POWER_AUTHORITY.json')
    def load_power(_bundle):
        if _bundle['day'] != bundle['day']: raise ValueError('PER_DAY_NATIVE_NAMESPACE_DRIFT')
        return cert, power, authority['current_IT_idle_kW_per_installed_GPU'], authority['current_IT_swing_kW_per_active_GPU']
    temporal.load_power = boundary.load_power = load_power
    temporal.native_coefficients = boundary.native_coefficients = original.native_coefficients = lambda _cert: coefficients
    boundary.planning_grid = date_route(boundary.planning_grid)
    boundary.planning_grid.__globals__.update(load_power=load_power, native_coefficients=lambda _cert: coefficients,OLD=output)
    import v42_compact.native as compact
    compact.frozen_a1_grid = boundary.planning_grid
    # The accepted certificate reconstructs per-day C0/Runtime/physical bindings.
    validation.check = date_route(validation.check)
    certify.check = validation.check
    grid.coefficients = lambda _bundle: (cert, coefficients)
    def load_native():
        ledger = {r['job_id']: dict(can_timeshift=r['can_timeshift'], TS_slots=r['latest_start']-r['reference_start'])
                  for r in bundle['source_window_audit']}
        # Route hashes only, never substitute another date's input bytes.
        temporal.OLD = output
        atomic(output / 'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json', bundle)
        import shutil
        shutil.copyfile(ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv', output/'CC4_EXECUTION_LAG_KERNEL.csv')
        temporal.OUT = ROOT / 'docs/v42_ts_cc4_temporal_refinement'
        jobs,bounds,seconds,resources,raw = temporal.native_jobs(bundle,ledger)
        from dataclasses import replace
        windows = {r['job_id']: r for r in bundle['source_window_audit']}
        for uid in bounds:
            bounds[uid] = replace(bounds[uid], allowed_starts=tuple(windows[uid]['allowed_starts']))
        return bundle,jobs,bounds,seconds,resources,raw
    data.load_native = load_native
    boundary.OLD = output
    return data, native, certify, coefficients, authority


def run_a1(bundle, output, live_path):
    import time
    import numpy as np
    import gurobipy as gp
    from v42_integrated.contract import physical_authority, all_transformer_rows, grid_audit, evaluate
    from v42_two.contract import passes, aidc_groups, P1_EPS, COMPONENT_EPS
    data_module,native,certify,coefficients,power = bind(bundle,output)
    with physical_authority():
        data = data_module.prepare()
        import v42_boundary.model as boundary
        original = boundary.add_grid
        boundary.add_grid = all_transformer_rows(original)
        boundary.planning_grid.__globals__['add_grid']=boundary.add_grid
        class Context:
            folder = output
            def check(self):
                if (output.parent/'CANCEL.json').exists(): raise InterruptedError('RESOURCE_HARD_GUARD')
            def progress(self, value):
                self.check()
                atomic(live_path, dict(value, phase='MODEL_BUILD', elapsed=time.monotonic()-start))
        start = time.monotonic()
        try: model,units,levels,controls,bindings = native.build(Context(),data,'F2-CRA')
        finally:
            boundary.add_grid = original
            boundary.planning_grid.__globals__['add_grid']=original
        rows=[]; spent=0.; selected=None; values=None; physical=None; last=[0.]
        model.Params.Method=1; model.Params.Threads=1; model.Params.MIPGap=.005; model.Params.Seed=20260929
        model.Params.OutputFlag=1; model.Params.LogToConsole=0; model.Params.LogFile=str(output/'A1_SOLVE.log')
        for group,name,expression in passes(aidc_groups(levels,units,data)):
            remaining=1800-spent
            if remaining <= 0: break
            model.setObjective(expression); model.Params.TimeLimit=remaining
            def callback(m, where):
                if (output.parent/'CANCEL.json').exists():
                    m.terminate(); return
                if where == gp.GRB.Callback.POLLING: return
                runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME))
                if runtime-last[0] < 1: return
                last[0]=runtime
                value=dict(phase=name,solver_status='OPTIMIZING',elapsed=spent+runtime,
                           incumbent=None,BestBd=None,gap=None,node_count=None)
                if where == gp.GRB.Callback.MIP:
                    incumbent=float(m.cbGet(gp.GRB.Callback.MIP_OBJBST)); bound=float(m.cbGet(gp.GRB.Callback.MIP_OBJBND))
                    value.update(incumbent=incumbent if abs(incumbent)<1e90 else None,
                                 BestBd=bound if abs(bound)<1e90 else None,
                                 node_count=float(m.cbGet(gp.GRB.Callback.MIP_NODCNT)))
                    if value['incumbent'] is not None and value['BestBd'] is not None and abs(incumbent)>1e-12:
                        value['gap']=abs(incumbent-bound)/abs(incumbent)
                atomic(live_path,value)
            last[0]=0
            model.optimize(callback); spent += model.Runtime
            try: bound=float(model.ObjBound)
            except (gp.GurobiError,AttributeError): bound=None
            try: gap=float(model.MIPGap) if model.SolCount and model.IsMIP else None
            except (gp.GurobiError,AttributeError): gap=None
            row=dict(group=group,component=name,status=model.Status,runtime=model.Runtime,
                     objective=model.ObjVal if model.SolCount else None,bound=bound,
                     gap=gap,Threads=int(model.Params.Threads),TimeLimit=model.Params.TimeLimit)
            rows.append(row); atomic(output/'A1_SOLVE_RESULT.json',dict(passes=rows,accepted=False,total_runtime=spent))
            if not model.SolCount or model.Status != gp.GRB.OPTIMAL: break
            point=np.asarray(model.getAttr('X'))
            physical,selected,values,snapshot=certify.certificate(model,units,data,controls,bindings,levels,point,model.MaxVio)
            physical['all_phase_grid']=grid_audit(coefficients,values,evaluate(levels[0][1],point))
            physical['PASS']=physical['PASS'] and physical['all_phase_grid']['PASS']
            atomic(output/'A1_PHYSICAL_AUDIT.json',physical)
            if not physical['PASS']: break
            model.addConstr(expression <= model.ObjVal+(P1_EPS if name=='rho' else COMPONENT_EPS),name='single_thread_A1_lock_'+name)
        accepted=len(rows)==4 and all(r['status']==gp.GRB.OPTIMAL for r in rows) and physical is not None and physical['PASS']
        atomic(output/'A1_SOLVE_RESULT.json',dict(accepted=bool(accepted),passes=rows,total_runtime=spent,Threads=1,total_TimeLimit=1800))
        if not accepted:
            model.dispose(); raise ValueError('A1_NOT_SCIENTIFICALLY_ACCEPTED')
        sites=sorted(bundle['capacities']); caps=np.array([bundle['capacities'][s] for s in sites]); known=np.zeros((96,12))
        for uid,option in selected.items():
            for site,a,b in option['segments']:
                for t in range(max(a,24),min(b,120)): known[t-24,sites.index(site)]+=data[1][uid].gpu
        pcc=np.array([[values[t][coefficients[t].control_names.index('aidc_load_kw['+s+']')] for s in sites] for t in range(96)])
        # Use the exact new C1 rows to invert total modeled IT/GPU occupancy.
        import pandas as pd
        c1=pd.read_csv(Path(bundle['current_day_folder'])/'C1_PLANNING_COEFFICIENTS.csv')
        slope=c1.pivot(index='slot',columns='aidc_id',values='slope')[sites].to_numpy()
        intercept=c1.pivot(index='slot',columns='aidc_id',values='intercept_kw')[sites].to_numpy()
        it=(pcc-intercept)/slope; total=(it-power['current_IT_idle_kW_per_installed_GPU']*caps)/power['current_IT_swing_kW_per_active_GPU']
        q=pcc*np.tan(np.arccos(.95))
        if np.any(total>caps+1e-5) or np.any(total<known-1e-5): raise ValueError('PLANNING_GPU_POWER_IDENTITY')
        np.savez_compressed(output/'PLANNING_PHYSICAL.npz',sites=np.array(sites),PCC_P_kw=pcc,PCC_Q_kvar=q,IT_kw=it,GPU=total,known_GPU=known)
        atomic(output/'A1_FREEZE.json',dict(PASS=True,accepted=True,selected_jobs=selected,physical=physical,passes=rows,
                                          arm='B1',day=bundle['day'],old_A1_freeze_reused=False,all_MESS_PQ_zero=True))
        model.dispose()
        return dict(PASS=True,folder=str(output),physical=physical,passes=rows)
