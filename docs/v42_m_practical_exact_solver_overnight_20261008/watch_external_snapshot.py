"""Observe external node progress and complete OPEN coverage, without solves."""
import json,os
from pathlib import Path
from datetime import datetime,timezone
from fractions import Fraction
OUT=Path(__file__).resolve().parent;RUN=OUT/'external_production'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def run():
    state=read(RUN/'OPEN_CHECKPOINT.json')['state'];live=read(RUN/'EXTERNAL_LIVE.json') if (RUN/'EXTERNAL_LIVE.json').exists() else None
    open_nodes=[n for n in state['nodes'].values() if n['state']=='OPEN'];lb=min((Fraction(n['LB']) for n in open_nodes),default=Fraction(state['UB']))
    r=dict(UTC=datetime.now(timezone.utc).isoformat(),stage_finished=(RUN/'RESULT.json').exists(),root_receipt_exists=(RUN/'external_nodes/0000/RESULT.json').exists(),processed=state['processed'],generated=len(state['nodes']),OPEN=len(open_nodes),in_flight=state['in_flight'],global_OPEN_LB=float(lb),UB=float(Fraction(state['UB'])),LP_live=live)
    if r['root_receipt_exists']:r['root_receipt']=read(RUN/'external_nodes/0000/RESULT.json')
    tmp=OUT/'EXTERNAL_WATCH.json.tmp'
    with tmp.open('w',encoding='utf-8',newline='\n') as f:json.dump(r,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,OUT/'EXTERNAL_WATCH.json');print(json.dumps(r))
if __name__=='__main__':run()
