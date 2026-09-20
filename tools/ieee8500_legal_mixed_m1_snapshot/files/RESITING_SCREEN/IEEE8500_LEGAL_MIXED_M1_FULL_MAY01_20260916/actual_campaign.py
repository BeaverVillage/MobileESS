"""Frozen production Actual adapter; no DA optimization or infrastructure tuning."""
import os, sys, json, time, hashlib, traceback
from pathlib import Path
sys.dont_write_bytecode = True
BASE = Path(__file__).absolute().parent
assert str(BASE).isascii()
import bootstrap
source_adapter = BASE.parent.parent/'independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913/validate_actual.py'
adapter = source_adapter.read_text(encoding='utf-8').split('\ndef selected():', 1)[0]
exec(compile(adapter, str(source_adapter)+'::legal_mixed_M1', 'exec'), globals())
POLICIES = ('B0','B1','B2') if '--b012' in sys.argv else ('B0','B1','B2','B3')
H = BASE/('Actual_B012' if '--b012' in sys.argv else 'Actual')
import actual_binding as binding
binding.install_actual()

def selected():
    zero = [dict(mess_id=m, slot=t, service_id=s, p_kw=0., q_kvar=0.,
                 departure_slot=None, origin_service_id=None, destination_service_id=None,
                 route_link_ids=[], connection_ready_slot=None, mode='CONNECTED',
                 battery_energy_kwh=760., soc_fraction=760./1200.)
            for m,s in binding.fb.INITIAL.items() for t in range(96)]
    choices = {'B0':(read(BASE/'REFERENCE_JOBS.json'),zero),
            'B1':(read(BASE/'B1/FINAL_JOBS.json'),zero),
            'B2':(read(BASE/'REFERENCE_JOBS.json'),read(BASE/'B2/FINAL_AUTHORITY.json')['trajectory_slots'])}
    if 'B3' in POLICIES:
        b3 = read(BASE/'B3/FINAL_AUTHORITY.json')
        choices['B3'] = (b3['jobs'],b3['trajectory_slots'])
    return choices

def verify():
    for r in read(H/'RULE_FREEZE.json')['source_files']:
        assert sha(r['path']) == r['sha256'], r['path']

def main():
    assert read(BASE/'ACTUAL_AUTHORIZATION.json')['authorized']
    if 'B3' in POLICIES:
        result = read(BASE/'FULL_RESULT.json')
        assert result['physical_PASS'] and result['transport_authority_preserved']
        gate_files = [BASE/'FULL_RESULT.json', BASE/'B3/FINAL_AUTHORITY.json']
    else:
        assert read(BASE/'ACTUAL_B012_PRIORITY_AUTHORIZATION.json')['authorized']
        from audit_inputs import main as audit_inputs
        audit_inputs()
        pairs={'B0':('B0_REPLAY/AC_VALIDATION.json','B0/Fresh/AC_VALIDATION.json'),
               'B1':('B1/final_exact/AC_VALIDATION.json','B1/Fresh/AC_VALIDATION.json'),
               'B2':('B2/physical_closure/accepted_clean_exact/AC_VALIDATION.json','B2/Fresh/AC_VALIDATION.json')}
        gate_files=[BASE/'INPUT_AUTHORITY_AUDIT.json',BASE/'ACTUAL_B012_PRIORITY_AUTHORIZATION.json']
        result={}
        for policy,paths in pairs.items():
            reports=[read(BASE/n) for n in paths]
            assert all(r['status']=='PASS' for r in reports)
            result[policy]={'DA':reports[0]['metrics'],'Fresh':reports[1]['metrics']}
            gate_files += [BASE/n for n in paths]
    # Ordering and the 0.90 target are reported, never prerequisites for Actual.
    H.mkdir(exist_ok=True)
    files = [Path(__file__), source_adapter, source, *gate_files]
    files += [BASE/n for n in ['actual_binding.py','actual_power_binding.py','availability_gating.py',
        'fleet_binding.py','CODE_DIFF.json','headroom_authority.py','HEADROOM_AUTHORITY.json',
        'AIDC_2X_AUTHORITY.json','FLEET_AUTHORITY.json','LAYOUT.json','PCC_OVERLAY.dss',
        'PCC_OVERLAY_INVENTORY.json','electrical_engine.py','AXES.json','SCREENING_RULE.json',
        'D1_AEMO_VIC1_FORECAST.json','REFERENCE_JOBS.json','B1/FINAL_JOBS.json',
        'B1/FINAL_AUTHORITY.json','B2/FINAL_AUTHORITY.json']]
    files += [METHOD/n for n in ['METHOD_FREEZE.json','METHOD_CODE_BINDING.json','robust_search.py',
                               'frozen_code/qsafe.py','frozen_code/worker.py','BATTERY_EFFICIENCY_AUTHORITY.json']]
    files += [Path(r[k]) for r in read(BASE/'CODE_DIFF.json') for k in ('source','override')]
    files.append(binding.source)
    for sub in ['v41','v41r1','v40d_actual','v40g_segments','v39a','v33m']:
        files += list((ROOT/'dayahead'/sub).glob('*.py'))
    files += [ROOT/'dayahead/mess_physics.py', ROOT/'dayahead/v28r2/c1_affine.py']
    from dayahead.v41.data import SOURCE_REPO
    audit = Path(SOURCE_REPO)/'dayahead/artifacts/v40d_actual_realized_replay'
    files.append(audit/'V40D_FROZEN_JOB_OBSERVATIONS.parquet')
    for name in ['V40D_AEMO_COMPLETENESS.json','V40D_WEATHER_COMPLETENESS.json','V40D_TRAFFIC_COMPLETENESS.json']:
        p=audit/name; files.append(p); j=read(p)
        refs = [j['demand']['source'],j['pv']['source']] if 'AEMO' in name else [j['derived']] if 'WEATHER' in name else [j['link_order'],*j['geometry_sources'],next(x for x in j['days'] if x['day']==DAY)['source']]
        for r in refs:
            assert sha(r['path'])==r['sha256']; files.append(Path(r['path']))
    files += list((BASE.parent.parent/'IEEE8500_scalability_20260910/source').rglob('*.dss'))
    if not (H/'RULE_FREEZE.json').exists():
        save(H/'RULE_FREEZE.json',dict(status='FROZEN_BEFORE_ACTUAL',date=DAY,
            s_DC=1.,s_MESS=1.,policies=list(POLICIES),source_files=[rec(p) for p in sorted(set(files))],
            DA_Fresh=result,actual_method='Existing arrival-gated six-fleet robust QSAFE V2',
            no_new_DA_optimization=True,no_post_result_resiting=True))
        (H/'BATTERY_EFFICIENCY_AUTHORITY.json').write_bytes((METHOD/'BATTERY_EFFICIENCY_AUTHORITY.json').read_bytes())
    verify(); bootstrap.protect()
    ns=kernel(); ns['independent_audit']=binding.independent_audit
    import gurobipy as gp
    gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('DA_OPTIMIZATION_FORBIDDEN_IN_ACTUAL'))
    da=inputs(ns)
    for policy in POLICIES:
        if not (H/policy/'COMPLETE.json').exists():
            assert (H/policy/'INPUT_READY.json').exists()
            run_policy(policy,ns,da)
        verify()
    results={p:read(H/p/'COMPLETE.json') for p in POLICIES}
    save(H/'CAMPAIGN_COMPLETE.json',dict(status='COMPLETE',policies=results,
        all_AC_feasible=all(r['AC_feasible'] for r in results.values()),completed_unix=time.time()))
    state(status='COMPLETE',stage='ACTUAL_CAMPAIGN_FINISHED')

if __name__=='__main__':
    try: main()
    except BaseException as e:
        H.mkdir(exist_ok=True)
        save(H/'TECHNICAL_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()))
        raise
