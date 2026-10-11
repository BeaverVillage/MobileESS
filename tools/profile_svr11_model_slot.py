"""Profile one independent Forecast sensitivity slot; no campaign mutation."""
from pathlib import Path
import sys,shutil,cProfile,pstats,time,json
import numpy as np
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import scope
from v42_svr11.model import generate,FIELDS

root=Path(sys.argv[1]).resolve();day=sys.argv[2];slot=int(sys.argv[3]);tag=sys.argv[4]
output=root/'model_benchmarks'/tag;assert not output.exists();output.mkdir(parents=True)
origin=root/'models'/day
(output/'FORECAST_ANCHOR').mkdir()
for name in ('B0_NEW_PLANNING_GENERATION.json','PLANNING_PHYSICAL.npz'):
    shutil.copyfile(origin/'FORECAST_ANCHOR'/name,output/'FORECAST_ANCHOR'/name)
receipts=[]
for path in sorted(origin.glob('SLOT_*.json')):
    receipts.append(record(path));v=read(path);assert record(v['data']['path'])==v['data']
    if int(path.stem.split('_')[1])!=slot:shutil.copyfile(path,output/path.name)
assert len(receipts)==96
profile=cProfile.Profile();start=time.perf_counter()
with scope(root/'CAMPAIGN_MANIFEST.json'):
    profile.enable()
    cert=generate(day,root/'inputs'/'B2'/day,output,lambda v:None)
    profile.disable()
wall=time.perf_counter()-start;profile.dump_stats(str(output/'PROFILE.pstats'))
with (output/'PROFILE.txt').open('w',encoding='utf8') as stream:
    pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(45)
with np.load(read(origin/f'SLOT_{slot:02d}.json')['data']['path']) as old,np.load(output/f'SLOT_{slot:02d}.npz') as new:
    equality={f:np.array_equal(old[f],new[f]) for f in FIELDS}
receipt=dict(PASS=all(equality.values()),day=day,slot=slot,wall_seconds=wall,
    fields_bitwise_equal=equality,origin_checkpoint_receipts=receipts,
    certificate=cert,profile=record(output/'PROFILE.pstats'),UTC=now(),
    Native_optimizer_calls=0,Actual_inputs_read=0,campaign_workers_modified=0)
atomic(output/'PROFILE_VALIDATION.json',receipt)
print(json.dumps({k:v for k,v in receipt.items() if k not in ('origin_checkpoint_receipts','certificate','profile')}))
print((output/'PROFILE.txt').read_text(encoding='utf8'))
