import json,gzip,pickle,sys,time
from pathlib import Path
from dataclasses import asdict
from fractions import Fraction
import numpy as np
sys.path.insert(0,r'D:\MobileESS_V42')
import gurobipy as gp
from v42_may_campaign_native90.a_routing import native_zero_scope
from v42_may_campaign_native90.common import read,atomic,sha,now
from v42_may_campaign_native90.maintenance_session import valid
from v42_a_stage_phase1.core import elastic_master
from v42_a_stage_phase1.backend import update_graph
from v42_a_stage_compact_rowgen.assembly import build
from v42_a_stage_compact_rowgen.lift import expanded_point
from v42_a_stage_early.candidate import expanded_graph
from v42_a_stage_early.progress import capture,inclusion_witness
from v42_a_stage_canary.phase import artificial_point
from v42_a_stage_domain_v2.active import option_from_json
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--root',required=True)
parser.add_argument('--session-token',required=True)
args=parser.parse_args()
root=Path(args.root).resolve();store=root/'hourly_maintenance';token=args.session_token
assert root==Path(r'D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01')
valid(store,token);out=root/'dates/B1/2025-05-19/output';started=time.perf_counter()
with gzip.open(out/'STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz','rb') as f:state=pickle.load(f)
G=state['grows'];raw=np.load(out/'STATIC/NATIVE/PHASE_I/S18/NATIVE_RAW.npz');x=raw['X'][:state['compact'].matrix.shape[1]]
ex=expanded_point(state,x);em=elastic_master(state['reference'],G);ep=artificial_point(em,ex);old=capture(state['reference'],state['reference_descriptor'],em,dict(X=ep))
selected=read(out/'PHASE_I/S18/PRICE/PRICING_RESULT.json')['selected_candidates'];data=state['data'];ledger=state['ledger'];candidates=[c for m in state['metas'].values() for c in m['candidates']]
for c in selected:
 c=dict(c);c['option']=option_from_json(c['option']);uid=data[7]['classes'][c['class_id']][0]
 graph=expanded_graph(data[5][uid],c['option'],data[1][uid],state['domains'][uid],uid in data[7]['preserve_singleton_mixed_flow'])
 data,ledger=update_graph(data,state['domains'],c['class_id'],graph);candidates.append(dict(c,option=asdict(c['option']),price=str(c['price'])))
with native_zero_scope(gp):
 new=build(state['reference'],G,state['n'],state['axes'],data,state['domains'],ledger,candidates)
nm=elastic_master(new['reference'],G)
changes=[dict(row=i,old=str(a),new=str(b)) for i,a,b in zip(em.artificial_rows,em.weights,nm.weights) if a!=b]
initial=elastic_master(state['compact'],G)
proof=dict(UTC=now(),Native_calls=0,P2_calls=0,day='2025-05-19',old_rows=state['reference'].matrix.shape[0],new_rows=new['reference'].matrix.shape[0],selected=len(selected),weights_changed=changes,signs_unchanged=em.artificial_signs==nm.artificial_signs,initial_reference_compact_weights_equal=em.weights==initial.weights,source_state_SHA=sha(out/'STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz'),elapsed_seconds=time.perf_counter()-started)
try:inclusion_witness(old,new['reference'],new['reference_descriptor'],nm,state['n'])
except ValueError as e:proof['original_error']=str(e)
frozen=elastic_master(new['reference'],G,weights_by_row=dict(zip(em.artificial_rows,em.weights)))
witness,mapped=inclusion_witness(old,new['reference'],new['reference_descriptor'],frozen,state['n']);proof['frozen_witness']=witness
atomic(store/(token+'_MAY19_WEIGHT_DIAGNOSIS.json'),proof)
with gzip.open(store/(token+'_MAY19_RECONSTRUCTION.pkl.gz'),'wb',compresslevel=1) as f:pickle.dump(dict(old=old,state=state,new=new,mapped=mapped),f,protocol=5)
print(json.dumps(proof))
