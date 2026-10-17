"""Read-only original-parent replay and real archived exact-price columns; Native0."""
from pathlib import Path
import sys,pickle,gzip,time,inspect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r024a
from v44.common import read,record,atomic,now,verify
from v42_may_campaign_native90.preflight import native_zero
from v44_recovery_r024a.parent_admission import validate as parent_validate
from v44_recovery_r024a.adaptive_pricing import AdaptivePricing,choose
from v44_recovery_r024a.phase_rebuild import Rebuild
from v44_recovery_r023.phase_rebuild import Rebuild as Prior
from v42_a_stage_phase1.runner import load_cache
from v42_a_stage_early.candidate import validate
from v42_a_stage_domain_v2.active import option_from_json
from fractions import Fraction

out=Path('D:/MobileESS_V44/development/r024a/real_validation');out.mkdir(parents=True,exist_ok=False)
C=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004');root=C/'2025-05-02/B3/attempt005/A2/OUTPUT'
assert inspect.getsource(Rebuild).replace('R024A','R023').replace('r024a','r023')==inspect.getsource(Prior)
with native_zero() as denied:
 parent=parent_validate(C/'2025-05-02/B3/attempt001',out/'parent',read(C/'2025-05-02/B3/attempt001/A2/request.json'))
 print('PARENT_PASS',parent['M1_plan_sha'],flush=True)
 with gzip.open(root/'STATIC/INITIAL_STATE.pkl.gz','rb') as f:state=pickle.load(f)
 f=root/'PHASE_I/S11';attribution=read(f/'ATTRIBUTION/RESIDUAL_ATTRIBUTION.json');a=AdaptivePricing(out)
 plans=[a.plan_classes(attribution) for _ in range(5)]
 assert plans[-1]['complete_eligible_class_exploration']
 print('COVERAGE',len(plans[0]['target_class_ids']),len(plans[-1]['target_class_ids']),flush=True)
 candidates=[];details={}
 for p in (f/'PRICE/B').glob('*/CONCRETE_RECOVERY.json'):
  d=read(p);details[d['class_id']]=d;candidates+=d['candidates']
 chosen,selection=choose(candidates,tuple(state['axes']))
 roster={r['class_id']:r for r in read(root/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
 caches={};checked=0
 for c in chosen:
  key=c['class_id'];receipt=details[key]
  if key not in caches:caches[key]=load_cache(roster[key])
  cache=caches[key];uid=state['data'][7]['classes'][key][0];N=len(state['data'][7]['classes'][key])
  got=validate(cache,state['data'][1][uid],state['data'][2][uid],state['data'][3],state['domains'][uid],state['data'][4][uid],state['data'][0],
      {k:i for i,k in enumerate(state['axes'])},receipt['global_coupling_pi'],N,Fraction(receipt['active_local_lower_bound']),option_from_json(c['option']),key)
  assert got['price']==Fraction(c['price']) and got['coefficient_sha256']==c['coefficient_sha256']
  checked+=1
 assert not denied and checked==len(chosen)>0
 print('REAL_EXACT_CANDIDATES_PASS',checked,flush=True)
 verify(read(C/'AUTONOMOUS_RECOVERY/R024A_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
 atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,Native_calls=0,parent_compatibility=record(out/'parent/R024A_PARENT_COMPATIBILITY.json'),
  real_archived_dual_round='r022/S11',candidate_count=len(candidates),selected=len(chosen),independent_original_membership_primal_coupling_RC_rechecks=checked,
  class_exploration_plans=plans,selection=selection,r023_rebuild_source_equal_after_label_normalization=True,
  production_A2_convergence_or_speedup_not_yet_claimed=True,previous_PASS_and_M1_bytes_preserved=True))
