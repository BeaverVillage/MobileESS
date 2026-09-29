from common13 import *
from stream13 import build_stream
from state13 import State,FIELDS,category
import shutil,platform,lightgbm

def main():
    LOCAL.mkdir(exist_ok=True)
    assert not (ROOT/'PREREGISTRATION.json').exists(),'Do not overwrite preregistration'
    prior=[]
    for i in range(6,13):
        folder=next((REPO/'docs').glob(f'runtime_vnext{i}_*'));manifest=folder/'DELIVERY_MANIFEST.json'
        rows=read(manifest)['files']
        for r in rows:assert sha(folder/r['relative'])==r['sha256']
        prior.append(dict(namespace=folder.name,N=len(rows),manifest=record(manifest)))
    write('BASE_PRESERVATION_RECEIPT.json',dict(time=now(),base=BASE,prior=prior))
    request=ROOT/'USER_REQUEST.txt'
    if not request.exists():
        shutil.copyfile('C:/Users/kjw39/.codex/attachments/6fd3e6e5-f2ed-4fc2-806b-3492c132a589/붙여넣은 텍스트.txt',request)
    for name in ['TEMPORAL_FOLD_CONTRACT.json','TEMPORAL_FOLD_SUPPORT.csv','FEATURE_CONTRACT.json','HAZARD_BIN_CONTRACT.json']:
        shutil.copyfile(V9/name,ROOT/name)
    source=V9/'.local/PREAPRIL_SOURCE.parquet';f=pd.read_parquet(source)
    cutoff=pd.Timestamp(read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['final_information_cutoff'])
    stream_cutoff=pd.Timestamp('2025-04-01T00:00:00Z')
    assert f.submit_time.lt(stream_cutoff).all()
    # Category vocabulary fitted only on earliest 10,000 submissions in first
    # TRAIN. It remains unavailable for earlier queries, preventing future
    # category availability from entering historical early feature rows.
    prefix=f[f.submit_time.lt(pd.Timestamp(prep(1)['fit_cutoff']))].sort_values(['submit_time','job_id'],kind='stable').head(10000)
    vocab={}
    for c in ['qos','partition']:
        counts=prefix[c].map(category).value_counts()
        ordered=sorted(counts.index,key=lambda x:(-counts[x],x))
        vocab[c]=[x for x in ordered if counts[x]>=20][:8]
    available=int(prefix.submit_time.max().timestamp())
    write('FROZEN_CATEGORY_VOCABULARY.json',dict(time=now(),categories=vocab,available_after=available,
        fit_N=len(prefix),membership=ids(prefix),fit_scope='earliest first-fold TRAIN prefix; no runtime labels',
        earlier_queries='all QoS/partition categories OTHER until t>available_after',support_min=20,max_per_field=8))
    example={c:None for c in FIELDS};state=State(vocab,available);cols=list(state.predict(example,0))
    groups={k:[c for c in cols if c.startswith(p)] for k,p in [('arrival','a_'),('pending','p_'),('running','r_'),('composition','c_'),('interaction','x_')]}
    write('CURRENT_STATE_FEATURE_CONTRACT.json',dict(time=now(),columns=cols,feature_count=len(cols),groups=groups,
        windows_seconds=[300,900,3600,21600,86400],high_GPU=16,long_wall_seconds=14400,
        quantiles='linear',empty_quantiles='NaN',empty_counts_and_shares=0,sum_scale=1000000,
        GPU_buckets=[1,4,8,16],wall_buckets_seconds=[3600,14400,43200,86400],
        interaction_dependencies={'x_gpu_arrival_3600':['arrival'],'x_wall_pending_long':['pending'],
          'x_same_partition_pending':['pending'],'x_same_qos_arrival_3600':['arrival']},
        provenance_mode='Kestrel_trace_proxy',STRICT_CAUSAL_FEATURE_COUNT=0,
        REQUEST_VERSION_AUTHORITY_FOUND=False,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False))
    write('SAME_TIMESTAMP_EVENT_CONTRACT.json',dict(time=now(),prediction='process only event_time<t; exclude ALL simultaneous events',
        later_dispatch_order=['SUBMIT','START','END'],within_type='stable job_id order after source canonical sorting',
        reason='No source sequence authority; handles zero-wait/zero-runtime episodes without leaking simultaneous events',
        duplicate='idempotent phase transition; repeated/earlier phase ignored',late_event='reject timestamp earlier than latest query/event',
        future='reject event_time>=asof',rolling_lower_bound='inclusive'))
    protocol=dict(time=now(),arms=['EXPANDING_S0','EXPANDING_S1','EXPANDING_S2','EXPANDING_S3','EXPANDING_S4','D90_S4'],
        learner=read(V9/'EXPERIMENT_PROTOCOL.json')['D1'],ranking=['Q90_pinball','reservation_actual_GPUh','Q50_MAE','coverage_std','inference_seconds'],
        S0='frozen V9 booster, same membership, full VALID parameter parity',S5='not included',D90='S4 only; 90 days before fit cutoff; static category maps refitted on D90 TRAIN',
        state_vocabulary='shared earliest first-fold TRAIN prefix, usable only after its last submit; frozen for all arms',
        C1=dict(eligibility='any C0 min-fold>=.80 AND pooled gt4h>=.80',max_challengers=1,
                select='best eligible C0 by primary ranking',method='existing V9 causal rolling14 additive shift; proper distribution support must still pass; no new calibration family'),
        gates=dict(A_pooled_Q90=[.88,.92],B_min_fold=.85,C_gt4h=.85,D_gt12h=.80,E_gt24h=.70,support_N=100,F_reservation_to_W0_max=.80,G_finite_proper_NLL=True,H_zero_support=0,I_future_reads=0),
        sharpness=dict(runtime_ratio='Q90/runtime over positive exact runtime only; median and P90; zero runtime reported separately',
                       short_job='0<runtime<=3600 seconds; ratio of summed slot-rounded Q90 GPUh to actual GPUh',slot_seconds=900),
        diagnostic_anchor='best S1/S2/S3/S4 including D90 by primary ranking; not provider selection',
        ablation='remove arrival/pending/running/composition/interaction separately; remove interactions depending on removed parent; absent group NOT_APPLICABLE; exact identical primary arm may be reused with proof',
        forensic='descriptive before-VALID snapshot vs preceding14d snapshot and next VALID; N=5 cannot establish tracking: INCONCLUSIVE unless repeatable model evidence',
        Stage_C='only if all TOTAL gates pass; no failed-model provider',
        remaining_gates=dict(pooled_Q90=[.88,.92],min_fold=.85,min_supported_age_stratum=.85,gt24h=.80,support_N=100,
           Q90_pinball='less than crude max(totalQ90-elapsed,0), tie conditional A',episode_roles='inherit TOTAL split; no cross-role checkpoint',OOF='not included'),
        April='only after TOTAL and remaining gates and frozen provider; EXPOSED_REGRESSION_ONLY',May='SEALED')
    write('EXPERIMENT_PROTOCOL.json',protocol)
    (ROOT/'CURRENT_STATE_EVENT_CONTRACT.md').write_text('''# V13 event contract

The offline adapter splits the existing pre-April GPU-job trace into a request
table and a chronological event schedule. The state module cannot access archive
rows, actual runtimes, or endpoint columns. SUBMIT carries only the nine request
proxies. START/END carry identity and their own observed timestamp only.

At query t the dispatcher delivers strictly earlier events. Every simultaneous
event is excluded; for later predictions a timestamp batch is applied in
SUBMIT, START, END order, then stable identity order. A zero-duration job can
therefore become terminal without remaining spuriously active. END can terminate
a pending cancelled episode; late START on a terminal identity is ignored.
Missing END never creates a completion. Pre-submit malformed events are excluded
individually, recorded in the adapter audit, not repaired using future endpoints.

The engine rejects future events, chronological reversals, outcome/unknown keys,
and orphan START/END. Phase transitions make duplicate events idempotent.
The checkpoint serializes version, latest event/query, identity phases, pending
and running descriptors, observed start times, rolling arrival buffers, counters,
sorted order-statistic lists, and feature cache. The dispatcher cursor is separate.
Trusted local pickle is the research checkpoint encoding.

This is event-time causality, not proof of original-submit request immutability
or scheduler delivery latency. Kestrel_trace_proxy remains research-only. The
input covers GPU-requested jobs, not every Kestrel workload. No 780-GPU divisor.
''',encoding='utf-8')
    (ROOT/'CURRENT_STATE_FEATURE_SPEC.md').write_text('''# Frozen current state features

S0 uses the same29 static V9 columns. S1 adds arrival pressure: counts5m,
15m/1h/6h/24h counts and request GPU/node/core/memory/GPU-time sums, GPU and
walltime means/medians, walltime Q75/Q90, highGPU>=16/longwall>4h/array counts
and fractions. Same-account1h/6h and sameQoS/partition1h counts, time since
strictly prior submission. Observed same-timestamp count is always0 under the
conservative contract; retrospective cohort size is deliberately unavailable.

S2 adds pending count and resource sums, GPU/wall Q50/Q90, observed submit age
Q50/Q90/max, longwall fraction, same-account count. S3 adds running count,
GPU/node/core/memory sums, elapsed Q50/Q90/max from observed START, same-account
count. S4 adds pending/running controlled QoS/partition shares plus OTHER,
GPU-size/walltime bucket shares, entropy and HHI, and four explicit interactions
listed in the JSON contract. No actual runtime enters any state feature.

TRAIN-prefix vocabulary is unavailable before its own observation cutoff; early
category shares map to OTHER. Raw matching account/partition/QoS counts use only
observed identities and never a job-ID predictive lookup. Job IDs solely maintain
event lifecycle. Empty sums/counts/shares are0; empty quantiles/ages/means NaN.
Resource sums use fixed micro-unit integers for deterministic insert/delete.
Age quantiles use t minus the reverse quantile of observed submit/start times.
The rolling lower endpoint is inclusive, upper endpoint strict. There are no
runtime-completion aggregates, absolute calendar features or capacity divisors.
''',encoding='utf-8')
    (ROOT/'.gitignore').write_text('.local/\n__pycache__/\n',encoding='utf-8')
    (ROOT/'.gitattributes').write_text('* -text\nFOLD_MODELS/** linguist-generated=true\n',encoding='utf-8')
    write('EXECUTION_ENVIRONMENT.json',dict(python=platform.python_version(),pandas=pd.__version__,numpy=np.__version__,lightgbm=lightgbm.__version__,backend='CPU4 deterministic'))
    roles=[]
    for i in range(1,6):
        for role in ['TRAIN','CAL','VALID']:
            path=V9/'.local'/f'fold{i}'/(role+'.parquet');g=pd.read_parquet(path)
            assert ids(g)==read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds'][i-1]['membership'][role]
            roles.append(dict(fold=i,role=role,**record(path)))
    write('SOURCE_MANIFEST.json',dict(time=now(),base=BASE,source=record(source),roles=roles,prior_manifests=prior,
        label_information_cutoff=str(cutoff),stream_cutoff=str(stream_cutoff),April_payload_read=False,May_payload_read=False))
    names=['CURRENT_STATE_EVENT_CONTRACT.md','SAME_TIMESTAMP_EVENT_CONTRACT.json','CURRENT_STATE_FEATURE_SPEC.md',
           'CURRENT_STATE_FEATURE_CONTRACT.json','FROZEN_CATEGORY_VOCABULARY.json','EXPERIMENT_PROTOCOL.json',
           'TEMPORAL_FOLD_CONTRACT.json','HAZARD_BIN_CONTRACT.json','state13.py','stream13.py']
    write('PREREGISTRATION.json',dict(time=now(),files=[record(ROOT/n) for n in names],before_forensic=True,before_ML=True))
    write('TRAINING_CODE_FREEZE.json',dict(time=now(),files=[record(ROOT/n) for n in ['model13.py','train13.py','calibration13.py']],before_training=True))
    build_stream(f,stream_cutoff)
    print('V13_REGISTERED',len(cols),sum(g['N'] for g in prior),'preserved files',flush=True)
if __name__=='__main__':main()
