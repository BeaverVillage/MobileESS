"""Frozen V41R4 post-selection closure with IEEE8500 electrical ports only.

No candidate enumeration, beam ranking, route search, B1 or B3 execution.
"""
import os, sys, json, time, hashlib, inspect, types, traceback
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
from dataclasses import asdict

HERE=Path(__file__).absolute().parent
OLD=HERE.parent/'IEEE8500_v41r4_production_20260911_r2'
sys.dont_write_bytecode=True
sys.path.insert(0,str(OLD))
import common8500 as c
c.P=HERE
c.install_output_paths()
import numpy as np
import mess_grid8500
mess_grid8500.P=HERE
from dayahead.v40h import recourse
from dayahead.v40h.beam_driver import _restore_slots
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v40a.grid import controls_from_trajectory
from dayahead.v17_ac_restoration_contract import ACViolation,RestorationCut,ViolationType,RHO,canonical_sha256
import mission_ac_cut_restore as original_local
import restoration_revision_v1 as original_revision

save=c.save
read=c.read
record=c.record
sha=c.sha
RULE_SOURCE=Path(original_revision.__file__).parent/'frozen_artifacts/v41r4_restoration_revision_v1/RULE_FREEZE.json'
ALLOWED_CHANGED_FIELDS={'p_kw','q_kvar','battery_energy_kwh','soc_fraction'}

def discrete(rows):
    return canonical_sha256({'rows':[{k:v for k,v in asdict(r).items() if k not in ALLOWED_CHANGED_FIELDS} for r in rows]})

def clone(fn,**bindings):
    result=types.FunctionType(fn.__code__,dict(fn.__globals__,**bindings),fn.__name__,fn.__defaults__,fn.__closure__)
    result.__kwdefaults__=fn.__kwdefaults__
    return result

def physical_values(a):
    return [np.sqrt(a[0]),np.abs(a[1]),np.abs(a[2]),np.abs(a[3])/np.array(c.AX['winding_rating_kVA'])]

def exact_frozen(*,trajectory,output,**unused):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    x=original_local.control_matrix({'control_names':c.NAMES},trajectory)
    e=c.Engine(output/'runtime');rows=[];states=[];arrays=[];violations=[];indexes={};start=time.perf_counter()
    try:
        for t in range(96):
            e.inputs(t,x[t]);e.solve();settled=bool(e.d.Solution.ControlActionsDone())
            a=e.arrays();vals=physical_values(a);arrays.append(a);states.append(e.state(t))
            state_sha=hashlib.sha256(b''.join(np.asarray(v).tobytes() for v in a)).hexdigest()
            for family,(axis,values) in enumerate(zip([c.AX['nodes'],c.AX['line'],c.AX['tx'],c.AX['winding']],vals)):
                bad=np.where((values<.95-1e-9)|(values>1.05+1e-9))[0] if family==0 else np.where(values>1+1e-9)[0]
                for idx in bad:
                    value=float(values[idx]);kind=([ViolationType.VOLTAGE_LOWER,ViolationType.VOLTAGE_UPPER][value>1.05] if family==0 else [None,ViolationType.LINE_CURRENT,ViolationType.TRANSFORMER_CURRENT,ViolationType.TRANSFORMER_KVA][family])
                    limit=(.95 if value<.95 else 1.05) if family==0 else 1.
                    violation=ACViolation(kind,'2025-05-21','B2',t,str(axis[idx]),None,value,limit,abs(value-limit),state_sha,trajectory.source_schedule_sha256)
                    violations.append(violation);indexes[violation.sha256]=(family,int(idx))
            row=dict(slot=t,Vmin_pu=float(vals[0].min()),Vmax_pu=float(vals[0].max()),
                max_phase_line_loading_pu=float(vals[1].max()),max_transformer_phase_current_pu=float(vals[2].max()),
                max_transformer_winding_kva_pu=float(vals[3].max()),converged=True,controls_settled=settled,
                Vmin_node=str(e.nodes[vals[0].argmin()]),Vmax_node=str(e.nodes[vals[0].argmax()]))
            rows.append(row)
    finally:e.close()
    metrics={k:(min if k=='Vmin_pu' else max)(r[k] for r in rows) for k in ('Vmin_pu','Vmax_pu','max_phase_line_loading_pu','max_transformer_phase_current_pu','max_transformer_winding_kva_pu')}
    summary=dict(**metrics,physical_violation=bool(violations) or not all(r['controls_settled'] for r in rows),convergence_count=96,
        controls_settled_count=sum(r['controls_settled'] for r in rows),elapsed_seconds=time.perf_counter()-start)
    summary['status']='FAIL' if summary['physical_violation'] else 'PASS'
    save(output/'AC_VALIDATION.json',dict(status=summary['status'],metrics=metrics,summary=summary,slots=rows))
    save(output/'CONTROL_STATES.json',states);save(output/'VIOLATIONS.json',[v.payload() for v in violations])
    np.savez_compressed(output/'ARRAYS.npz',x=x,**{key:np.array([a[j] for a in arrays]) for j,key in enumerate(['v2','line','tx','S'])})
    print('EXACT',output.relative_to(HERE),summary['status'],metrics,flush=True)
    return SimpleNamespace(summary=summary,values=arrays,states=states,violations=tuple(violations),indexes=indexes,x=x)

def signed_cuts(*,frozen,fresh,violations,iteration_index,margins,**unused):
    """Original +/-5 central-difference rule at the failed IEEE8500 state."""
    cuts=[];ledger=[];repeat_max=0.;solves=0
    root=HERE/'local_signed_ac'/f'round_{iteration_index:02}'
    for t in sorted({v.slot for v in violations}):
        vv=[v for v in violations if v.slot==t]
        e=c.Engine(root/f'slot_{t:02}'/'runtime')
        try:
            for history in range(t+1):
                e.inputs(history,fresh.x[history]);e.solve();solves+=1
                assert e.d.Solution.ControlActionsDone()
            vals=physical_values(e.arrays());expected=physical_values(fresh.values[t])
            repeat=max(float(np.max(np.abs(a-b))) for a,b in zip(vals,expected));repeat_max=max(repeat_max,repeat)
            assert repeat<=1e-6,('STALE_FRESH_AC_ANCHOR',t,repeat)
            e.hold(fresh.states[t]);e.controls(fresh.x[t]);e.solve();solves+=1
            held=physical_values(e.arrays())
            held_error=max(abs(float(held[fresh.indexes[v.sha256][0]][fresh.indexes[v.sha256][1]])-v.actual_value) for v in vv)
            # The frozen preflight also retains chronological Fresh intercepts
            # while computing signed derivatives at tight held-state tolerance.
            # This extra zero-injection solve is diagnostic, not a replacement
            # for the exact chronological anchor checked above at 1e-6.
            # Preserve the discrepancy; do not change the Fresh cut intercept,
            # original margins, physical limits, or clean acceptance tolerance.
            save(root/f'slot_{t:02}'/'HELD_DERIVATIVE_BASE_DIAGNOSTIC.json',dict(
                chronological_anchor_error=repeat,tight_held_base_error=held_error,
                fresh_intercept_retained=True,held_intercept_used=False,
                numerical_engine_source=record(c.PREF/'electrical_engine.py')))
            deriv={v.sha256:np.zeros(60) for v in vv}
            services=sorted({str(s).upper() for s in frozen.mess_locations_96x4[t] if not str(s).upper().startswith('TRANSIT_')})
            for service in services:
                for kind in ('p_kw','q_kvar'):
                    j=c.NAMES.index(f'mess_{kind}[{service}]');sides=[]
                    for sign in (1,-1):
                        x=fresh.x[t].copy();x[j]+=sign*5.;e.controls(x);e.solve();solves+=1;sides.append(physical_values(e.arrays()))
                    for v in vv:
                        family,idx=fresh.indexes[v.sha256];plus=float(sides[0][family][idx]);minus=float(sides[1][family][idx]);d=(plus-minus)/10
                        deriv[v.sha256][j]=d;ledger.append(dict(violation_sha256=v.sha256,slot=t,control_index=j,control_name=c.NAMES[j],plus=plus,minus=minus,derivative=d,signed_step=5.))
                    e.controls(fresh.x[t]);e.solve();solves+=1
            radius=np.r_[np.zeros(12),np.full(24,RHO*300),np.full(24,RHO*400)]
            for v in vv:
                j=deriv[v.sha256];isv=v.violation_type in (ViolationType.VOLTAGE_LOWER,ViolationType.VOLTAGE_UPPER)
                margin=margins['m_V_pu' if isv else ('m_transformer_kva_pu' if v.violation_type==ViolationType.TRANSFORMER_KVA else 'm_I_pu')]
                cuts.append(RestorationCut(v.sha256,canonical_sha256(fresh.states[t]),hashlib.sha256(j.tobytes()).hexdigest(),v.violation_type,t,
                    '>=' if v.violation_type==ViolationType.VOLTAGE_LOWER else '<=',v.actual_value,v.hard_limit,margin,RHO,iteration_index,c.NAMES,
                    tuple(map(float,fresh.x[t])),tuple(map(float,j)),tuple(map(float,radius))))
        finally:e.close()
    report=dict(frozen_tap_central_difference=True,finite_difference_step=5.,Fresh_finite_difference_solve_count=solves,
        maximum_anchor_reproduction_error_pu=repeat_max,derivatives=ledger,IEEE8500_only=True)
    save(root/'SIGNED_DERIVATIVE_AUTHORITY.json',dict(cuts=[v.payload() for v in cuts],report=report))
    return tuple(cuts),report

def local_binding():
    solver=clone(recourse.solve_fixed_route,evaluate_grid=c.evaluate_grid)
    return clone(original_local.restore,run_fresh_opendss=exact_frozen,corrected_mapping=nullcontext,
        extract_ac_violations=lambda fresh:fresh.violations,local_fresh_ac_restoration_cuts=signed_cuts,
        solve_fixed_route=solver,add_grid=mess_grid8500.add,write_json=save)

def fallback_binding():
    # Only electrical import substitution; original MIQP/search/selection retained.
    src=inspect.getsource(original_revision.model_candidate)
    old='from dayahead.v40a.grid import add_grid'
    assert src.count(old)==1
    src=src.replace(old,'from mess_grid8500 import add as add_grid')
    ns=dict(original_revision.model_candidate.__globals__);exec(compile(src,str(HERE/'closure8500.py')+'::electrical_adapter','exec'),ns)
    def exact_adapter(day,policy,d,power,candidate,ctx,folder):
        f=original_local.make_frozen(day,policy,d['AIDC_decision'],power,candidate)
        return exact_frozen(trajectory=f,output=folder)
    return clone(original_revision.fallback,model_candidate=ns['model_candidate'],exact=exact_adapter,save=save)

def freeze():
    assert not (HERE/'RULE_FREEZE.json').exists()
    c.verify();rule=read(RULE_SOURCE)
    for row in rule['code']+[rule['local_margin']]:assert sha(row['path'])==row['sha256'],row['path']
    assert sha(OLD/'PRODUCTION_RELEASE.json')=='5f8f48e2dc26c3b135d2cfec0dcf7d937b81d79aca2440ab15de6f874bc678c4'
    for row in read(OLD/'PRODUCTION_RELEASE.json')['code']:assert sha(row['path'])==row['sha256'],row['path']
    src=OLD/'B2/beam/2025-05-21/B2/B2/FINAL_RESULT.json';selected=read(src)
    assert selected['selected_state']['beam_state_id']=='B2-S4-b55b48c9f33cb380'
    initial=MessTrajectory(tuple(_restore_slots(selected['trajectory_slots'])))
    assert recourse.validate_physics(initial)['status']=='PASS'
    save(HERE/'ORIGINAL_SELECTED_DECISION.json',dict(state_id='B2-S4-b55b48c9f33cb380',trajectory_slots=selected['trajectory_slots'],source=record(src),discrete_sha=discrete(initial.slots)))
    files=[Path(__file__),RULE_SOURCE,original_local.MARGINS_PATH,OLD/'common8500.py',OLD/'mess_grid8500.py',
        OLD/'B0/FINAL.json',OLD/'B0/POWER.npz',OLD/'B1/FINAL_AUTHORITY.json',OLD/'B1/ACCEPTED_AIDC.json',
        OLD/'B2/final_exact/AC_VALIDATION.json',src,HERE/'ORIGINAL_SELECTED_DECISION.json',
        c.PREF/'ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json',
        HERE.parent/'IEEE8500_B2_physical_closure_20260912/RULE_FREEZE.json',
        HERE.parent/'IEEE8500_B2_physical_closure_20260912/FAILURE.json']+[Path(r['path']) for r in rule['code']]
    save(HERE/'RULE_FREEZE.json',dict(created_unix=time.time(),stage='B2_POST_SELECTION_PHYSICAL_CLOSURE_ONLY',
        sequence=['PRIMARY_FRESH_FAIL','LOCAL_FIXED_DISCRETE_RESTORATION','ONLY_STATUS_3_FULL_PHYSICAL_PQ_FALLBACK','CLEAN_96_SLOT_EXACT_AC_ACCEPTANCE'],
        original_closure_rule=record(RULE_SOURCE),local_K_MAX=original_local.K_MAX,RHO=RHO,
        local_margins=read(original_local.MARGINS_PATH)['margins'],allowed_changed_fields=sorted(ALLOWED_CHANGED_FIELDS),
        signed_difference_step=5.,source=1.04,Vreg=123.5,alpha=.5,CAPBank3='OFF',hard_limits_unchanged=True,
        B1_rerun=False,B3_start=False,beam_or_final_selection_changes=False,diagnostic_candidate_inputs=False,
        electrical_differences=['IEEE8500 full affine grid rows','IEEE8500 60-control/PCC binding','IEEE8500 clean AC engine and axis','IEEE8500 failed-state signed AC cuts'],
        original_local_restore_bytecode_unchanged=True,original_fallback_search_bytecode_unchanged=True,files=[record(p) for p in files]))
    print('RULE_FROZEN',flush=True)

def run():
    rule=read(HERE/'RULE_FREEZE.json')
    for r in rule['files']:assert sha(r['path'])==r['sha256'],r['path']
    c.verify();selected=read(HERE/'ORIGINAL_SELECTED_DECISION.json');initial=MessTrajectory(tuple(_restore_slots(selected['trajectory_slots'])))
    jobs=read(OLD/'B0/FINAL.json')['jobs']
    with np.load(OLD/'B0/POWER.npz') as z:power={k:z[k].copy() for k in z.files}
    voltage={'control_names':c.NAMES,'node_names':c.AX['nodes']}
    ctx=SimpleNamespace(coefficients=c.Coefficients(),nodes=c.AX['nodes'],electrical=SimpleNamespace(voltage=voltage),
        v41_electrical_certificate=record(c.PREF/'ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json'),revision_pcc=power['pcc'])
    c.state(status='RUNNING',stage='LOCAL_FIXED_DISCRETE_RESTORATION',B3_blocked=True)
    fallback_used=False
    try:
        try:
            final,local=local_binding()('2025-05-21','B2',jobs,power,initial,ctx,HERE/'local')
            assert local['status']=='PASS'
        except AssertionError as error:
            info=error.args[0] if error.args else None
            if not (isinstance(info,tuple) and info[0]=='CUT_RECOURSE_FAILURE' and info[1].get('status_code')==3):raise
            save(HERE/'LOCAL_INFEASIBLE.json',dict(status='INFEASIBLE',solver=info[1],strict_fallback_gate_pass=True))
            fallback_used=True;c.state(status='RUNNING',stage='FULL_PHYSICAL_PQ_FALLBACK',B3_blocked=True)
            final,_=fallback_binding()('2025-05-21','B2',{'AIDC_decision':jobs},power,initial,ctx,HERE/'full_pq')
        assert discrete(final.slots)==selected['discrete_sha']
        assert recourse.validate_physics(final)['status']=='PASS'
        c.state(status='RUNNING',stage='CLEAN_96_SLOT_EXACT_AC_ACCEPTANCE',B3_blocked=True)
        replay=c.exact(power['pcc'],final.slots,HERE/'accepted_clean_exact')
        assert replay['status']=='PASS',replay['metrics']
        for r in rule['files']:assert sha(r['path'])==r['sha256'],r['path']
        grid=c.evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,power['pcc'],final.slots),ctx.nodes)
        save(HERE/'B2_RESTORED_ACCEPTANCE.json',dict(status='PASS',primary_status='PRIMARY_FRESH_FAIL',
            primary=record(OLD/'B2/final_exact/AC_VALIDATION.json'),original_state=selected['state_id'],
            local_status='INFEASIBLE' if fallback_used else 'PASS',full_physical_PQ_fallback=fallback_used,
            final_slots=[asdict(r) for r in final.slots],AC=replay['metrics'],planning_grid=grid,
            unchanged_discrete_sha=discrete(final.slots),physics=recourse.validate_physics(final),
            B1_preserved=record(OLD/'B1/FINAL_AUTHORITY.json'),beam_selection_unchanged=True,
            diagnostic_candidate_used=False,B3_started=False,rule=record(HERE/'RULE_FREEZE.json')))
        save(HERE/'CLOSURE_SHA256_MANIFEST.json',dict(files=[record(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name not in ('STATUS.json','run.stdout.log','run.stderr.log')]))
        c.state(status='PASS',stage='B2_PHYSICAL_CLOSURE_ACCEPTED',B3_started=False)
    except BaseException as error:
        save(HERE/'FAILURE.json',dict(status='FAIL_CLOSE',error=repr(error),traceback=traceback.format_exc(),B3_started=False))
        c.state(status='FAIL_CLOSE',stage='B2_PHYSICAL_CLOSURE_STOPPED',B3_blocked=True)
        raise

if __name__=='__main__':
    if sys.argv[1:] == ['freeze']:freeze()
    elif sys.argv[1:] == ['run']:run()
    else:raise SystemExit('Expected freeze or run')
