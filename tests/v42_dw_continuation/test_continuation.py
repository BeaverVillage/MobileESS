from v42_dw_continuation.common import *
from v42_dw_runtime.contracts import certification_settings,DiscoverySnapshot,RuntimeFlags
import numpy as np

def test_exact1433_authority_and_preserved_runtime():
 b=read(OUT/'DW_CONTINUATION_BASE_AUDIT.json');assert b['PASS'] and b['pool_columns']==1433
 assert b['floor']==read(ARC/'ARC_LP_CERTIFIED_RESULT.json')['L_arc_cert'] and b['threshold']==read(ARC/'DW_MATERIAL_THRESHOLD_AUTHORITY.json')['T_cert']
 assert sha(OUT/'DW_RUNTIME_FEATURE_SELECTION.json')==sha(SCI/'DW_RUNTIME_FEATURE_SELECTION.json')

def test_five_completed_round_trigger_boundaries():
 assert early_trigger([1],[.58,.5799,.5798,.5797,.5796],.57) is None
 assert early_trigger([1],[.58,.57999,.57998,.57997,.57996,.5797499],.57) is None
 assert early_trigger([1],[.58,.57999,.57998,.57997,.57996,.5797501],.57)=='FIVE_ROUND_IMPROVEMENT_BELOW_0_00025'
 assert early_trigger([0,0],[.58],.57)=='TWO_ZERO_ACCEPTED'
 assert early_trigger([1],[.5709999],.57)=='UPPER_WITHIN_0_001'

def test_new_grant_is_distinct_and_no_arbitrary_round_stop():
 p=read(OUT/'DW_CONTINUATION_PREREGISTRATION.json');assert p['new_authorized_optimize']==1800 and p['historical_optimize']==read(SCI/'DW_CHECKPOINT_LATEST.json')['elapsed_budget']
 assert p['fixed_round_limit'] is None and not p['automatic_second_grant'] and p['checkpoint_block_rounds']==8
 s=(ROOT/'v42_dw_continuation/cg.py').read_text(encoding='utf8');assert 'range(len(self.accepted),12)' not in s and "self.last_completed_dual()" in s

def test_certification_firewall_unchanged():
 snap=DiscoverySnapshot.create(1,[0],[2],[1]*4,[3]*4,.1,.6);cfg=certification_settings('FINAL_CERTIFICATION',snap,RuntimeFlags(True,True,True,False))
 assert not cfg['early_quota_terminate'] and not cfg['smoothed_certificate'] and cfg['global_BestBd_required']
 worker=(ROOT/'v42_dw_continuation/worker.py').read_text(encoding='utf8');assert "job['type']!='DISCOVERY' and model.Status in (2,9)" in worker

def test_wait_excludes_budget_and_other_lane_actions():
 p=read(OUT/'DW_CONTINUATION_PREREGISTRATION.json');assert p['wait_budget_consumption']==0 and p['B1_kill']==p['B1_edits']==p['B1_scheduler_edits']==0
 s=(ROOT/'v42_dw_continuation/admission.py').read_text(encoding='utf8');assert 'p.kill(' not in s and 'p.terminate(' not in s and 'time.sleep(2)' in s

def test_saved_pool_dual_and_smoothing_restored_exactly():
 cp=read(SCI/'DW_CHECKPOINT_LATEST.json');assert len(cp['pool'])==1433
 with np.load(SCI/cp['smooth_file']) as z:assert hashlib.sha256(z['pi'].tobytes()+z['alpha'].tobytes()).hexdigest()==cp['smooth_key']
 with np.load(SCI/cp['RMP']['point_file']) as z:assert hashlib.sha256(z['pi'].tobytes()+z['alpha'].tobytes()).hexdigest()==cp['RMP']['dual_SHA']
