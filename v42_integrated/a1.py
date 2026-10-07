"""Regenerate complete A1 from source jobs, frozen Runtime/CC4 and PR132 grid."""
import os
from pathlib import Path
from .governance import ROOT, OUT, write, sha, NORMALAMPS

LOCAL = ROOT.parent/'INTEGRATED_M1_LOCAL/A1_CANONICAL'
os.environ['V42_ROOT_OUTPUT'] = 'docs/v42_integrated_normalamps_zero_margin_m1/A1_BUILD'
os.environ['V42_ROOT_LOCAL'] = 'INTEGRATED_M1_LOCAL/A1_CANONICAL'

def run():
    import time, json
    import numpy as np
    import pandas as pd
    import gurobipy as gp
    from .contract import physical_authority, all_transformer_rows, evaluate, grid_audit
    from v42_root.data import prepare
    from v42_root.native import build
    from v42_root.common import Context
    from v42_root.certify import certificate
    from v42_two.contract import aidc_groups, passes, P1_EPS, COMPONENT_EPS
    from v42_bootstrap.grid import coefficients
    from v42_native.voltage import Stage, authority_sha
    import v42_boundary.model as boundary
    from .resources import snapshot
    LOCAL.mkdir(parents=True,exist_ok=True); (OUT/'A1_BUILD').mkdir(parents=True,exist_ok=True)
    marker=LOCAL/'A1_STARTED.json'
    if marker.exists(): raise ValueError('A1_NO_RETRY')
    write('A1_RESOURCE_RECEIPT.json',snapshot())
    marker.write_text(json.dumps(dict(source_model_regeneration=True,old_A1_solution_reused=False)),encoding='utf8')
    with physical_authority() as thermal:
        started=time.perf_counter(); print('A1_SOURCE_REGENERATION',flush=True)
        if (LOCAL/'DATA.pkl').exists():
            initial=json.loads((OUT/'A1_INITIAL_SOURCE_DATA_HASH_AUDIT.json').read_text(encoding='utf8'))
            assert sha(LOCAL/'DATA.pkl')==initial['source_data_cache_sha256'], 'ONLY_THIS_TASK_NEW_SOURCE_CACHE_ALLOWED'
        data=prepare(); bundle=data[0]
        from v42_a_stage_domain_v2.execution import require_action_authorized
        require_action_authorized(bundle,'A1')
        assert len(data[1])==1499 and bundle['day']=='2025-05-01'
        issue=pd.Timestamp(bundle['issue_time'])
        assert all(r['known_at_issue'] and pd.Timestamp(r['submit_time'])<=issue and pd.Timestamp(r['issue_time'])==issue for r in bundle['known_population'])
        assert bundle['RUNTIME_PROVIDER_READY'] is True
        from v42_capacity.common import resolve
        sources=[]
        def source_walk(obj):
            if isinstance(obj,dict):
                if 'path' in obj and 'sha256' in obj:
                    p=resolve(obj); sources.append(dict(path=str(p),sha256=sha(p)))
                for value in obj.values(): source_walk(value)
            elif isinstance(obj,list):
                for value in obj: source_walk(value)
        source_walk(bundle)
        from v42_boundary.common import OLD
        write('SOURCE_DATA_HASH_AUDIT.json',dict(PASS=True,bundle_sha256=sha(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),sources=sources,known_jobs=1499,future_actual_reads=0,source_available_before_issue=True,Runtime_refit=0,CC4_refit=0,source_data_cache_sha256=sha(LOCAL/'DATA.pkl')))
        original=boundary.add_grid
        boundary.add_grid=all_transformer_rows(original)
        try: m,units,legacy,controls,bindings=build(Context(),data,'F2-CRA')
        finally: boundary.add_grid=original
        m.update(); groups=passes(aidc_groups(legacy,units,data)); rows=[]; spent=0.; physical=None
        write('A1_MODEL_CENSUS.json',dict(rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,nnz=m.NumNZs,build_seconds=time.perf_counter()-started,voltage_band=[.95,1.05],margin_pu=0,NormalAmps_authority=NORMALAMPS,old_matrix_patch=False))
        # PR132 inherited A1 solver choice; M1's Method=2 policy is separate.
        m.Params.Threads=4; m.Params.MIPGap=.005; m.Params.Seed=20260929
        assert m.Params.Method==-1
        source_point=Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/V42_BOOTSTRAP_LOCAL/replay/FINAL_X.npy')
        if source_point.is_file():
            from .matrix import arrays,audit
            candidate=np.load(source_point);A,columns=arrays(m)
            proposal=dict(source_sha256=sha(source_point),candidate_only=True,old_A1_freeze_authority=False,variables_fixed=False,accepted=False)
            if len(candidate)==m.NumVars:
                row_audit=audit(A,columns,candidate,integral=True)
                proposal['new_full_matrix_audit']=row_audit
                if row_audit['PASS']:
                    check,_,candidate_controls,_=certificate(m,units,data,controls,bindings,legacy,candidate,row_audit['max_constraint_violation'])
                    _,candidate_coeff=coefficients(bundle)
                    check['all_phase_grid']=grid_audit(candidate_coeff,candidate_controls,evaluate(legacy[0][1],candidate))
                    proposal['new_physical_audit']=check
                    if check['PASS'] and check['all_phase_grid']['PASS']:
                        m.setAttr('Start',m.getVars(),candidate.tolist());proposal['accepted']=True
            else:proposal['reason']='COLUMN_COUNT_MISMATCH'
            write('A1_VALIDATED_CANDIDATE_START.json',proposal)
            del candidate,A,columns
        m.Params.OutputFlag=1; m.Params.LogToConsole=0; m.Params.LogFile=str(OUT/'A1_SOLVE.log')
        last=[-60.]
        def progress(model,where):
            if where==gp.GRB.Callback.POLLING: return
            t=float(model.cbGet(gp.GRB.Callback.RUNTIME))
            if t-last[0]>=30:
                last[0]=t
                state=dict(component=groups[len(rows)][1],runtime=t,completed_passes=len(rows))
                if where==gp.GRB.Callback.MIP:
                    state.update(nodes=float(model.cbGet(gp.GRB.Callback.MIP_NODCNT)))
                write('A1_LIVE.json',state); print('A1_PROGRESS',state,flush=True)
        print('A1_MODEL_READY',m.NumConstrs,m.NumVars,m.NumNZs,flush=True)
        solver_error=None
        for group,name,expr in groups:
            if spent>=3600: break
            m.setObjective(expr); m.Params.TimeLimit=3600-spent
            try:m.optimize(progress)
            except gp.GurobiError as error:
                solver_error=dict(error_code=error.errno,error_message=str(error),scientific_UB=None,scientific_LB=None,certificate_valid=False)
                write('A1_NATIVE_ERROR.json',solver_error)
                break
            spent+=m.Runtime
            rows.append(dict(group=group,component=name,status=m.Status,objective=m.ObjVal if m.SolCount else None,bound=m.ObjBound,runtime=m.Runtime,gap=m.MIPGap if m.SolCount else None))
            write('A1_SOLVE_RESULT.json',dict(passes=rows,total_runtime=spent,accepted=False))
            if not m.SolCount: break
            point=np.array(m.getAttr('X'))
            physical,selected,values,snap=certificate(m,units,data,controls,bindings,legacy,point,m.MaxVio)
            _,coeff=coefficients(bundle); grid=grid_audit(coeff,values,evaluate(legacy[0][1],point))
            physical['all_phase_grid']=grid; physical['PASS']=physical['PASS'] and grid['PASS']
            write('A1_PHYSICAL_AUDIT.json',physical)
            if not physical['PASS'] or m.Status!=gp.GRB.OPTIMAL: break
            m.addConstr(expr<=m.ObjVal+(P1_EPS if name=='rho' else COMPONENT_EPS),name='integrated_A1_lock_'+name)
        complete=len(rows)==len(groups) and all(r['status']==gp.GRB.OPTIMAL for r in rows) and physical is not None and physical['PASS']
        result=dict(accepted=bool(complete),passes=rows,total_runtime=spent,solver_error=solver_error,old_A1_freeze_reused=False,source_regenerated=True,final_scientific_groups=[g[0] for g in groups],scientific_objectives_exclude_reserve_and_CC4=True)
        write('A1_SOLVE_RESULT.json',result)
        if complete:
            anchor=dict(control_names=list(coeff[0].control_names),controls=values,voltage_authority_sha256=authority_sha(Stage.A1),transformer_current_authority_sha256=NORMALAMPS,source_stage='A1',fixed_AIDC_control_columns=[i for i,n in enumerate(coeff[0].control_names) if n.startswith('aidc_load_kw')])
            write('INTEGRATED_A1_FREEZE.json',dict(PASS=True,accepted=True,physical=physical,anchor=anchor,selected_jobs=selected,source_data_sha256=sha(LOCAL/'DATA.pkl'),objective=rows[0]['objective'],freeze_before_M1=True,result=result))
            np.savez_compressed(LOCAL/'A1_FINAL_POINT.npz',values=point,names=np.array(m.getAttr('VarName')))
        else:
            write('A1_ROOT_CAUSE.json',dict(status='NATIVE_SOLVER_ERROR' if solver_error else 'INFEASIBLE' if m.Status==gp.GRB.INFEASIBLE else 'A1_NOT_ACCEPTED',terminal_status=m.Status,solver_error=solver_error,passes=rows,physical=physical,constraint_relaxation=False,M1_run=False,log_sha256=sha(OUT/'A1_SOLVE.log')))
            write('INTEGRATED_A1_FREEZE.json',dict(PASS=False,accepted=False,status='NOT_FROZEN',reason='A1_GATE_FAILED',result=result))
        m.dispose(); print('A1_FINISHED',complete,rows,flush=True)
        return complete

if __name__=='__main__':
    run()
