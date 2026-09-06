"""Full exposed GPU normalization equivalence, including per-CPU memory nulls."""
import numpy as np
from .common import *
from .data import frame,normalize,memory

def main():
    from hpc_oda_commons.ingest.jobs_parquet.apply import _memory_slurm_to_mb
    rawpath=CACHE.with_name('kestrel_preissue_raw.parquet')
    with Firewall('full_mapping_equivalence',files=[CACHE,rawpath]):
        raw=frame(rawpath);raw=raw.loc[raw.gpus_requested.gt(0)]
        values=raw.memory_req.dropna().unique().tolist()+['4Gc','.5G','90000Mn','UNLIMITED']
        for value in values:
            a,b=memory(value),_memory_slurm_to_mb(value)
            assert (np.isnan(a) and b is None) or a==b,('MEMORY_MISMATCH',value,a,b)
        new=normalize(raw)
        # The pinned descriptor filters require_nonnull(runtime_seconds) after mapping.
        missing_runtime=int(new.runtime_seconds.isna().sum())
        new=new.loc[new.runtime_seconds.notna()]
        old=frame(CACHE);pair=new.merge(old,on='job_id',suffixes=('_new','_old'),validate='one_to_one')
        assert len(pair)==len(new),'NORMALIZATION_ROW_LOSS'
        checks={}
        for c in FEATURES9+['runtime_seconds','submit_time','start_time','end_time','job_state']:
            p,q=pair[c+'_new'],pair[c+'_old']
            ok=np.allclose(p.astype(float),q.astype(float),rtol=0,atol=0,equal_nan=True) if c in FEATURES9[:5]+['runtime_seconds'] else ((p==q)|(p.isna()&q.isna())).all()
            checks[c]=bool(ok)
        assert all(checks.values()),checks
        write('V40K_FEATURE_TARGET_EQUIVALENCE.json',{'status':'PASS','paired_rows':len(pair),'exact_checks':checks,
          'distinct_memory_strings_verified_against_pinned_parser':len(values),'entire_exposed_GPU_population':True,
          'canonical_descriptor_null_runtime_exclusions':missing_runtime,
          'source_SHA':sha(ROOT/'dayahead/v40k/data.py'),'raw_input_SHA':sha(rawpath),'normalized_input_SHA':sha(CACHE)})
        print('FULL_GPU_FEATURE_TARGET_EQUIVALENCE_PASS',len(pair),flush=True)
if __name__=='__main__':main()
