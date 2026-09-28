from core import *
import sys
REQUIRED='TARGET_DEFINITIONS.md TARGET_POPULATION_AUDIT.json TARGET_BOUNDARY_AUDIT.csv TARGET_DISTRIBUTION.csv TARGET_OPERATIONAL_ALIGNMENT.csv FEATURE_CONTRACT.json FEATURE_CAUSAL_AVAILABILITY.parquet FEATURE_GROUPS.json FEATURE_LEAKAGE_AUDIT.json ARM_REGISTRATION.json ARM_METRICS.csv HOUR_SLOT_METRICS.csv LEAD_GROUP_METRICS.csv STRATIFIED_METRICS.csv PARETO_FRONT.csv PAIRED_UNCERTAINTY.csv PREDICTIONS.parquet TARGET_SELECTION_FREEZE.json FEATURE_SELECTION_FREEZE.json STAGE2_MODEL_PROTOCOL.json STAGE2_MODEL_METRICS.csv STAGE2_SELECTION_FREEZE.json FINAL_REVIEW_KO.md FINAL_VERDICT.json SOURCE_MANIFEST.json'.split()
def seal():
    assert read(ROOT/'VALIDATION.json')['PASS']
    assert all((ROOT/p).exists() for p in REQUIRED)
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json':files.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size))
    write('DELIVERY_MANIFEST.json',dict(time=pd.Timestamp.now(tz='UTC'),files=files,required_complete=True,base_commit='bae7916c759e1c845bb87a8ee0dff761b5db7f7a',scope='new docs/cc4_v27_target_feature_sharpness only',not_included='__pycache__; manifest cannot hash itself'))
def verify():
    f=read(ROOT/'DELIVERY_MANIFEST.json');bad=[r['path'] for r in f['files'] if not (ROOT/r['path']).exists() or sha(ROOT/r['path'])!=r['sha256']]
    assert not bad,bad;print('DELIVERY_VERIFIED',len(f['files']))
if __name__=='__main__':seal() if sys.argv[1]=='seal' else verify()
