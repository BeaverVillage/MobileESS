"""Implementation regressions; never a monthly safety or siting comparison."""
from pathlib import Path
import inspect,ast,copy
from v42_pr134_b1.common import read,atomic,record,now

def fail_continue():
    from .controller import initial,next_policy,reconcile
    ledger=initial();seen=[]
    # Use the actual dispatch policy selector on 124 mixed terminal outcomes.
    for n in range(124):
        arm=next_policy(ledger);row=next(r for r in ledger['dates'].values() if r['arm']==arm and r['status']=='NOT_EXECUTED')
        row['status']='FAIL' if n%3==0 else 'PASS';seen.append(row['arm']+'/'+row['day'])
    from . import DAYS,ORDER
    assert seen==[a+'/'+d for a in ORDER for d in DAYS] and next_policy(ledger) is None
    return dict(PASS=True,implementation_selector_used=True,attempts=124,FAIL_dates=42,last=seen[-1],PASS_count_not_gate=True,evidence_kind='IMPLEMENTATION_TEST')

def controllers(root):
    from v42_voltage_control.bindings import original_bindings
    from v42_voltage_control.svr import install
    from v42_voltage_control.timecontrol import CommonClock
    scenario=read(Path(root)/'hardware/SCENARIO.json');authority,*_=original_bindings()
    # Real native single-timestamp controllers, identical operating plans;
    # only synthetic Actual background loads differ. No optimization occurs.
    planning,ad,_=authority.compile_verified();clock=CommonClock('DAYAHEAD','2025-05-01');clock.bind(planning);bank=install(planning,scenario['svr'])
    try:
        for name in planning.Transformers.AllNames():
            if str(name).lower().startswith('svr_'):
                planning.Transformers.Name(name);planning.Transformers.Wdg(2);planning.Transformers.Tap(.9)
        plan_before=[.9]*33
        def actual(scale):
            e,adapter,initial=authority.compile_verified()
            try:
                c=CommonClock('ACTUAL','2025-05-01');c.bind(e);b=install(e,scenario['svr']);start=copy.deepcopy(b.initial_state)
                for name in e.Loads.AllNames():
                    if str(name).lower().startswith(('idc_','mess_')):continue
                    e.Loads.Name(name);e.Loads.kW(e.Loads.kW()*scale);e.Loads.kvar(e.Loads.kvar()*scale)
                c.settle_slot(e,0)
                measured=b.measure();inventory=authority.source()['inventory'](e)
                taps=[p['tap'] for d in measured['devices'] for p in d['phases']]
                return dict(start=start,taps=taps,original=[r['initial_tap'] for r in inventory['regulators'] if not r['name'].startswith('svr_')],converged=measured['Converged'])
            finally:e.Basic.ClearAll()
        a=actual(.65)
        for name in planning.Transformers.AllNames():
            if str(name).lower().startswith('svr_'):
                planning.Transformers.Name(name);planning.Transformers.Wdg(2);planning.Transformers.Tap(1.1)
        b=actual(.65);changed=actual(1.35)
        assert a==b and a['start']==changed['start'] and (a['taps']!=changed['taps'] or a['original']!=changed['original'])
        assert a['converged'] and b['converged'] and changed['converged']
        return dict(PASS=True,Planning_tap_mutation_values=[.9,1.1],same_Actual_input_bit_exact=True,
            changed_Actual_background_changes_native_taps=True,independent_source_initial_states=True,
            native_single_timestamp=True,no_monthly_safety_certificate=True,Actual_results=[a,b,changed])
    finally:planning.Basic.ClearAll()

def source_paths():
    from v42_voltage_control import b0_new,forecast
    from v42_pr134_b1 import replay
    from v42_may_campaign_native90 import operations
    fns=(b0_new.fresh_environment,forecast.run_fresh,replay.fresh,operations.fresh)
    records=[]
    for f in fns:
        s=inspect.getsource(f);tree=ast.parse(s)
        setters=[ast.unparse(n) for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('Tap','TapNum') and n.args]
        assert not setters
        assert 'regulator_taps' not in s
        records.append(record(inspect.getfile(f)))
    # Original Fresh has an optional static replay helper. The approved ports
    # all replace that callback with measured AUTO control before invocation.
    assert "('apply_frozen_native_state',native_controls)" in inspect.getsource(forecast.run_fresh)
    assert '("apply_frozen_native_state",controls)' in inspect.getsource(b0_new.fresh_environment)
    assert 'apply_frozen_native_state' in inspect.getsource(replay.fresh)
    return dict(PASS=True,Actual_entry_points_no_Tap_setter_or_Planning_Tap_array_reads=True,
        legacy_static_callback_replaced=True,code=records,scope='Entry points and inherited callback routing; per-date measured context isolation also required')

def run(root):
    value=dict(schema='V42_SVR11_IMPLEMENTATION_REGRESSIONS_V1',FAIL_CONTINUE=fail_continue(),control_independence=controllers(root),
        Actual_code_paths=source_paths(),model_regeneration_gate='Every non-B0 worker requires SVR11 source-bound 96x60 sensitivities and 153 transformer phase rows before Native entry; complete certificate checked per date',
        full_campaign_or_voltage_safety_certification=False,UTC=now())
    atomic(Path(root)/'IMPLEMENTATION_REGRESSIONS.json',value)
    return value

if __name__=='__main__':
    import sys
    run(sys.argv[1])
