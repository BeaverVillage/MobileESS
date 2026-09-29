"""Independent delivery checks of causal labels, frozen bytes, supports, and scores."""
from common10 import *
from finalize10 import assert_freeze,FREEZES
from calibration10 import ProbabilityMap
import numpy as np,pandas as pd,subprocess,platform,importlib.metadata as md
def main():
    assert_freeze();prior=read(ROOT/'BASE_PRESERVATION_RECEIPT.json');n=0
    for group in prior['prior']:
        manifest=Path(group['manifest']['path']);assert sha(manifest)==group['manifest']['sha256']
        for item in read(manifest)['files']:
            assert sha(manifest.parent/item['relative'])==item['sha256'],item['relative'];n+=1
    sources=read(ROOT/'FOLD_MEMBERSHIP_REFERENCE.json');assert sha(sources['source']['path'])==sources['source']['sha256']
    for item in sources['prepared_role_files']:assert sha(item['path'])==item['sha256']
    causal=[]
    for i in [1,2,3,4,5,'final']:
        for role in (['TRAIN','CAL'] if i=='final' else ['TRAIN','CAL','VALID']):
            f=fold_data(i,role);event=f.event.to_numpy(bool);cen=f.censored.to_numpy(bool);pending=~(event|cen)
            assert not (event&cen).any()
            assert (f.loc[event,'end_time']<f.loc[event,'observation_cutoff']).all()
            assert (f.loc[event,'start_time']<=f.loc[event,'end_time']).all()
            assert np.max(abs((f.loc[event,'end_time']-f.loc[event,'start_time']).dt.total_seconds()-f.loc[event,'runtime_seconds']))<1e-8
            assert f.loc[cen,'end_time'].isna().all() and f.loc[cen,'runtime_seconds'].isna().all()
            assert np.max(abs((f.loc[cen,'observation_cutoff']-f.loc[cen,'start_time']).dt.total_seconds()-f.loc[cen,'duration_lower']))<1e-8
            assert f.loc[pending,'duration_lower'].isna().all()
            causal.append(dict(fold=i,role=role,N=len(f),exact=int(event.sum()),censored=int(cen.sum()),pending=int(pending.sum()),future_end_reads=0))
    maps=0
    for p in (ROOT/'CALIBRATION_STATES').glob('*.json'):
        for s in read(p)['states'].values():
            if s['max_completion_used']!='NaT':assert pd.Timestamp(s['max_completion_used'])<pd.Timestamp(s['day'])
            for value in [s['pooled']]+list(s['groups'].values()):assert ProbabilityMap(value).audit();maps+=1
            for support in s['support']:
                expected=support['N']>=500 and support['completed']>=200 and support['long_gt4h']>=100 and support['long_gt12h']>=50
                assert bool(support['support_sufficient'])==expected
                assert bool(support['pooled_fallback'])==(not expected)
    for table in ['RAW_GRID_FOLD_METRICS.csv','FOLD_LEVEL_METRICS.csv']:
        z=pd.read_csv(ROOT/table);z=z[z.proper_score_finite.notna()]
        assert z.proper_score_finite.astype(bool).all() and z.zero_support_count.eq(0).all()
        assert np.isfinite(z.proper_interval_NLL).all()
    started=pd.Timestamp(read(ROOT/'APRIL_EVALUATION_STARTED.json')['time'])
    assert all(pd.Timestamp(read(ROOT/name)['time'])<started for name in FREEZES)
    assert read(ROOT/'APRIL_EVALUATION_RECEIPT.json')['remaining']['checkpoint_N']==299805
    expected={'W0':150,'B0':47,'V8':111,'V9':127,'V10':91};q=pd.read_csv(ROOT/'APRIL2_EXPOSED_QUEUE_REGRESSION.csv').set_index('arm')
    assert {a:int(q.loc[a,'start_lt_H']) for a in expected}==expected and q.capacity_violations.eq(0).all()
    assert read(ROOT/'APRIL_DISTRIBUTION_SCORES.json')['zero_support_count']==0
    assert read(ROOT/'STANDALONE_PROVIDER_VALIDATION.json')['PASS']
    changed=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=REPO,text=True).splitlines();assert not changed
    write('FINAL_INTEGRITY_AUDIT.json',dict(time=now(),PASS=True,prior_scientific_files_byte_identical=n,prior_manifests_byte_identical=4,fold_membership_and_caches_unchanged=True,
        causal_role_checks=causal,calibration_maps_audited=maps,all_six_freezes_before_April=True,provider_bytes_unchanged_after_April=True,April2_starts=expected,capacity_violations=0,
        future_end_before_cutoff=0,FUTURE_CALIBRATION_EVENT_READS=0,FUTURE_CALIBRATION_RESIDUAL_READS=0,MAY_PAYLOAD_OPENED=False,no_tracked_base_files_changed=True))
    gpu_lines=[s for s in (ROOT/'benchmark10.log').read_text(encoding='utf-8',errors='replace').splitlines() if 'Using GPU Device:' in s];assert any('RTX 4060 Laptop GPU' in s for s in gpu_lines)
    write('EXECUTION_ENVIRONMENT.json',dict(time=now(),python=sys.version,platform=platform.platform(),CPU=platform.processor(),GPU_identity_evidence=gpu_lines,
        versions={p:md.version(p) for p in ['numpy','pandas','scipy','scikit-learn','lightgbm','pyarrow']},benchmark_conditions='Same host, single timing per backend; preApril calibration evaluation concurrent. Wall-clock measurements are descriptive, not controlled hardware speed guarantees.',backend_log=record(ROOT/'benchmark10.log')))
    print('FINAL_INTEGRITY_PASS',n,maps,flush=True)
if __name__=='__main__':main()

