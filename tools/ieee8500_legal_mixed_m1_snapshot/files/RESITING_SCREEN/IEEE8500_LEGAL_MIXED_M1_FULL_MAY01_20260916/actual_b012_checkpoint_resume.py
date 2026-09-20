"""Resume the frozen Actual algorithm after an accepted slot checkpoint."""
import ast,hashlib,json,time,traceback
from pathlib import Path
import actual_b012_resume as runtime
a=runtime.a

def main():
    a.verify()
    prior=a.read(a.H/'TRIAL_ERROR_HANDLING_FREEZE.json')
    assert a.sha(runtime.__file__)==prior['adapter']['sha256']
    authority=a.read(a.BASE/'ACTUAL_CHECKPOINT_RESUME_AUTHORITY.json')
    assert authority['status']=='FROZEN_BEFORE_RESUME'
    for row in [authority['checkpoint'],authority['events'],authority['previous_status'],*authority['completed']]:
        assert a.sha(row['path'])==row['sha256'],row['path']
    cp=a.read(authority['checkpoint']['path']);events=a.read(authority['events']['path'])
    n=cp['slots'];q=a.np.asarray(cp['Q'],dtype=float)
    assert q.shape==(n,6) and len(events)==n and [e['slot'] for e in events]==list(range(n))
    assert cp['rule_sha']==a.sha(a.H/'RULE_FREEZE.json')
    assert a.np.array_equal(q,a.np.asarray([e['Q_accepted'] for e in events]))
    resume_dir=a.H/Path(authority['checkpoint']['path']).parent.name
    a.Electrical=runtime.TrialElectrical
    ns=a.kernel();ns['independent_audit']=a.binding.independent_audit
    def restore_prefix(folder,data):
        engine=a.Electrical(resume_dir/'prefix_replay',data);rows=[]
        try:
            for t in range(n):
                row=engine.apply(t,q[t]);assert row['converged'] and row['controls_settled']
                if events[t]['status']!='ROBUST_Q_ONLY_UNRESOLVED':assert ns['feasible'](row)
                rows.append(row)
        finally:engine.close()
        a.save(resume_dir/'PREFIX_REPLAY_VERIFIED.json',dict(status='PASS',slots=n,
            original_checkpoint=authority['checkpoint'],original_events=authority['events'],
            voltage_sha256=[hashlib.sha256(r['v'].tobytes()).hexdigest() for r in rows],
            taps=[r['taps'] for r in rows],original_Q_unchanged=True))
        return rows
    source=a.source.read_text(encoding='utf-8')
    node=next(x for x in ast.parse(source).body if isinstance(x,ast.FunctionDef) and x.name=='run_policy')
    original=ast.get_source_segment(source,node)
    bound=original.replace('2025-05-21','2025-05-01').replace("W/'IEEE8500_numerical_preflight_20260911/AXES.json'","BASE/'AXES.json'")
    changes={
        "q=data['Q_EXEC'].copy();state(":"q=data['Q_EXEC'].copy();q[:RESUME_SLOTS]=RESUME_Q;state(",
        "baseline=continuous(folder/'ETA95_ACTUAL',data,q);bs=outputs(folder/'ETA95_ACTUAL',baseline,data,axes)":"baseline=restore_prefix(folder,data);bs=read(folder/'ETA95_ACTUAL/AC_SUMMARY.json')",
        "accepted=[];events=[];trials=[];engine_count=0;solve_count=0":"accepted=list(baseline);events=list(RESUME_EVENTS);trials=[];engine_count=0;solve_count=0",
        "for t in range(96):":"for t in range(RESUME_SLOTS,96):",
        "dict(trials=trials,clean_engines=engine_count,physical_solves=solve_count,prefix_verified=True,no_future_actual_applied=True)":"dict(trials=trials,clean_engines=engine_count,physical_solves=solve_count,prefix_verified=True,no_future_actual_applied=True,trial_scope='resumed slots only',restored_slots=RESUME_SLOTS,resume_authority=RESUME_AUTHORITY)"}
    for old,new in changes.items():
        assert bound.count(old)==1,old
        bound=bound.replace(old,new)
    freeze=resume_dir/'RESUME_RUNTIME_FREEZE.json'
    a.save(freeze,dict(status='FROZEN_BEFORE_RESUME',adapter=a.rec(Path(__file__)),
        original_run_policy=a.rec(a.source),authority=a.rec(a.BASE/'ACTUAL_CHECKPOINT_RESUME_AUTHORITY.json'),
        bound_source=bound,original_QSAFE_search_unchanged=True,per_slot_trial_cap_unchanged=True,
        completed_slot_search_skipped=True,independent_96_slot_final_replay_unchanged=True))
    scope=dict(a.__dict__,RESUME_SLOTS=n,RESUME_Q=q,RESUME_EVENTS=events,
               RESUME_AUTHORITY=authority,restore_prefix=restore_prefix)
    exec(compile(bound,str(__file__)+'::resumed_run_policy','exec'),scope)
    a.bootstrap.protect()
    import gurobipy as gp
    gp.Model.optimize=lambda *x,**k:(_ for _ in ()).throw(RuntimeError('DA_OPTIMIZATION_FORBIDDEN_IN_ACTUAL'))
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    da=MessElectricalAuthority.from_repository();da.validate()
    a.state(status='RUNNING',stage='ACTUAL_CHECKPOINT_PREFIX_REPLAY',policy='B2',restored_slots=n)
    scope['run_policy']('B2',ns,da)
    a.verify();assert a.sha(__file__)==a.read(freeze)['adapter']['sha256']
    final_events=a.read(a.H/'B2/Q_CONTROL_EVENTS.json');assert final_events[:n]==events
    for row in authority['completed']:assert a.sha(row['path'])==row['sha256']
    results={p:a.read(a.H/p/'COMPLETE.json') for p in ('B0','B1','B2')}
    a.save(a.H/'CAMPAIGN_COMPLETE.json',dict(status='COMPLETE',policies=results,
        all_AC_feasible=all(r['AC_feasible'] for r in results.values()),completed_unix=time.time(),
        checkpoint_resume=a.rec(freeze)))
    a.state(status='COMPLETE',stage='ACTUAL_CAMPAIGN_FINISHED')

if __name__=='__main__':
    try:main()
    except BaseException as e:
        a.save(a.H/'TECHNICAL_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()))
        a.state(status='FAILED',stage='ACTUAL_CHECKPOINT_RESUME_FAILED',error=repr(e));raise
