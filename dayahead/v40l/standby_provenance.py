"""Read-only key provenance across three already opened blocks; no predictions."""
import collections
import pickle
from io import BytesIO
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .common import *
from .data import base_features,keys

STAGES=[('Apr-01--07','VISIBLE_DEVELOPMENT'),('Apr-08--14','CALIBRATION'),('Apr-15--23','SELECTION')]
def qstats(a):
    a=np.asarray(a,float)
    return dict(zip(['P5','P50','P95','max'],np.quantile(a,[.05,.5,.95,1]).tolist())) if len(a) else {k:None for k in ['P5','P50','P95','max']}
def canonical(row):
    result=[]
    for i,c in enumerate(F9):
        v=row[c]
        if pd.isna(v):v='__MISSING__'
        elif i<5:v=float(v)
        else:v=str(v)
        result.append(v)
    return tuple(result)
def profile_id(k):return hashlib.sha256(json.dumps(k,default=str).encode()).hexdigest()
def main():
    protected=['V40L_TAIL_SELECTION_COMPARISON.json','V40L_FINAL_STATUS.json','V40L_FINAL_SHADOW_REPORT.json','V40L_TAIL_METHOD_FREEZE.json',
      'V40L_TAIL_ESTIMAND_CONTRACT.json','V40L_TAIL_CANDIDATE_REGISTRY.json','V40L_POST_SELECTION_TAIL_DIAGNOSTIC.json','V40L_T7_FAILURE_DECOMPOSITION.json']
    before={n:sha(OUT/n) for n in protected}
    assert read('V40L_FINAL_STATUS.json')['classification']=='V40L_TAIL_MODEL_INSUFFICIENT'
    assert read('V40L_TAIL_SELECTION_COMPARISON.json')['winner'] is None
    assert not read('V40L_FINAL_SHADOW_REPORT.json')['opened']
    with Firewall('strong_standby_support_provenance'):
        lookup_path=OUT/'models/SUPPORT.pkl';lookup=pickle.loads(lookup_path.read_bytes())
        source_sha=read('V40L_PRECALIBRATION_EXECUTION_FREEZE.json')['file_SHA']
        assert sha(lookup_path)==source_sha[lookup_path.relative_to(ROOT).as_posix()]
        assert sha(ROOT/'dayahead/v40l/data.py')==source_sha['dayahead/v40l/data.py']
        # Only frozen key/count/timestamp lookup metadata is read, never training outcomes.
        max_end=max(int(np.max(t)) for t in lookup.tables[0].values())
        assert max_end<lookup.freeze
        period_results={};hs_frames={};key_map={};data_sources={}
        for label,stage in STAGES:
            path=OUT/(stage+'_ROWS.parquet');cols=['job_id','submit_time']+F9
            f=pq.read_table(BytesIO(path.read_bytes()),columns=cols).to_pandas()
            x=base_features(f);kk=keys(x,F9)
            independent=[canonical(r) for r in f[F9].to_dict('records')]
            assert kk==independent,'KEY_CANONICALIZATION_INCONSISTENT'
            assert (f.submit_time.astype('datetime64[ns, UTC]').astype('int64')>=lookup.freeze).all()
            ex=np.array([len(lookup.tables[0].get(k,())) for k in kk],int);near=np.array([len(lookup.tables[1].get(k[1:],())) for k in kk],int)
            state=np.where(ex>=100,'STRONG_SUPPORT',np.where(ex>0,'SPARSE_SUPPORT',np.where(near>=100,'REGIME_MISMATCH','OUT_OF_SUPPORT')))
            hardware=f.partition.fillna('__MISSING__').astype(str).str.contains('h100',case=False)
            standby=f.qos.fillna('__MISSING__').astype(str).str.lower().eq('standby')
            assert np.array_equal(hardware.to_numpy(),x.hardware.eq('H100').to_numpy()) and np.array_equal(standby.to_numpy(),x.standby.eq(1).to_numpy())
            mask=hardware&standby
            z=x.loc[mask].copy();z['job_id']=f.loc[mask,'job_id'];z['submit_time']=f.loc[mask,'submit_time']
            z['exact_count']=ex[mask];z['near_count']=near[mask];z['support_class']=state[mask]
            hs_frames[label]=z;key_map[label]=[k for k,m in zip(kk,mask) if m]
            sc={s:int((z.support_class==s).sum()) for s in ['STRONG_SUPPORT','SPARSE_SUPPORT','REGIME_MISMATCH','OUT_OF_SUPPORT']}
            wall=[]
            for t,g in z.groupby('requested_seconds',sort=True):
                wall.append({'seconds':float(t),'hours':float(t/3600),'N':len(g),'fraction':len(g)/len(z),'support_class_counts':g.support_class.value_counts().to_dict(),
                  'exact_count':qstats(g.exact_count),'near_count':qstats(g.near_count)})
            period_results[label]={'total_H100_standby_N':len(z),'support_class_counts':sc,'strong_support_fraction':sc['STRONG_SUPPORT']/len(z),
              'exact_count':qstats(z.exact_count),'near_count':qstats(z.near_count),'requested_walltime_seconds':qstats(z.requested_seconds),
              'requested_walltime_distribution':wall,'partition_QoS_counts':[{'partition':p,'qos':q,'N':int(n)} for (p,q),n in z.groupby(['partition','qos']).size().items()],
              'actual_H100_standby_submit_range':[str(z.submit_time.min()),str(z.submit_time.max())],
              'actual_H100_standby_submit_dates':sorted(z.submit_time.dt.strftime('%Y-%m-%d').unique().tolist()),
              'hardware_definition_consistent':True,'standby_definition_consistent':True,'feature_key_consistent':True,'independent_key_construction_mismatches':0,
              'support_lookup_SHA':sha(lookup_path),'source_rows_SHA':sha(path),'projected_columns':cols,'raw_stored_dtypes':{c:str(f[c].dtype) for c in F9}}
            data_sources[label]={'path':path.relative_to(ROOT).as_posix(),'SHA':sha(path),'columns_read':cols,'runtime_status_outcome_columns_decoded':False}
        assert [period_results[k]['total_H100_standby_N'] for k,_ in STAGES]==[2291,383,1317]
        assert [period_results[k]['support_class_counts']['STRONG_SUPPORT'] for k,_ in STAGES]==[1772,130,4]
        last='Apr-15--23';z=hs_frames[last];profiles=collections.Counter()
        for k in key_map[last]:
            if len(lookup.tables[0].get(k,()))==0 and len(lookup.tables[1].get(k[1:],()))>=100:profiles[(k[0],k[1:])]+=1
        profile_reports=[]
        for (wall,knear),n in profiles.most_common():
            hist={str(k[0]):len(v) for k,v in lookup.tables[0].items() if k[1:]==knear}
            byperiod={}
            for label,_ in STAGES:
                byperiod[label]=dict(collections.Counter(str(k[0]) for k in key_map[label] if k[1:]==knear))
            assert str(wall) not in hist
            profile_reports.append({'near_feature8_profile_SHA':profile_id(knear),'selection_requested_seconds':wall,'selection_requested_hours':wall/3600,'selection_N':n,
              'exact_count':0,'near_count':len(lookup.tables[1][knear]),'historical_requested_seconds_counts':hist,'observed_period_requested_seconds_counts':byperiod})
        assert sum(p['selection_N'] for p in profile_reports)==1153
        strong=[]
        for row in z.loc[z.exact_count>=100].to_dict('records'):
            strong.append({k:(str(v) if k=='submit_time' else v) for k,v in row.items() if k in ['job_id','submit_time','requested_seconds','num_gpus_req','partition','qos','hardware','standby','exact_count','near_count']})
        # Compare distributions descriptively; no alternative support definition is used.
        tv={}
        for prior in ['Apr-01--07','Apr-08--14']:
            pa=hs_frames[prior].requested_seconds.value_counts(normalize=True);pb=z.requested_seconds.value_counts(normalize=True)
            union=pa.index.union(pb.index);tv[prior+' vs selection']=float(abs(pa.reindex(union,fill_value=0)-pb.reindex(union,fill_value=0)).sum()/2)
        classification='TEMPORAL_COVARIATE_SHIFT'
        explanations={
          'TEMPORAL_COVARIATE_SHIFT':'Primary explanation within the accepted cohorts: requested-walltime mix shifted to 12h; 1153 jobs belong to two already well-supported feature8 profiles whose historical requests were exclusively 48h.',
          'SUPPORT_DEFINITION_TOO_STRICT':'Exact feature9 matching, including exact requested walltime and identity/resource fields, mechanically makes new combinations non-strong. No alternative definition or threshold was evaluated; this diagnostic does not judge or change the frozen rule.',
          'POPULATION_SCARCITY':'Not the primary explanation for the whole H100-standby cohort: selection N=1317. The supported conditional subset is scarce because the key mix differs.',
          'IMPLEMENTATION_INCONSISTENCY':'No evidence found: identical frozen source/lookup, consistent hardware/QoS definitions, independently canonicalized keys and reproduced 1772/130/4 strong counts.',
          'MIXED':'Not selected; the observed collapse has a specific requested-walltime/profile explanation. Cohort extraction limitations remain a separate uncertainty.'}
        integrity={'status':'PASS','new_fits':0,'new_runtime_predictions':0,'new_model_predict_calls':0,'new_support_transform_calls':0,'retuning':0,'support_rule_changes':0,'threshold_changes':0,'conformal_retuning':0,
          'new_raw_partitions_opened':0,'runtime_status_outcome_columns_read':False,'selection_winner_shadow_unchanged':True,'before_after_SHA':before}
        assert all(sha(OUT/n)==h for n,h in before.items())
        result={'created_at':now(),'scope':'READ_ONLY_SUPPORT_PROVENANCE; no V40L selection change','provenance_classification':classification,
          'V40L_classification':'V40L_TAIL_MODEL_INSUFFICIENT','winner':None,'shadow':'SEALED','periods':period_results,'data_sources':data_sources,
          'support_authority':{'lookup_SHA':sha(lookup_path),'source_SHA':sha(ROOT/'dayahead/v40l/data.py'),'freeze_UTC':str(pd.Timestamp(lookup.freeze,tz='UTC')),
            'max_historical_known_end':str(pd.Timestamp(max_end,tz='UTC')),'historical_rows':sum(len(v) for v in lookup.tables[0].values()),
            'exact_key_fields':F9,'near_key_fields':F9[1:],'numeric_key_normalization':'float values; missing -> __MISSING__','categorical_key_normalization':'string values; missing -> __MISSING__',
            'hardware_definition':'partition contains h100, case-insensitive','standby_definition':'QoS.lower()==standby; partition substring alone is not the definition',
            'class_rules':{'STRONG_SUPPORT':'exact_count>=100','SPARSE_SUPPORT':'0<exact_count<100','REGIME_MISMATCH':'exact_count==0 and near_count>=100','OUT_OF_SUPPORT':'exact_count==0 and near_count<100'},
            'April_support_update':'None: frozen Apr01 lookup used unchanged for all three periods. No April job added to support.'},
          'why_selection_N4':{'total_H100_standby_N':1317,'strong':4,'sparse':35,'regime_mismatch':1153,'out_of_support':125,
            'requested_12h_N':int(z.requested_seconds.eq(43200).sum()),'requested_12h_fraction':float(z.requested_seconds.eq(43200).mean()),
            '48h_historical_to_12h_query_profiles':profile_reports,'four_strong_rows':strong,'walltime_total_variation_distance':tv},
          'classification_rationale':explanations,'cohort_limitation':'Results concern accepted pre-May/end-known whole-row-group-filtered cohorts. Their actual dates differ: April08 and April21-23 are absent. Do not infer the same distribution shift for excluded jobs or the full raw calendar population.',
          'integrity':integrity}
        write('V40L_STRONG_STANDBY_SUPPORT_PROVENANCE.json',result,immutable=True)
        lines=['# V40L strong-support H100-standby provenance','',f'원인 분류: **{classification}**. 기존 **V40L_TAIL_MODEL_INSUFFICIENT / winner NONE / shadow SEALED**를 유지한다.','',
          '세 기간의 저장된 causal columns와 동일한 Apr01 동결 support lookup을 조인했다. fit/predict/Support.transform/retuning을 실행하지 않았고 runtime/status/outcome columns를 읽지 않았다.','',
          '| Period | Total H100-standby | Strong | Sparse | Regime mismatch | Out of support | Exact P5 | P50 | P95 | Max |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        for label,r in period_results.items():
            sc=r['support_class_counts'];q=r['exact_count'];lines.append(f"| {label} | {r['total_H100_standby_N']:,} | {sc['STRONG_SUPPORT']:,} | {sc['SPARSE_SUPPORT']:,} | {sc['REGIME_MISMATCH']:,} | {sc['OUT_OF_SUPPORT']:,} | {q['P5']:,.0f} | {q['P50']:,.0f} | {q['P95']:,.0f} | {q['max']:,.0f} |")
        lines+=['','Strong 비중은 **77.346% → 33.943% → 0.304%**다. Selection 전체 H100-standby가 4개였던 것이 아니라, 1,317개 중 exact_count>=100인 집합이 4개였다.','',
          '| Requested walltime | Apr01–07 N | Apr08–14 N | Apr15–23 N |','|---|---:|---:|---:|']
        walls=sorted(set().union(*(set(g.requested_seconds) for g in hs_frames.values())))
        for t in walls:lines.append(f"| {t/3600:g}h | "+' | '.join(str(int(hs_frames[label].requested_seconds.eq(t).sum())) for label,_ in STAGES)+' |')
        lines+=['','핵심은 **과거 48h profile에 현재 12h 요청이 들어온 것**이다. Selection의 1,223/1,317개(92.863%)가 12h다. 그중 1,153개는 아래 두 profile이며, walltime 이외 8개 key는 과거에 충분히 존재한다.','',
          '| Near-key profile SHA prefix | Selection 12h N | Historical walltime | Historical count | Current exact count |','|---|---:|---|---:|---:|']
        for p in profile_reports:lines.append(f"| {p['near_feature8_profile_SHA'][:12]} | {p['selection_N']} | 48h only | {p['near_count']} | 0 |")
        lines+=['','동결된 exact key는 requested_seconds, nodes, cores, GPUs, memory, partition, QoS, user, account의 9개다. Near key는 이 중 requested_seconds만 제외한다. 따라서 이 1,153개는 STRONG이 아니라 사전등록한 REGIME_MISMATCH로 분류된다. 12h 특별 규칙이나 threshold 변경을 추가하지 않았다.','',
          '나머지는 sparse 35개, OOD 125개, strong 4개다. Strong 4개의 job identity, submit time, walltime, exact/near counts는 JSON에 기록했다.','',
          'Hardware는 partition에 h100 포함(대소문자 무시), standby는 QoS.lower()==standby다. 세 기간의 해당 집단은 모두 partition=gpu-h100-stdby / QoS=standby였다. 모든 key는 동일한 numeric float/string/missing-value 정규화를 사용했고 독립 canonical-key 구성의 불일치는 0개다. 동일 source/lookup SHA를 검증했다.','',
          'Support authority는 Apr01에 고정됐고 세 기간 사이에 April jobs를 추가하지 않았다. Strict exact matching이 이 변화를 support 부족으로 드러내지만, 이번 진단은 규칙이 너무 엄격한지에 대한 대체 실험을 수행하지 않았다. Implementation inconsistency나 전체 H100-standby population scarcity가 주원인이라는 근거는 없다.','',
          '분류는 관측된 허용 cohort에 한정한다. Whole-row-group/시각 firewall 때문에 calibration에는 Apr08이, selection에는 Apr21–23이 포함되지 않는다. 제외된 job이나 전체 raw calendar population까지 같은 shift로 일반화하지 않는다.','',
          'V40L support threshold/gate/classification은 변경하지 않았다. 추가 fit/prediction/retuning은 0회이며 shadow는 계속 SEALED다.']
        (OUT/'V40L_STRONG_STANDBY_SUPPORT_PROVENANCE.md').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
        print(json.dumps({'classification':classification,'counts':{k:v['support_class_counts'] for k,v in period_results.items()},'mismatch_profile_N':[p['selection_N'] for p in profile_reports],'integrity':'PASS'}),flush=True)
if __name__=='__main__':main()
