"""Real native one-slot integration, explicitly not a 96-slot scientific gate."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np

from v42_b3_joint.contracts import digest
from v42_voltage_control import integration, authority


def test_two_real_time_namespaces_compile_same_initial_controls_and_keep_separate_queues(tmp_path):
    from v42_regcontrol import authority as original
    from v42_voltage_control.capcontrol import candidate_contract
    from v42_may_campaign_native90.preflight import native_zero
    connection=tmp_path/'connections.json';connection.write_text('{}')
    engine,_,_=original.compile_verified()
    try:
        cap=candidate_contract(engine,'A1')
    finally:
        engine.Basic.ClearAll()
    identity=dict(schema=integration.SCHEMA,case='A1',time_mode='TIME',capcontrol=cap,
                  svr=None,connection_manifest=integration.record(connection))
    scenario=dict(identity,scenario_SHA=digest(identity))
    sources=authority.source_files(); source=digest(sources)
    audits=[]
    with native_zero() as denied:
        for namespace in ('DAYAHEAD','ACTUAL'):
            audit=integration.PhysicalScenario(scenario,tmp_path/namespace,source_SHA=source,
                                               arm='B2',day='2025-05-01',namespace=namespace)
            engine,_,initial=original.compile_verified()
            trajectory=SimpleNamespace(day='2025-05-01',case='B2',namespace=namespace,
                pcc_p_kw=np.zeros((96,12)),pcc_q_kvar=np.zeros((96,12)),
                mess_p_kw=np.zeros((96,4)),mess_q_kvar=np.zeros((96,4)),
                mess_locations_96x4=tuple(tuple('STA01' for _ in range(4)) for _ in range(96)))
            frame=dict(day=trajectory.day,arm=trajectory.case,trajectory=trajectory,slot=0)
            with authority.physical_permit('B2','2025-05-01',source,scenario,namespace=namespace,development=True):
                audit.install_actual(engine,frame,original)
                engine.Solution.SolveSnap()
                audit.settle_actual(engine,frame,original)
                assert audit.rows[0]['time_control']['end_seconds']==900
                assert audit.rows[0]['time_control']['physical_solve_count']==len(audit.events)
                assert audit.rows[0]['settled_original_controls']['all_seven_RegControls_enabled']
                assert audit.rows[0]['physical']['all_original_and_added_axes_checked']
                assert len(audit.rows[0]['physical']['nodes'])==386
                assert not audit.rows[0]['capcontrol']['minimum_hold_violations']
                assert initial==audit.source_initial_controls
                assert audit.controllerinitialstate['other_namespace_states_read']==0
            audits.append(audit)
        assert not denied
    try:
        assert audits[0].sessions.keys()!=audits[1].sessions.keys()
        assert audits[0].initial_controls==audits[1].initial_controls
        assert audits[0].source_initial_controls==audits[1].source_initial_controls
        assert audits[0].sessions[next(iter(audits[0].sessions))]['clock'] is not audits[1].sessions[next(iter(audits[1].sessions))]['clock']
    finally:
        for audit in audits:
            for session in audit.sessions.values(): session['engine'].Basic.ClearAll()


def test_real_series_svr_declared_terminal_proxy_preserves_original_current_authority(tmp_path):
    from v42_regcontrol import authority as original
    from v42_voltage_control.siting import original_inventory,development_contract
    from v42_may_campaign_native90.preflight import native_zero
    from dataclasses import asdict
    connection=tmp_path/'connections.json';connection.write_text('{}')
    engine,_,_=original.compile_verified()
    try:
        source=original.source()
        old_branches,_=source['oriented_branches'](engine)
        inventory=original_inventory(engine,source_receipts=[integration.record(original.__file__)])
        svr=development_contract(inventory,('STA08',))
        identity=dict(schema=integration.SCHEMA,case='B',time_mode='TIME',capcontrol=None,
                      svr=svr,connection_manifest=integration.record(connection))
        scenario=dict(identity,scenario_SHA=digest(identity));source_SHA=digest(authority.source_files())
        audit=integration.PhysicalScenario(scenario,tmp_path/'physical',source_SHA=source_SHA,
                                           arm='B2',day='2025-05-01')
        tr=SimpleNamespace(day='2025-05-01',case='B2',namespace='ACTUAL',
            pcc_p_kw=np.zeros((96,12)),pcc_q_kvar=np.zeros((96,12)),
            mess_p_kw=np.zeros((96,4)),mess_q_kvar=np.zeros((96,4)),
            mess_locations_96x4=np.full((96,4),'STA01'))
        frame=dict(day=tr.day,arm=tr.case,trajectory=tr,slot=0)
        with native_zero() as denied,authority.physical_permit('B2',tr.day,source_SHA,scenario,development=True):
            audit.install_actual(engine,frame,original)
            engine.Solution.SolveSnap();audit.settle_actual(engine,frame,original)
            for branch in old_branches:
                if branch.branch_id=='transformer.mess_sta08_tx':
                    before=asdict(branch)
                    measured=audit.measure_original_branch(engine,branch,source['branch_measurement'])
                    legacy=audit.measure_original_branch(engine,branch,source['legacy_branch_measurement'])
                    assert len(measured)==len(legacy)==3 and all(np.isfinite(v) for v in measured+legacy)
                    assert measured[0]==legacy[0] and measured[2]==legacy[2]
                    engine.Transformers.Name(branch.branch_id.split('.',1)[1]);engine.Transformers.Wdg(1)
                    nominal=engine.Transformers.kVA()/(np.sqrt(3.0)*engine.Transformers.kV())
                    assert legacy[1]==legacy[0]/nominal
                    assert asdict(branch)==before
                    proxy=audit.topology_measurement_proxies[-1]
                    assert proxy['original_parent_bus']=='67'
                    assert proxy['measured_parent_bus']=='svr_sta08_regulated'
                    assert proxy['original_parent_terminal_1based']==1
            assert len(audit.topology_measurement_proxies)==6
            row=audit.rows[0]
            assert len(row['physical']['nodes'])==389
            assert row['svr']['hardware_PASS'] and row['svr']['added_nodes_voltage_PASS']
            assert not denied
    finally:
        engine.Basic.ClearAll()


def test_cold_original_thermal_authority_is_precompiled_before_scenario_hooks(tmp_path):
    from v42_regcontrol import authority as original
    from v42_thermal.authority import current_authority
    from v42_may_campaign_native90.preflight import native_zero
    connection=tmp_path/'connections.json';connection.write_text('{}')
    identity=dict(schema=integration.SCHEMA,case='REFa',time_mode='TIME',capcontrol=None,svr=None,
                  connection_manifest=integration.record(connection))
    scenario=dict(identity,scenario_SHA=digest(identity));source=digest(authority.source_files())
    current_authority.cache_clear()
    with native_zero() as denied,authority.physical_permit('B0','2025-05-01',source,scenario,development=True):
        with integration.scenario_scope(scenario,tmp_path/'scope',source_SHA=source,arm='B0',day='2025-05-01') as audit:
            assert audit.thermal_authority_prewarm['cache_was_cold']
            assert audit.thermal_authority_prewarm['completed_before_source_hooks']
            assert audit.thermal_authority_prewarm['original_Planning_Actual_authority_equal']
            engine,_,inventory=original.compile_verified()
            try:
                assert inventory['RegControl_count']==7 and inventory['CapControl_count']==0
                assert inventory['control_mode']==0 and not audit.sessions
            finally:
                engine.Basic.ClearAll()
        assert not denied
