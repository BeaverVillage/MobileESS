from common16 import *
sys.path.insert(0,str(V13))
import common13

h=pd.read_parquet(LOCAL/'HISTORIC_KESTREL_PROXY.parquet');e=pd.read_parquet(LOCAL/'EMBEDDING_KESTREL_PROXY.parquet')
hids=set(h.loc[h.status.eq('RESEARCH_PROXY_CROSSWALK'),'id']);eids=set(e.loc[e.status.eq('RESEARCH_PROXY_CROSSWALK'),'id'])
rows=[]
for fold in range(1,6):
    v=common13.data(fold,'VALID')
    for level,accepted in [('HISTORIC_TO_KESTREL',hids),('BOTH_EMBEDDING_AND_KESTREL',eids)]:
        for hours in [0,4,8,12,24]:
            part=v if hours==0 else v.loc[v.runtime_seconds>hours*3600]
            n=int(part.job_id.isin(accepted).sum())
            rows.append(dict(fold=fold,mapping_level=level,threshold_hours=hours,N=len(part),matched=n,unmatched_or_ambiguous=len(part)-n,mapping_rate=n/len(part) if len(part) else None,
                population='Exact existing Runtime VALID roles; GPU population; no training or scoring'))
pd.DataFrame(rows).to_csv(ROOT/'RADDIT_Kestrel_FIVE_FOLD_MAPPING.csv',index=False)
# Correct the semantic label, independently of prediction metrics: these are partition_* IDs.
a=pd.read_csv(ROOT/'RADDIT_FULL_SCHEMA_AUDIT.csv');mask=a.field.eq('partition')
a.loc[mask,'representation']='STABLE_ANON_IDENTITY';a.loc[mask,'opaque_token_fraction']=1.
a.to_csv(ROOT/'RADDIT_FULL_SCHEMA_AUDIT.csv',index=False)
b=pd.read_csv(ROOT/'RADDIT_FIELD_AUTHORITY_AUDIT.csv');b.loc[b.source.eq('RADDiT historic')&b.field.eq('partition'),'meaning']='STABLE_ANON_IDENTITY'
b.to_csv(ROOT/'RADDIT_FIELD_AUTHORITY_AUDIT.csv',index=False)
write('CROSSWALK_NAMESPACE_CORRECTION.json',dict(time=now(),scope='Source semantics correction, unrelated to ML parameters or performance',
    partition_native='partition_0000001 style opaque IDs',partition_original='standard/short/gpu-h100 etc structured scheduler names',
    token_codebook_available=False,inferred_codebook_used=False,native_partition_interpreted_numerically=False,
    first_attempt=rec(ROOT/'CROSSWALK_INVALID_NAMESPACE_ATTEMPT.json'),corrected_result=rec(ROOT/'RADDIT_CROSSWALK_SUMMARY.json'),
    unchanged_numeric_time_keys=True,comparable_holdouts=['start_time','qos'],fivefold_distribution=rec(ROOT/'RADDIT_Kestrel_FIVE_FOLD_MAPPING.csv')))
print('FIVE_FOLD_MAPPING',pd.DataFrame(rows).query('threshold_hours==0').to_string(index=False),flush=True)
