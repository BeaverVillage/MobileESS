from common10 import *
from prepare10 import grids
import shutil
assert not (ROOT/'FOLD_MODELS').exists(),'Cannot revise after V10 training'
for n in ['TAIL_GRID_CANDIDATES.json','TAIL_EXTRAPOLATION_TRAIN_CONTRACT.json','PREREGISTRATION.json']:
    if not (ROOT/('INITIAL_'+n)).exists():shutil.copyfile(ROOT/n,ROOT/('INITIAL_'+n))
allgrids={};tails={}
for i in [1,2,3,4,5,'final']:allgrids[str(i)],tails[str(i)]=grids(fold_data(i,'TRAIN'))
for name,key,value in [('TAIL_GRID_CANDIDATES.json','by_fold',allgrids),('TAIL_EXTRAPOLATION_TRAIN_CONTRACT.json','by_fold',tails)]:
    v=read(ROOT/name);v[key]=value;v['time']=now();(ROOT/name).write_text(json.dumps(clean(v),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
reg=read(ROOT/'PREREGISTRATION.json');reg['time']=now();reg['files']=[record(r['path']) for r in reg['files']]
(ROOT/'PREREGISTRATION.json').write_text(json.dumps(reg,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
write('PREPARATION_IMPLEMENTATION_REPAIR.json',dict(time=now(),reason='TRAIN support audit found forced72h grid prefix violated minimum100 events per adaptive interval; stop at first unsupported interval and use preregistered positive-rate continuation',V10_training_started=False,VALID_evaluated=False,April_read=False,grids={k:{g:len(v[g])-1 for g in ['G0','G1','G2']} for k,v in allgrids.items()}))
print('TRAIN_ONLY_SUPPORT_REPAIR_COMPLETE')
