from common16 import *
h=pd.read_parquet(LOCAL/'HISTORIC_KESTREL_PROXY.parquet')
e=pd.read_parquet(LOCAL/'EMBEDDING_KESTREL_PROXY.parquet')
f=pd.read_csv(ROOT/'RADDIT_Kestrel_FIVE_FOLD_MAPPING.csv')
groups={}
for name,t in [('HISTORIC_UNIQUE',h),('EMBEDDING_BOTH_UNIQUE',e)]:
    a=t[t.status.eq('RESEARCH_PROXY_CROSSWALK')];g=pd.to_numeric(a.gpus_requested,errors='coerce')
    groups[name]=dict(N=len(a),known_positive_requested_GPUs=int(g.gt(0).sum()),known_zero_requested_GPUs=int(g.eq(0).sum()),missing_requested_GPUs=int(g.isna().sum()))
write('NATIVE_TARGET_POPULATION_AUDIT.json',dict(time=now(),groups=groups,existing_GPU_VALID_matches=f.loc[f.threshold_hours.eq(0),'matched'].tolist(),
    interpretation='Unique mapped native rows have no positive requested-GPU quantity and do not intersect any fixed Runtime GPU VALID cohort. Native performance cannot be transferred directly to V42 GPU Runtime safety.',
    missing_GPU_is_not_imputed_zero=True,node_hours_not_GPU_hours=True,
    README_context='Public RADDiT README describes CPU-exclusive power prediction and CPU-only quickstart; this does not certify every unmatched row as CPU-only.',
    source_readme=rec(RAD/'README.md'),mapping=rec(ROOT/'RADDIT_Kestrel_FIVE_FOLD_MAPPING.csv')))
print(groups,flush=True)
