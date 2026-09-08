"""V41R4 data-only calibration. No optimizer or electrical engine imports.

The immutable output contains aggregate feeder residuals, not invented local
forecast errors. The original V16.2 physical mapping is the unit authority.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import builtins
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import sys
import time
import zipfile

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
ROOT = Path('D:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
RAW = Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터')
OLD = ROOT/'dayahead/artifacts/v41r3_fast_power_scale_freeze'
SCALE = ROOT/'dayahead/artifacts/v41r3_scale_rebalance'
TZ = timezone(timedelta(hours=10))
START, END = '2025-01-01', '2025-04-29'
RECORDS = {}


def record(path):
    p = Path(path).resolve()
    if str(p) not in RECORDS:
        with p.open('rb') as f:
            sha = hashlib.file_digest(f, 'sha256').hexdigest()
        RECORDS[str(p)] = dict(path=str(p), sha256=sha, bytes=p.stat().st_size)
    return RECORDS[str(p)]


def read(path):
    record(path)
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(name, value):
    p = OUT/name
    with p.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')
    assert read(p) == value
    return record(p)


def load_mapping():
    """Load only the pure, frozen data-mapping module by exact file path."""
    p = ROOT/'dayahead/grid_background_v16_2.py'
    record(p)
    spec = importlib.util.spec_from_file_location('v41r4_frozen_background', p)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    sources = read(SCALE/'V41R3_BACKGROUND_INPUT_PROVENANCE.json')['raw_exogenous_sources']
    by_sha = {r['sha256']: Path(r['path']) for r in sources}
    refs = {}
    for key, expected in module.EXPECTED_SHA256.items():
        if key == 'pv_reference':
            # Already frozen normalization constant, not a numerical input.
            refs[key] = dict(sha256=expected, status='FROZEN_NORMALIZATION_ONLY_NOT_READ')
            continue
        p = by_sha[expected]
        refs[key] = record(p)
        assert refs[key]['sha256'] == expected, ('MAPPING_DRIFT', key)
    paths = module.BackgroundSourcePaths(**{k: Path(v['path']) if 'path' in v else Path('NOT_READ') for k,v in refs.items()})
    module._verify_sources = lambda _: refs
    return module, paths, refs


def archive_values(path, kind):
    """Read values only inside the authorized window; reject duplicate rows."""
    datecol, valcol = ('SETTLEMENTDATE','TOTALDEMAND') if kind == 'demand' else ('INTERVAL_DATETIME','POWER')
    lo, hi = '2025/01/01 00:00:00', '2025/04/30 00:00:00'
    selected = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.lower().endswith('.csv'):
                continue
            with z.open(name) as stream:
                headers = {}
                for row in csv.reader(io.TextIOWrapper(stream, encoding='utf-8-sig')):
                    if row and row[0] == 'I':
                        headers[tuple(row[1:4])] = row[4:]
                    elif row and row[0] == 'D' and tuple(row[1:4]) in headers:
                        r = dict(zip(headers[tuple(row[1:4])], row[4:]))
                        stamp = r.get(datecol, '')
                        # Calendar filter precedes value conversion/access.
                        if not lo < stamp <= hi or r.get('REGIONID') != 'VIC1':
                            continue
                        if kind == 'pv' and r.get('TYPE') != 'MEASUREMENT':
                            continue
                        selected.append((stamp, float(r[valcol])))
    frame = pd.DataFrame(selected, columns=['timestamp','value'])
    frame['timestamp'] = pd.to_datetime(frame.timestamp, format='%Y/%m/%d %H:%M:%S').dt.tz_localize(TZ)
    return frame


def forecast_path(day):
    if day < '2025-04-01':
        return WORK/'MobileESS_v29r1_reliability_calibrated_noregret/cache/v29r1_trust_cert_sources/jan_mar_2025/days'/day/'aemo_forecast.json'
    return WORK/'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/april_2025/days'/day/'aemo_forecast.json'


def rank_contract():
    names = ('V41R3_COMPOUND_RANKING_COMPLETION_AUDIT.json',
             'V41R3_COMPOUND_REAL_CONSUMPTION_READBACK.json',
             'V41R3_RESTORED_CANDIDATE_DOMAIN.json')
    a, b, c = [read(OLD/'final_four_method'/n) for n in names]
    assert all(v['status'] == 'PASS' for v in (a,b,c))
    assert a['COMPOUND_NET_EFFECT_COMPUTED'] == a['COMPOUND_NET_EFFECT_USED_IN_ORDERING'] == 'YES'
    assert b['COMPOUND_NET_EFFECT_USED_IN_REAL_SEARCH'] == 'YES'
    assert a['candidate_count'] == b['candidate_count'] == c['total'] == 4889827
    assert a['candidate_set_SHA'] == b['candidate_set_SHA'] == c['candidate_set_SHA']
    for r in a['source_files']:
        assert record(r['path'])['sha256'] == r['sha256'], ('RANKING_SOURCE_DRIFT',r['path'])
    assert record(c['manifest']['path'])['sha256'] == c['manifest']['sha256']
    return dict(status='PASS', candidate_count=c['total'], candidate_set_SHA=c['candidate_set_SHA'],
                temporal_choices=c['restored_count'], TIMESHIFTING_ACTIVE=True,
                COMPOUND_NET_EFFECT_COMPUTED='YES', COMPOUND_NET_EFFECT_USED_IN_ORDERING='YES',
                new_candidates=0, removed_candidates=0, evidence=[record(OLD/'final_four_method'/n) for n in names])


def main():
    started = time.perf_counter()
    assert not (OUT/'V41R4_PREMAY_EMPIRICAL_UNCERTAINTY_AUTHORITY.json').exists(), 'AUTHORITY_ALREADY_FROZEN'
    original_import = builtins.__import__
    def guarded(name, *a, **k):
        assert not any(s in name.lower() for s in ('gurobi','opendss','dss_python','dss_capi','optimizer','electrical_context')), ('FORBIDDEN_HISTORICAL_IMPORT',name)
        return original_import(name, *a, **k)
    builtins.__import__ = guarded
    ranking = rank_contract()
    prerequisite=OUT/'V41R4_V41R3_RANKING_PREREQUISITE.json'
    if prerequisite.exists():
        assert read(prerequisite)==ranking
    else:
        save(prerequisite.name, ranking)
    bg, paths, mapping_sources = load_mapping()
    qlookup = bg._lookup(paths.q_lookup, ('month','day_type','slot_30min'), 'q_variation_factor')
    # Read the issue-time implementation without importing any project runtime.
    issue_source = record(ROOT/'dayahead/v41/data.py')
    import ast
    tree = ast.parse(Path(issue_source['path']).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == 'issue_time')
    namespace = dict(pd=pd, timezone=timezone, timedelta=timedelta)
    exec(compile(ast.Module(body=[node],type_ignores=[]),issue_source['path'],'exec'), namespace)
    cutoff = namespace['issue_time']('2025-05-01').tz_convert(TZ)
    last_complete = (cutoff.normalize()-pd.Timedelta(days=1)).date().isoformat()
    assert last_complete == END, ('ISSUE_TIME_CUTOFF_CONFLICT',str(cutoff),last_complete)
    raw_files = [p for folder in ('AEMO','전력 데이터 AEMO Victoria','AEMO rooftop PV 자료') for p in (RAW/folder).rglob('*.zip')]
    actual = {'demand': [], 'pv': []}
    actual_sources = {'demand': [], 'pv': []}
    for month in range(1,5):
        for kind, family in [('demand','DISPATCHREGIONSUM'), ('pv','ROOFTOP_PV_ACTUAL')]:
            filename = f'PUBLIC_ARCHIVE#{family}#FILE01#2025{month:02}010000.zip'
            matches = [p for p in raw_files if p.name == filename]
            # Multiple copies must be byte-identical to share authority.
            assert matches, ('HISTORICAL_ARCHIVE_MISSING',filename)
            assert len({record(p)['sha256'] for p in matches}) == 1, ('CONFLICTING_ARCHIVES',filename)
            p = sorted(matches, key=str)[0]
            actual_sources[kind].append(record(p))
            actual[kind].append(archive_values(p,kind))
            print('HISTORICAL_DATA_READ',kind,month,flush=True)
    actual = {k:pd.concat(v,ignore_index=True) for k,v in actual.items()}
    rows, excluded, residuals, forecasts = [], [], {}, []
    for date in pd.date_range(START, END, freq='D'):
        day = date.date().isoformat(); p = forecast_path(day)
        if not p.exists():
            excluded.append(dict(day=day,reasons=['MISSING_CAUSAL_FORECAST'])); continue
        f = read(p); manifest = read(p.parent/'source_day_manifest.json')
        for cat in ('causal_grid_demand_forecast_vintage','causal_rooftop_pv_forecast_vintage'):
            assert manifest['categories'][cat]['sha256'] == record(p)['sha256'], ('FORECAST_DRIFT',day)
        start = pd.Timestamp(day,tz=TZ); end = start+pd.Timedelta(days=1)
        expected_end = pd.date_range(start+pd.Timedelta(minutes=15), end, freq='15min')
        assert list(pd.to_datetime(f['timestamps_96'])) == list(expected_end), ('FORECAST_AXIS',day)
        assert pd.Timestamp(f['cutoff_fixed_aest']) == start-pd.Timedelta(hours=6)
        assert all(pd.Timestamp(f[k]) <= pd.Timestamp(f['cutoff_fixed_aest']) for k in ('demand_issue','pv_issue'))
        assert end <= cutoff
        values, reasons = {}, []
        for kind, minutes in [('demand',5),('pv',30)]:
            a = actual[kind]; a = a[(a.timestamp>start)&(a.timestamp<=end)]
            axis = pd.date_range(start+pd.Timedelta(minutes=minutes),end,freq=f'{minutes}min')
            if a.timestamp.duplicated().any(): reasons.append(kind+'_DUPLICATE_ACTUAL');continue
            s = a.set_index('timestamp').value.reindex(axis)
            if not np.isfinite(s.to_numpy()).all(): reasons.append(kind+'_MISSING_OR_NONFINITE_ACTUAL');continue
            values[kind] = s.reindex(expected_end).to_numpy() if kind=='demand' else np.repeat(s.to_numpy(),2)
        if reasons:
            excluded.append(dict(day=day,reasons=reasons));continue
        demand = np.asarray(f['demand_mw_96']); pv = np.asarray(f['pv_mw_96'])
        assert demand.shape == pv.shape == (96,) and np.isfinite([demand,pv]).all()
        p_factor = bg.ALPHA_GRID * bg.IEEE123_NATIVE_P_KW / bg.P95_REFERENCE_MW
        pv_factor = bg.ALPHA_GRID * bg.PV_CAPACITY_EXPECTED_KW / bg.PV_REFERENCE_MAX_MW
        p_da = demand*p_factor + pv*pv_factor
        p_ac = values['demand']*p_factor + values['pv']*pv_factor
        def qfac(axis):
            return np.array([bg.IEEE123_NATIVE_Q_KVAR/bg.IEEE123_NATIVE_P_KW * qlookup[(t.month,'weekday' if t.weekday()<5 else 'weekend',t.hour*2+t.minute//30)] for t in axis])
        # Exact production semantics: DA mapper receives interval-end stamps;
        # Actual mapper receives interval-start stamps. Pair by interval identity.
        r = dict(P_BG_kW=p_ac-p_da,
                 Q_BG_kvar=p_ac*qfac(expected_end-pd.Timedelta(minutes=15))-p_da*qfac(expected_end),
                 PV_P_kW=(values['pv']-pv)*pv_factor)
        e_net = r['P_BG_kW']-r['PV_P_kW']
        assert np.allclose(e_net,(values['demand']-demand)*p_factor,rtol=0,atol=1e-10)
        h,l = float(np.quantile(e_net,.95,method='linear')),float(np.quantile(e_net,.05,method='linear'))
        rows.append(dict(day=day,H_d_kW=h,L_d_kW=l))
        residuals[day] = {k:v.tolist() for k,v in r.items()}
        forecasts.append(dict(day=day,source=record(p),manifest=record(p.parent/'source_day_manifest.json'),
                              demand_source_sha256=f['demand_source_sha256'],pv_source_sha256=f['pv_source_sha256'],
                              demand_issue=f['demand_issue'],pv_issue=f['pv_issue']))
    assert len(rows)>1
    ht=float(np.quantile([r['H_d_kW'] for r in rows],.9,method='linear'))
    lt=float(np.quantile([r['L_d_kW'] for r in rows],.1,method='linear'))
    high=min(rows,key=lambda r:(abs(r['H_d_kW']-ht),r['day']))
    low=min(rows,key=lambda r:(abs(r['L_d_kW']-lt),r['day']))
    assert high['day'] != low['day'], 'SAME_UPPER_LOWER_DAY_FAIL_CLOSED'
    # Cross-check analytical aggregate calculations against original pure mapper.
    checks=[]
    for selected in (high,low):
        day=selected['day']; f=read(forecast_path(day)); da=bg.build_authority_background_binding(timestamps_fixed_aest=f['timestamps_96'],demand_mw_96=f['demand_mw_96'],rooftop_pv_mw_96=f['pv_mw_96'],paths=paths)
        start=pd.Timestamp(day,tz=TZ);end=start+pd.Timedelta(days=1)
        vals={}
        for kind,minutes in [('demand',15),('pv',30)]:
            a=actual[kind].set_index('timestamp').value
            v=a.reindex(pd.date_range(start+pd.Timedelta(minutes=minutes),end,freq=f'{minutes}min')).to_numpy()
            vals[kind]=v if kind=='demand' else np.repeat(v,2)
        ac=bg.build_authority_background_binding(timestamps_fixed_aest=[t.isoformat() for t in pd.date_range(start,periods=96,freq='15min')],demand_mw_96=vals['demand'],rooftop_pv_mw_96=vals['pv'],paths=paths)
        errors={}
        for key,field in [('P_BG_kW','gross_p_kw_96'),('Q_BG_kvar','gross_q_kvar_96'),('PV_P_kW','pv_generation_kw_96')]:
            got=np.array([sum(r.values()) for r in getattr(ac,field)])-np.array([sum(r.values()) for r in getattr(da,field)])
            errors[key]=float(np.max(np.abs(got-np.array(residuals[day][key]))))
        assert max(errors.values())<1e-8
        checks.append(dict(day=day,absolute_error=errors))
    # Freeze every day's arrays so selection can be independently reproduced.
    residual_ref=save('V41R4_ALL_ELIGIBLE_RESIDUALS.json',dict(days=residuals,units=dict(P_BG_kW='kW',Q_BG_kvar='kvar',PV_P_kW='kW')))
    value=dict(schema='V41R4_PREMAY_EMPIRICAL_UNCERTAINTY_V1',status='FROZEN',
        calibration_start=START,calibration_end=END,eligible_day_count=len(rows),excluded_days=excluded,
        earliest_May_issue_fixed_AEST=cutoff.isoformat(),issue_time_source=issue_source,
        eligible_actual_interval_end_max=(pd.Timestamp(max(residuals),tz=TZ)+pd.Timedelta(days=1)).isoformat(),
        timezone='FIXED_AEST_UTC_PLUS_10_NO_DST',resolution_minutes=15,
        common_granularity='Aggregate feeder P/Q/PV; raw observed error authority VIC1 regional total; no observed bus/phase error claim',
        signal_authority=dict(
            P_BG='Frozen gross-background mapping of paired VIC1 operational demand and rooftop PV',
            Q_BG='Derived paired Q through existing Jemena Q/P seasonal profile; no independent measured reactive-power forecast-error claim',
            PV_P='VIC1 POWERMEAN forecast vs TYPE=MEASUREMENT POWER Actual, frozen feeder PV scaling',
            PV_Q='NO_AUTHORITATIVE_FORECAST_ACTUAL_PAIR; not perturbed; existing unity-PF PV preserved'),
        alignment=dict(forecast='30-min interval-end values repeated twice at 15-min ends',
            actual_demand='Native 5-min records required complete; exact quarter-hour endpoint sample, unchanged production rule',
            actual_PV='Complete 30-min MEASUREMENT duplicated twice; energy conserved',
            physical_mapping_timestamps='Inherited DA interval-end and Actual interval-start; paired on common interval identity',
            missing='Exclude whole day on missing/nonfinite/duplicate Actual; never fill, shuffle or substitute'),
        scaling=dict(alpha_BG=1.6,residuals_include_alpha_BG=False,ALPHA_GRID=bg.ALPHA_GRID,
            historical_physical_normalization_is_frozen=True,PV_outside_alpha_BG=True,
            application='1.60*(May nominal aggregate BG + selected aggregate BG residual); distribute via unchanged target-day nominal phase shares. PV nominal + selected PV residual.'),
        d_HIGH=high['day'],H_d_HIGH_kW=high['H_d_kW'],H_target_kW=ht,
        d_LOW=low['day'],L_d_LOW_kW=low['L_d_kW'],L_target_kW=lt,
        daily_scores=rows,selected_residuals=dict(S1=residuals[high['day']],S2=residuals[low['day']]),
        residual_archive=residual_ref,selection_algorithm=dict(upper='daily q95 -> empirical q90 nearest day',lower='daily q05 -> empirical q10 nearest day',quantile_method='linear',tie_break=['smaller absolute distance','earlier date'],weights=None,selection_frozen_for_all_May_days_and_policies=True),
        actual_sources=actual_sources,forecast_sources=forecasts,mapping_sources=mapping_sources,
        source_inventory=list(RECORDS.values()),aggregate_mapper_crosschecks=checks,
        ranking_prerequisite=ranking,HISTORICAL_OPTIMIZATION_CALLS=0,HISTORICAL_OPENDSS_CALLS=0,
        MAY_DATA_USED=False,MAY04_ACTUAL_USED=False,ML_RETRAIN_COUNT=0,ML_RECALIBRATION_COUNT=0,ML_MODEL_CHANGE_COUNT=0,
        forbidden_import_guard='Optimization/electrical engine imports rejected throughout calibration',
        calibration_seconds=time.perf_counter()-started,
        file_SHA_convention='Exact final file SHA256 in adjacent .sha256 and V41R4_UNCERTAINTY_AUTHORITY_SEAL.json; self-referential file hash excluded')
    ref=save('V41R4_PREMAY_EMPIRICAL_UNCERTAINTY_AUTHORITY.json',value)
    (OUT/'V41R4_PREMAY_EMPIRICAL_UNCERTAINTY_AUTHORITY.json.sha256').write_text(ref['sha256']+'  '+Path(ref['path']).name+'\n',encoding='ascii')
    save('V41R4_UNCERTAINTY_AUTHORITY_SEAL.json',dict(status='FROZEN',authority=ref,residuals=residual_ref,construction_source=record(__file__),d_HIGH=high['day'],d_LOW=low['day'],MAY_DATA_USED=False,MAY04_ACTUAL_USED=False))
    print(json.dumps(dict(eligible_days=len(rows),excluded=len(excluded),high=high,low=low,H_target=ht,L_target=lt,seconds=value['calibration_seconds'])),flush=True)


if __name__=='__main__':
    main()
