import gzip,pickle,json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,r'D:\MobileESS_V42')
from v42_may_campaign_native90.common import read,atomic,now,sha
from v42_may_campaign_native90.maintenance_session import valid
from v42_a_stage_phase1.core import phase_objective,primal_replay
from v42_a_stage_early.progress import capture,inclusion_witness
from v42_a_stage_compact_rowgen.assembly import compact_inverse
from v42_may_phase_v4.phase import FrozenWeights
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--root',required=True)
parser.add_argument('--session-token',required=True)
args=parser.parse_args()
root=Path(args.root).resolve();store=root/'hourly_maintenance';token=args.session_token
assert root==Path(r'D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01')
valid(store,token)
with gzip.open(store/(token+'_MAY19_RECONSTRUCTION.pkl.gz'),'rb') as f: rec=pickle.load(f)
a,b=rec['state'],rec['new'];G=a['grows'];old=rec['old'];initial_before=a['reference'].fingerprint();new_before=b['reference'].fingerprint();compact_before=b['compact'].fingerprint();raw_before=old['raw_X'].copy()
frozen=FrozenWeights(a['compact'],G)
previous=capture(a['reference'],a['reference_descriptor'],frozen.elastic_master(a['reference'],G),dict(X=old['raw_X']))
new_master=frozen.elastic_master(b['reference'],G)
witness,mapped=inclusion_witness(previous,b['reference'],b['reference_descriptor'],new_master,a['n'])
inverse=compact_inverse(b,mapped[:b['reference'].matrix.shape[1]])
full=frozen.elastic_master(b['compact'],G);included=np.r_[inverse,mapped[b['reference'].matrix.shape[1]:]]
replay=primal_replay(full.snapshot,included)
proof=dict(PASS=bool(witness['PASS'] and replay['PASS'] and phase_objective(full,included)==previous['Phi']),UTC=now(),Native_calls=0,P2_calls=0,production_point_or_ledger_reused=False,offline_saved_point_used_only_for_diagnosis=True,phase_objective_before=str(previous['Phi']),phase_objective_after=str(phase_objective(full,included)),prior_inclusion=witness,compact_inverse_replay=replay,original_reference_unchanged=a['reference'].fingerprint()==initial_before,expanded_reference_unchanged=b['reference'].fingerprint()==new_before,expanded_compact_unchanged=b['compact'].fingerprint()==compact_before,raw_unchanged=bool(np.array_equal(raw_before,old['raw_X'])),class_membership_unchanged=a['data'][7]['classes']==b['data'][7]['classes'],complete_domains_unchanged={str(k):v.sha for k,v in a['domains'].items()}=={str(k):v.sha for k,v in b['domains'].items()},initial_snapshot_SHA=initial_before,expanded_snapshot_SHA=new_before,compact_snapshot_SHA=compact_before,activation_state='STAGED_ONLY',performance_claim=False)
assert proof['PASS'] and all(proof[k] for k in ['original_reference_unchanged','expanded_reference_unchanged','expanded_compact_unchanged','raw_unchanged','class_membership_unchanged','complete_domains_unchanged'])
folder=Path(r'D:\MobileESS_V42\docs\v42_may_phase_v4_20261009');folder.mkdir(exist_ok=True)
atomic(folder/'VALIDATION.json',proof);atomic(store/(token+'_PHASE_V4_VALIDATION.json'),proof)
print(json.dumps(proof))
