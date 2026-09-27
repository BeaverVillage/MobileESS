"""Copy frozen parameter meanings into convenient delivery metadata, never tune."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1];f=json.loads((ROOT/'FINAL_SELECTION_FREEZE.json').read_text())
objects={
    'ENSEMBLE_PARAMETERS.json':dict(weight_DeepAR=f['weight'],weight_LightGBM=1-f['weight'],quantiles=[.5,.9],seeds=[20260924,20260925,20260926],
        operator='convex mean of quantile predictions; NOT mixture-CDF quantiles',seed_reduction='arithmetic prediction mean',selection='DEVELOPMENT only',
        freeze_sha256=hashlib.sha256((ROOT/'FINAL_SELECTION_FREEZE.json').read_bytes()).hexdigest()),
    'HYBRID_PARAMETERS.json':dict(risk='P_B1(Y>unchanged TRAIN burst threshold)',threshold=f['gate'],normal_hours='exact B0',gated_hours='both B1 quantiles',selection='DEVELOPMENT only')}
for name,obj in objects.items():
    path=ROOT/name
    if path.exists():assert json.loads(path.read_text())==obj
    else:
        with path.open('x',encoding='utf-8') as stream:json.dump(obj,stream,indent=2)
print('FROZEN PARAMETER METADATA PASS')
