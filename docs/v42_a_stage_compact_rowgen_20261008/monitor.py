"""Small read-only progress snapshot; no native calls or domain authority."""
import json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from v42_a_stage_compact_rowgen.resources import sample
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def run():
    d=dict(UTC=datetime.now(timezone.utc).strftime('%H:%M:%S'),remaining_min=round((read(OUT/'OVERNIGHT_START.json')['deadline_unix']-time.time())/60,1))
    m=sample();d.update(RAM_GiB=round(m['available_RAM_bytes']/2**30,2),commit_GiB=round(m['available_commit_bytes']/2**30,2),unsafe=m['unsafe'])
    p=OUT/'DIRECT_CHECKPOINT.json'
    if p.exists():
        c=read(p);d.update(certified_stages=[s['component'] for s in c['stages']],validated_LB=c['valid_global_LB'],validated_UB=None if c['incumbent'] is None else c['incumbent']['value'])
    logs=list((OUT/'M19/P2/DIRECT').rglob('NATIVE_SOLVER.log'))
    if logs:
        p=max(logs,key=lambda p:p.stat().st_mtime);lines=p.read_text(encoding='utf8').splitlines();d['query']=p.parent.relative_to(OUT).as_posix()
        rows=[l.strip() for l in lines if re.match(r'^\s*\d+\s+\d+\s',l)]
        d['native_progress']=rows[-1] if rows else next((l.strip() for l in reversed(lines) if l.strip()),'')
        memory=p.parent/'SYSTEM_MEMORY.json'
        if memory.exists():d['callback_age_seconds']=round(time.time()-read(memory)['samples'][-1]['unix'],1)
    p=OUT/'DIRECT_RESULT.json'
    if p.exists():
        r=read(p);d.update(ended=True,A1_accepted=r['A1_accepted'],stop_reason=r.get('stop_reason'))
    print(json.dumps(d,separators=(',',':')))
if __name__=='__main__':run()
