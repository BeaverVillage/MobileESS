"""Independent pooled metric/bootstrap replay from frozen predictions only."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['Q90_coverage','calibration_error','normalized_Q90_pinball','requirement_ratio',
         'high_load_coverage','positive_coverage','normalized_Q50_pinball']
ROLES = ['EXPOSED_EVALUATION','MAY_HISTORICAL']


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def metric(y, q50, q90, width, threshold, scale, resolution):
    error = y-q90
    coverage = float(np.mean(y <= q90))
    high, positive = y > threshold, y > 0
    reserve_y = y[:, -1].sum() if resolution == 'CUM' else y.sum()
    reserve_q = q90[:, -1].sum() if resolution == 'CUM' else q90.sum()
    return np.array([coverage, abs(coverage-.9), np.mean(np.maximum(.9*error,-.1*error)/width/scale),
        reserve_q/reserve_y if reserve_y > 0 else np.nan,
        np.mean((y <= q90)[high]) if high.any() else np.nan,
        np.mean((y <= q90)[positive]) if positive.any() else np.nan,
        np.mean(.5*np.abs(y-q50)/width/scale)])


def unpack(frame, resolution):
    frame = frame.sort_values(['day','block'])
    days = frame.day.drop_duplicates().to_numpy()
    count = {'H1':24,'H3':8,'H6':4,'CUM':24}[resolution]
    assert len(frame) == len(days)*count
    assert np.array_equal(frame.block, np.tile(np.arange(count), len(days)))
    arrays = [frame[key].to_numpy().reshape(len(days), count) for key in ['actual','Q50','Q90','duration','high_load_threshold']]
    assert all(np.isfinite(a).all() for a in arrays)
    assert np.array_equal(arrays[3], np.broadcast_to(arrays[3][0], arrays[3].shape))
    assert np.array_equal(arrays[4], np.broadcast_to(arrays[4][0], arrays[4].shape))
    return days, arrays[:3]+[arrays[3][0],arrays[4][0]]


def main():
    assert (ROOT/'EVALUATION_COMPLETE.json').exists() and not (ROOT/'UNCERTAINTY_AUDIT.json').exists()
    complete, frozen, protocol = [read(ROOT/n) for n in ['EVALUATION_COMPLETE.json','FINAL_SELECTION_FREEZE.json','PROTOCOL.json']]
    assert sha(ROOT/'PREDICTIONS.parquet') == complete['prediction_sha256']
    assert sha(ROOT/'FINAL_SELECTION_FREEZE.json') == complete['freeze_sha256']
    assert sha(ROOT/'PROTOCOL.json') == frozen['protocol_sha256']
    for name,digest in frozen['code'].items(): assert sha(ROOT/name) == digest
    assert protocol['bootstrap']['draws'] == 2000 and protocol['bootstrap']['blocks'] == [1,7]
    scale = protocol['normalizer']['value']; assert np.isfinite(scale) and scale > 0
    final = pd.read_parquet(ROOT/'PREDICTIONS.parquet')
    recorded = pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv')
    key = ['role','resolution','method','reference_resolution','reference_method','contrast','metric','block_observed_days']
    assert len(recorded) == 252 and not recorded.duplicated(key).any()
    assert set(recorded.role) == set(ROLES) and set(recorded.metric) == set(NAMES)
    assert set(recorded.resolution) == {'H3','H6','CUM'} and set(recorded.block_observed_days) == {1,7}
    findings, largest, draw_count = [], 0., 0
    for role in ROLES:
        role_frame = final[final.role.eq(role)]
        groups = {}
        for resolution in ['H1','H3','H6','CUM']:
            for method in ['DIRECT','AGGREGATED_H1']:
                groups[(resolution,method)] = unpack(role_frame[role_frame.resolution.eq(resolution) & role_frame.method.eq(method)], resolution)
        for resolution in ['H3','H6','CUM']:
            comparisons = [('DIRECT','AGGREGATED_H1',resolution,'SAME_TARGET_DIRECT_EFFECT'),
                           ('DIRECT','DIRECT','H1','RESOLUTION_EFFECT'),
                           ('AGGREGATED_H1','DIRECT','H1','RESOLUTION_EFFECT')]
            for method, reference_method, reference_resolution, contrast in comparisons:
                days,a = groups[(resolution,method)]; other_days,b = groups[(reference_resolution,reference_method)]
                assert np.array_equal(days,other_days)
                n = len(days)
                point = metric(*a,scale,resolution)-metric(*b,scale,reference_resolution)
                for block in [1,7]:
                    rng = np.random.default_rng(protocol['bootstrap']['seed'])
                    samples = []
                    for _ in range(2000):
                        starts = rng.integers(n,size=int(np.ceil(n/block)))
                        index = np.concatenate([(start+np.arange(block)) % n for start in starts])[:n]
                        av = [v[index] for v in a[:3]]+a[3:]
                        bv = [v[index] for v in b[:3]]+b[3:]
                        samples.append(metric(*av,scale,resolution)-metric(*bv,scale,reference_resolution))
                    samples = np.asarray(samples); draw_count += 2000
                    for k,name in enumerate(NAMES):
                        selected = recorded[recorded.role.eq(role) & recorded.resolution.eq(resolution) & recorded.method.eq(method)
                            & recorded.reference_resolution.eq(reference_resolution) & recorded.reference_method.eq(reference_method)
                            & recorded.contrast.eq(contrast) & recorded.metric.eq(name) & recorded.block_observed_days.eq(block)]
                        assert len(selected) == 1
                        row = selected.iloc[0]; invalid = int((~np.isfinite(samples[:,k])).sum())
                        lo,hi = (np.nan,np.nan) if invalid else np.quantile(samples[:,k],[.025,.975])
                        actual, expected = np.array([point[k],lo,hi]), row[['delta','CI95_low','CI95_high']].to_numpy(float)
                        assert np.array_equal(np.isnan(actual),np.isnan(expected)), (role,resolution,method,name,'NAN_PATTERN')
                        assert np.allclose(actual,expected,atol=1e-10,rtol=2e-12,equal_nan=True), (role,resolution,method,name,block)
                        assert row.nonfinite_draws == invalid and row.N_days == n and row.draws == 2000
                        valid = np.isfinite(actual)
                        error = float(np.max(abs(actual[valid]-expected[valid]))) if valid.any() else 0.
                        largest = max(largest,error)
                        findings.append(dict(role=role,resolution=resolution,method=method,reference_resolution=reference_resolution,
                            contrast=contrast,metric=name,block=block,nonfinite_draws=invalid,maximum_error=error))
    assert len(findings) == 252 and draw_count == 72000
    receipt = dict(PASS=True,time=pd.Timestamp.now(tz='UTC').isoformat(),source_sha256=sha(__file__),
        rows_checked=len(findings),bootstrap_draws_recomputed=draw_count,maximum_absolute_difference=largest,
        invalid_CI_rows=sum(item['nonfinite_draws'] > 0 for item in findings),invalid_draws_never_dropped_or_resampled=True,
        CUM_reserve_terminal_only=True,whole_day_prefix_dependence_preserved=True,study_imports=0,
        prediction_sha256=sha(ROOT/'PREDICTIONS.parquet'),uncertainty_sha256=sha(ROOT/'PAIRED_UNCERTAINTY.csv'),
        limitations=['unadjusted per-contrast95% intervals, no simultaneous familywise guarantee',
                    'frozen-forecast conditional; no refit/selection uncertainty','resolution contrasts have different outcome/high-load definitions',
                    'May exposed historical diagnostic','inherited proxy UNVERIFIED/UNOBSERVED'],findings=findings)
    with (ROOT/'UNCERTAINTY_AUDIT.json').open('x',encoding='utf-8') as stream: json.dump(receipt,stream,indent=2)
    print('UNCERTAINTY AUDIT PASS',len(findings),largest)


if __name__ == '__main__': main()
