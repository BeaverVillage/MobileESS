"""Small fixed-trajectory and original mapping contracts; Native calls = 0."""
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from v42_may_campaign import operations as op
from v42_may_campaign.common import atomic, read, record
from v42_pr134_b1 import replay
from v42_pr134_b1.common import CODE

sys.path.insert(0, str(CODE))
from dayahead.v28r2 import opendss_mapping as mapping
from dayahead.v28r2.trajectory import FrozenTrajectory


def test_original_context_file_paths_are_distinct_and_never_change_scientific_state(tmp_path):
    inventory = dict(RegControl_count=7, CapControl_count=0, initial_taps=[1.] * 7)
    paths, records, engines = [], [], []
    for day in ('2025-05-01', '2025-05-02', '2025-05-03'):
        data_path = [str(tmp_path)]
        def directory(value=None, data_path=data_path):
            if value is not None:
                data_path[0] = value
            return data_path[0]
        engine = SimpleNamespace(Basic=SimpleNamespace(DataPath=directory))
        engines.append(engine)
        output = tmp_path / day / 'FRESH'
        result = op.isolated_compile(lambda: (engine, {}, inventory), output, records)
        assert result[0] is engine and result[2] is inventory
        paths.append(Path(engine.Basic.DataPath()))
    assert len(set(paths)) == 3
    assert inventory == dict(RegControl_count=7, CapControl_count=0, initial_taps=[1.] * 7)
    assert all(row['scientific_control_settings_changed'] is False for row in records)


def test_engine_rejecting_private_directory_is_not_accepted(tmp_path):
    engine = SimpleNamespace(Basic=SimpleNamespace(DataPath=lambda *args: str(tmp_path / 'shared')))
    with pytest.raises(ValueError, match='DATA_PATH_ISOLATION'):
        op.isolated_compile(lambda: (engine, {}, {}), tmp_path / 'own', [])


def fixture_stage(tmp_path, arm):
    root = tmp_path / arm
    folder, result, source = root / 'input', root / 'output', root / 'stage'
    for path in (folder, result, source):
        path.mkdir(parents=True)
    request = dict(run_id='fresh-current-test', root=str(root), input_folder=str(folder),
                   output=str(result), day='2025-05-12', arm=arm)
    planning = dict(sites=np.asarray([f'AIDC{i:02d}' for i in range(1, 13)]),
                   PCC_P_kw=np.full((96, 12), 10.), PCC_Q_kvar=np.full((96, 12), 3.),
                   IT_kw=np.full((96, 12), 8.), GPU=np.full((96, 12), 5.))
    atomic(folder / 'NATIVE_INPUT.json', dict(day=request['day'], capacities={s: 100 for s in planning['sites']}))
    np.savez_compressed(source / 'PLANNING_PHYSICAL.npz', **planning)
    selected = {'job-1': dict(job_uid='job-1', site='AIDC01', start=24, end=28, segments=[['AIDC01', 24, 28]])}
    stage = dict(PASS=True, accepted=True, day=request['day'], arm=arm, UB=1., LB=.999,
                 certified_gap=.001, P2_calls=0)
    if arm == 'B1':
        receipts = {}
        for name in ('physical', 'acceptance', 'global_bound'):
            atomic(source / (name + '.json'), dict(PASS=True))
            receipts[name] = record(source / (name + '.json'))
        accepted = dict(stage, A1_P1_ONLY_ACCEPTED=True, A1_ACCEPTED=False, MESS_optimization_calls=0,
                        all_MESS_PQ_zero=True, selected_jobs=selected, **receipts)
        atomic(source / 'B1_P1_FREEZE.json', accepted)
        stage.update(freeze=record(source / 'B1_P1_FREEZE.json'), planning=record(source / 'PLANNING_PHYSICAL.npz'))
    else:
        atomic(folder / 'B2_FIXED_AIDC.json', dict(identity=dict(PASS=True, day=request['day'], arm=arm,
            AIDC_optimization_calls=0, B0_B1_schedule_result_reads=0), selected_jobs=selected,
            physical=record(source / 'PLANNING_PHYSICAL.npz')))
        p, q = np.zeros((96, 4)), np.zeros((96, 4))
        p[0] = [12, -8, 0, 0]; q[0] = [4, -2, 0, 0]
        locations = [['STA01', 'STA12', 'TRANSIT_STA08_STA06', 'STA06']] * 96
        plan = dict(P_kw=p.tolist(), Q_kvar=q.tolist(), locations=locations,
                    SOC_kwh=np.full((97, 4), 100.).tolist(), unit_ids=[f'MESS{i:02d}' for i in range(1, 5)],
                    routes=[], day=request['day'], arm=arm, case_sha='a' * 64)
        atomic(source / 'OPTIMIZED_MESS_PLAN.json', plan)
        certificates = {}
        for name in ('strict_UB', 'exact_LB'):
            atomic(source / (name + '.json'), dict(PASS=True))
            certificates[name] = record(source / (name + '.json'))
        stage.update(planning=planning, mess=plan, mess_plan=record(source / 'OPTIMIZED_MESS_PLAN.json'),
                     certificate=certificates, case_sha='a' * 64, AIDC_optimization_calls=0)
    return request, stage


@pytest.mark.parametrize('arm', ['B1', 'B2'])
def test_original_freeze_and_fixed_actual_preserve_every_power_command(tmp_path, monkeypatch, arm):
    request, stage = fixture_stage(tmp_path, arm)
    source = Path(request['output']) / 'OPERATIONS/SOURCE'
    planning = source.parent / 'PLANNING'; actual = source.parent / 'ACTUAL'
    for path in (source, planning, actual):
        path.mkdir(parents=True)
    from v42_may_campaign import execution
    from v42_regcontrol import authority
    monkeypatch.setattr(execution, 'authorize', lambda *args: request['day'])
    monkeypatch.setattr(authority, 'source', lambda: None)
    original_code = replay.freeze_planning.__code__
    accepted, physical, mess = op._accepted(request, stage, source)
    op.freeze_planning(request, accepted, mess, planning)
    freeze_sha = record(planning / 'V42_DAYAHEAD_DECISION_FREEZE.json')
    op.actual(request, planning, source, actual)
    assert replay.freeze_planning.__code__ is original_code
    assert record(freeze_sha['path'])['sha256'] == freeze_sha['sha256']
    decision = read(freeze_sha['path'])
    assert decision['current_P1_acceptance'] and not decision['historical_four_objective_acceptance']
    assert decision['decision']['arm'] == arm
    assert decision['decision']['MESS_OFF'] is (arm == 'B1')
    with np.load(actual / 'ACTUAL_FIXED_TRAJECTORY.npz') as archive:
        assert np.array_equal(archive['PCC_P_kw'], physical['PCC_P_kw'])
        assert np.array_equal(archive['PCC_Q_kvar'], physical['PCC_Q_kvar'])
    with np.load(actual / 'ACTUAL_MESS_TRAJECTORY.npz') as archive:
        assert np.array_equal(archive['P_kw'], mess['P_kw'])
        assert np.array_equal(archive['Q_kvar'], mess['Q_kvar'])
        assert np.array_equal(archive['locations'], mess['locations'])
        if arm == 'B2':
            assert np.array_equal(archive['SOC_kwh'], mess['SOC_kwh'])
    receipt = read(actual / 'ACTUAL_FIXED_REPLAY_RECEIPT.json')
    assert receipt['Actual_reoptimization'] == receipt['AIDC_optimizer_calls'] == receipt['MESS_optimizer_calls'] == 0


@pytest.mark.parametrize('mutation', ['rejected', 'gap', 'p2', 'wrong_day', 'lb_conflict'])
def test_only_current_accepted_p1_can_enter_operations(tmp_path, mutation):
    request, stage = fixture_stage(tmp_path, 'B1')
    source = tmp_path / 'materialize'; source.mkdir()
    if mutation == 'rejected': stage['accepted'] = False
    elif mutation == 'gap': stage['certified_gap'] = .0051
    elif mutation == 'p2': stage['P2_calls'] = 1
    elif mutation == 'wrong_day': stage['day'] = '2025-05-13'
    else: stage['LB'] = 1.1
    with pytest.raises(ValueError, match='CURRENT_P1_ACCEPTED'):
        op._accepted(request, stage, source)


def test_b2_cannot_change_its_own_fixed_aidc(tmp_path):
    request, stage = fixture_stage(tmp_path, 'B2')
    stage['planning']['PCC_P_kw'][0, 0] += .001
    source = tmp_path / 'materialize'; source.mkdir()
    with pytest.raises(ValueError, match='FIXED_AIDC_PLANNING_CHANGED'):
        op._accepted(request, stage, source)


def test_source_receipt_sha_is_verified_before_replay(tmp_path):
    request, stage = fixture_stage(tmp_path, 'B1')
    Path(stage['freeze']['path']).write_text('{}', encoding='utf-8')
    source = tmp_path / 'materialize'; source.mkdir()
    with pytest.raises(ValueError, match='SOURCE_SHA_DRIFT'):
        op._accepted(request, stage, source)


def test_source_capacities_define_exact_aidc_array_axis(tmp_path):
    request, stage = fixture_stage(tmp_path, 'B1')
    source = tmp_path / 'materialize'; source.mkdir()
    bundle = read(Path(request['input_folder']) / 'NATIVE_INPUT.json')
    bundle['capacities']['AIDC13'] = bundle['capacities'].pop('AIDC12')
    atomic(Path(request['input_folder']) / 'NATIVE_INPUT.json', bundle)
    with pytest.raises(ValueError, match='FROZEN_AIDC_SITE_AXIS'):
        op._accepted(request, stage, source)


class Elements:
    def __init__(self, names):
        self.names, self.selected, self.values = names, None, {}
    def AllNames(self): return self.names
    def Name(self, value=None):
        if value is not None: self.selected = value
        return self.selected
    def kW(self, value): self.values.setdefault(self.selected, {})['p'] = value
    def kvar(self, value): self.values.setdefault(self.selected, {})['q'] = value


def mapped_slot(p, q, locations):
    engine = SimpleNamespace(Loads=Elements(['MESS_CHG_STA01', 'MESS_CHG_STA12']),
                             Generators=Elements(['MESS_DIS_STA01', 'MESS_DIS_STA12']))
    background = SimpleNamespace(gross_p_kw_96=[{}] * 96, gross_q_kvar_96=[{}] * 96,
                                 pv_generation_kw_96=[{}] * 96)
    context = SimpleNamespace(legacy_context=(None, None, background, None, None, None))
    trajectory = FrozenTrajectory('2025-05-12', 'ACTUAL', 'B2', np.ones((96, 12)) * 10,
        np.ones((96, 12)) * 3, np.tile(p, (96, 1)), np.tile(q, (96, 1)),
        tuple(f'MESS{i:02d}' for i in range(1, 5)), np.asarray([locations] * 96), 'a' * 64)
    mapping.apply_trajectory_slot(engine, dict(loads=[], pv_generators=[]), context, trajectory, 0)
    return engine


def test_original_mess_mapping_keeps_charge_discharge_and_q_signs():
    engine = mapped_slot([12, -8, 0, 0], [4, -2, 0, 0], ['STA01', 'STA12', 'TRANSIT_STA08_STA06', 'STA12'])
    assert engine.Generators.values['MESS_DIS_STA01'] == {'p': 12., 'q': 4.}
    assert engine.Loads.values['MESS_CHG_STA01'] == {'p': 0., 'q': 0.}
    assert engine.Generators.values['MESS_DIS_STA12'] == {'p': 0., 'q': -2.}
    assert engine.Loads.values['MESS_CHG_STA12'] == {'p': 8., 'q': 0.}
    assert engine.Loads.values['IDC_IDC01'] == {'p': 10., 'q': 3.}


def test_original_mapping_aggregates_shared_service_and_rejects_transit_power():
    engine = mapped_slot([12, -8, 0, 0], [4, -2, 0, 0], ['STA01', 'STA01', 'STA12', 'STA12'])
    assert engine.Generators.values['MESS_DIS_STA01'] == {'p': 4., 'q': 2.}
    assert engine.Loads.values['MESS_CHG_STA01'] == {'p': 0., 'q': 0.}
    with pytest.raises(RuntimeError, match='NONZERO_MESS_IN_TRANSIT'):
        mapped_slot([12, -8, .1, 0], [4, -2, 0, 0], ['STA01', 'STA12', 'TRANSIT_STA08_STA06', 'STA12'])


def passing_summary():
    return dict(convergence_count=96, OpenDSS_solve_count=96, clean_engine_count=1, physical_violation=False,
        voltage_violation_count=0, line_current_violation_count=0, transformer_current_violation_count=0,
        transformer_kva_violation_count=0, schedule_mutation_count=0)


@pytest.mark.parametrize('key', ['schedule_mutation_count', 'convergence_count', 'OpenDSS_solve_count', 'clean_engine_count'])
def test_original_fresh_summary_cannot_be_pass_with_failed_execution_or_immutable_gate(key):
    summary = passing_summary()
    assert op._summary_pass(summary, True)
    summary[key] += 1
    assert not op._summary_pass(summary, True)
    assert not op._summary_pass(passing_summary(), False)


def test_original_actual_fresh_physical_exposures_remain_measured_results():
    summary = passing_summary()
    summary.update(physical_violation=True, voltage_violation_count=5,
                   line_current_violation_count=7, transformer_current_violation_count=2,
                   transformer_kva_violation_count=2, rho_max_AC=2.1)
    assert op._summary_pass(summary, True)
    assert summary['rho_max_AC'] == 2.1 and summary['physical_violation']


def test_fresh_port_routes_bindings_only_and_keeps_original_backend_body():
    from dayahead.v28r2 import opendss_backend
    original = opendss_backend.run_fresh_opendss.__code__
    source = inspect.getsource(replay.fresh)
    routed = op._fresh_port(replay.fresh, dict(vars(replay)))
    assert callable(routed) and inspect.getsource(replay.fresh) == source
    assert opendss_backend.run_fresh_opendss.__code__ is original
    assert 'model.optimize' not in inspect.getsource(op)


def test_daily_actual_axis_never_filters_or_interpolates_wrong_data(tmp_path):
    request, stage = fixture_stage(tmp_path, 'B1')
    folder = Path(request['input_folder']); original = tmp_path / 'legacy_day'; original.mkdir()
    stamps = pd.date_range('2025-05-12 00:15:00+10:00', periods=96, freq='15min')
    path = original / 'daily.parquet'
    pd.DataFrame(dict(ts_fixed_aest_end=stamps, demand_mw=np.ones(96), rooftop_pv_mw=np.zeros(96))).to_parquet(path)
    atomic(original / 'SOURCE_PROVENANCE.json', dict(daily_sources={'aemo_actual.parquet': record(path)}))
    atomic(folder / 'OPERATIONS.json', dict(current_day_folder=str(original), forecast_inputs=dict(AEMO=dict(timestamps_96=[t.isoformat() for t in stamps]))))
    op.actual_sources(request, tmp_path / 'valid')
    frame = pd.read_parquet(path); frame.loc[0, 'ts_fixed_aest_end'] += pd.Timedelta(minutes=15)
    frame.to_parquet(path)
    atomic(original / 'SOURCE_PROVENANCE.json', dict(daily_sources={'aemo_actual.parquet': record(path)}))
    with pytest.raises(ValueError, match='EXACT_DAILY_AXIS'):
        op.actual_sources(request, tmp_path / 'wrong_axis')


@pytest.mark.parametrize('arm', ['B1', 'B2'])
def test_full_original_96_slot_backend_with_native_zero_mock_engine(tmp_path, monkeypatch, arm):
    """Execute the actual preserved backend code, replacing only the engine."""
    from v42_may_campaign import execution
    from v42_regcontrol import authority, runner
    from v42_thermal import authority as thermal
    from dayahead.v28r2 import opendss_backend as backend
    request, stage = fixture_stage(tmp_path, arm)
    folder = Path(request['input_folder'])
    legacy_day = tmp_path / 'actual_daily'; legacy_day.mkdir()
    stamps = pd.date_range('2025-05-12 00:15:00+10:00', periods=96, freq='15min')
    raw = legacy_day / 'derived.parquet'
    pd.DataFrame(dict(ts_fixed_aest_end=stamps, demand_mw=np.ones(96), rooftop_pv_mw=np.zeros(96))).to_parquet(raw)
    atomic(legacy_day / 'SOURCE_PROVENANCE.json', dict(daily_sources={'aemo_actual.parquet': record(raw)}))
    atomic(folder / 'OPERATIONS.json', dict(current_day_folder=str(legacy_day), forecast_inputs=dict(AEMO=dict(timestamps_96=[t.isoformat() for t in stamps]))))
    # The B2 monthly producer has its separate arithmetic test below; supply
    # this already-derived daily source for the engine binding integration.
    original_actual_sources = op.actual_sources
    def daily_source(req, output):
        return original_actual_sources(dict(req, arm='B1'), output)
    monkeypatch.setattr(op, 'actual_sources', daily_source)
    monkeypatch.setattr(execution, 'authorize', lambda *args: request['day'])
    monkeypatch.setattr(thermal, 'current_authority', lambda: dict(transformer_current_authority_sha256=replay.CHECKER))
    bg = SimpleNamespace(gross_p_kw_96=[{}] * 96, gross_q_kvar_96=[{}] * 96, pv_generation_kw_96=[{}] * 96)
    monkeypatch.setattr(runner, 'background', lambda *args: bg)
    engines, native_calls = [], []
    class NativeAllocation:
        @classmethod
        def from_adapter(cls, adapter): return cls()
        def apply(self, engine, background, slot):
            assert background is bg
            native_calls.append((engine, slot))
            return {}, [], dict(slot=slot, background_applied_once=True)
        def validate_native_engine(self, engine):
            assert engine in engines
    def compile_engine():
        data_path = [str(tmp_path)]
        def directory(value=None):
            if value is not None:
                data_path[0] = value
            return data_path[0]
        engine = SimpleNamespace(
            Basic=SimpleNamespace(ClearAll=lambda: None, Version=lambda: 'mock-native-zero', DataPath=directory),
            Circuit=SimpleNamespace(AllNodeNames=lambda: ['bus.1'], AllBusMagPu=lambda: [1.], Losses=lambda: [0., 0.]),
            Solution=SimpleNamespace(SolveSnap=lambda: None, Converged=lambda: True, ControlActionsDone=lambda: True),
            Loads=Elements([f'MESS_CHG_STA{i:02d}' for i in range(1, 25)]),
            Generators=Elements([f'MESS_DIS_STA{i:02d}' for i in range(1, 25)]))
        engines.append(engine)
        return engine, dict(loads=[], pv_generators=[]), dict(RegControl_count=7, CapControl_count=0)
    branches = (SimpleNamespace(branch_id='line.test', phase='A'),
                SimpleNamespace(branch_id='transformer.test', phase='A'))
    src = dict(NativeAllocation=NativeAllocation, oriented_branches=lambda odd: (branches, {}),
        inventory=lambda engine: dict(RegControl_count=7, CapControl_count=0),
        native_state=lambda engine: ([1.] * 7, [1] * 4),
        branch_measurement=lambda engine, branch: (.1, .1, np.nan if branch.branch_id.startswith('line.') else .1))
    monkeypatch.setattr(authority, 'source', lambda: src)
    monkeypatch.setattr(authority, 'compile_verified', compile_engine)
    monkeypatch.setattr(authority, 'assert_inventory', lambda *args, **kwargs: True)
    monkeypatch.setattr(backend, '_native_state', lambda engine: ([1.] * 7, [1] * 4))
    original_code = backend.run_fresh_opendss.__code__
    original_bindings = {name: getattr(backend, name) for name in (
        'compile_clean_engine', 'apply_trajectory_slot', 'apply_frozen_native_state', '_branch_measurement', '_voltage_vector')}
    result = op.run(request, stage)
    assert result['PASS'] and result['Native_calls'] == 0
    assert result['Actual_reoptimization'] == result['P2_calls'] == 0
    assert result['summary']['OpenDSS_solve_count'] == 96
    assert result['all_MESS_PQ_zero'] is (arm == 'B1')
    assert len(engines) == 2 and len(native_calls) == 96
    assert [slot for engine, slot in native_calls] == list(range(96))
    assert all(engine is engines[1] for engine, slot in native_calls)
    assert backend.run_fresh_opendss.__code__ is original_code
    assert all(getattr(backend, name) is value for name, value in original_bindings.items())
    log = read(result['Fresh']['physical_input_log']['path'])['slots']
    assert len(log) == 96 and log[0]['MESS_P_kw'] == ([0.] * 4 if arm == 'B1' else [12., -8., 0., 0.])
    assert read(result['Fresh']['receipt']['path'])['Planning_tap_replay'] is False
    with pytest.raises(PermissionError, match='ATTEMPT_NEVER_REUSED'):
        op.run(request, stage)


def test_b2_monthly_actual_reuses_original_day_selection_and_pv_repeat_two(tmp_path, monkeypatch):
    from v42_holdout import realization, common as holdout
    request, stage = fixture_stage(tmp_path, 'B2')
    folder = Path(request['input_folder'])
    day = request['day']
    start = pd.Timestamp(day, tz='Etc/GMT-10')
    ending = pd.date_range(start + pd.Timedelta(minutes=15), periods=96, freq='15min')
    pv_axis = pd.date_range(start + pd.Timedelta(minutes=30), periods=48, freq='30min')
    demand, pv, weather = (tmp_path / name for name in ('monthly-demand.zip', 'monthly-pv.zip', 'monthly-weather.parquet'))
    demand.write_bytes(b'raw-authority-demand'); pv.write_bytes(b'raw-authority-pv')
    pd.DataFrame(dict(ts=pd.date_range(start, periods=96, freq='15min'), t_wb_c=np.full(96, 20.), rh_pct=np.full(96, 50.))).to_parquet(weather)
    spec = dict(exogenous_sources=dict(demand=record(demand), pv=record(pv), weather=record(weather)))
    def rows(path):
        if Path(path) == demand:
            return [dict(REGIONID='VIC1', SETTLEMENTDATE=start.strftime('%Y/%m/%d %H:%M:%S'), TOTALDEMAND='999999')] + [
                dict(REGIONID='VIC1', SETTLEMENTDATE=stamp.strftime('%Y/%m/%d %H:%M:%S'), TOTALDEMAND=str(index + 1))
                for index, stamp in enumerate(ending)]
        return [dict(REGIONID='VIC1', TYPE='MEASUREMENT', INTERVAL_DATETIME=stamp.strftime('%Y/%m/%d %H:%M:%S'), POWER=str(index + 100))
                for index, stamp in enumerate(pv_axis)]
    monkeypatch.setattr(realization, 'archive_rows', rows)
    monkeypatch.setattr(holdout, 'source_freeze', lambda: spec)
    original_code = realization.exogenous.__code__
    atomic(folder / 'SOURCE_PROVENANCE.json', dict(day=day, daily_sources={'aemo_actual.parquet': record(demand)}))
    frozen_source = record(folder / 'SOURCE_PROVENANCE.json')
    atomic(folder / 'OPERATIONS.json', dict(current_day_folder=str(folder), forecast_inputs=dict(AEMO=dict(timestamps_96=[t.isoformat() for t in ending]))))
    destination = op.actual_sources(request, tmp_path / 'post-freeze-actual')
    assert realization.exogenous.__code__ is original_code
    assert record(frozen_source['path'])['sha256'] == frozen_source['sha256']
    derived = pd.read_parquet(destination / 'DERIVED_AEMO_ACTUAL.parquet')
    assert derived.demand_mw.tolist() == list(range(1, 97))
    assert derived.rooftop_pv_mw.tolist() == np.repeat(np.arange(100, 148), 2).tolist()
    assert pd.DatetimeIndex(derived.ts_fixed_aest_end).equals(ending)
    receipt = read(tmp_path / 'post-freeze-actual/ACTUAL_SOURCE_RECEIPT.json')
    assert receipt['Native_calls'] == 0 and receipt['existing_Actual_data_rules_unchanged']


def test_real_independent_b2_input_native_zero_freeze_actual_schema(tmp_path, monkeypatch):
    """Real new input arrays; mocked acceptance is explicitly test-only."""
    from v42_may_campaign.common import ROOT
    from v42_may_campaign import execution
    from v42_regcontrol import authority
    folder = ROOT / 'runtime/v42_may_campaign/candidate_20261009_implementation01/inputs/B2/2025-05-12'
    if not (folder / 'B2_FIXED_AIDC.json').is_file():
        pytest.skip('New independent candidate input has not been generated on this host')
    fixed = read(folder / 'B2_FIXED_AIDC.json')
    protected = [record(folder / 'NATIVE_INPUT.json'), record(folder / 'B2_FIXED_AIDC.json'), fixed['physical']]
    request, mocked_stage = fixture_stage(tmp_path, 'B2')
    request['input_folder'] = str(folder)
    with np.load(fixed['physical']['path'], allow_pickle=False) as archive:
        real_arrays = {k: archive[k].copy() for k in archive.files}
    assert real_arrays['sites'].tolist() == [f'AIDC{i:02d}' for i in range(1, 13)]
    mocked_stage['planning'] = real_arrays
    mocked_stage['TEST_ONLY_MOCKED_ACCEPTANCE_NO_SCIENTIFIC_PASS_CLAIM'] = True
    source = Path(request['output']) / 'OPERATIONS/SOURCE'
    planning, actual = source.parent / 'PLANNING', source.parent / 'ACTUAL'
    for path in (source, planning, actual): path.mkdir(parents=True)
    monkeypatch.setattr(execution, 'authorize', lambda *args: request['day'])
    monkeypatch.setattr(authority, 'source', lambda: None)
    accepted, copied, mess = op._accepted(request, mocked_stage, source)
    assert set(copied) == set(real_arrays)
    assert all(np.array_equal(copied[k], real_arrays[k]) for k in copied)
    op.freeze_planning(request, accepted, mess, planning)
    op.actual(request, planning, source, actual)
    decision = read(planning / 'V42_DAYAHEAD_DECISION_FREEZE.json')['decision']
    assert len(decision['known_job_actions']) == len(fixed['selected_jobs'])
    assert {row['AIDC'] for row in decision['site_PCC_power_trajectory']} == set(real_arrays['sites'])
    with np.load(actual / 'ACTUAL_FIXED_TRAJECTORY.npz', allow_pickle=False) as archive:
        assert np.array_equal(archive['PCC_P_kw'], real_arrays['PCC_P_kw'])
        assert np.array_equal(archive['PCC_Q_kvar'], real_arrays['PCC_Q_kvar'])
    assert all(record(r['path'])['sha256'] == r['sha256'] for r in protected)
