"""Authority preservation, terminal firewall, exact thresholds, restart debit."""
from pathlib import Path
import hashlib,json
import pytest
from v42_dw_accelerated.common import OUT,SCI,ROOT,read,sha,decision,early_trigger,BUDGET
from v42_dw_accelerated.resources import severe_paging
from v42_dw_runtime.contracts import RuntimeFlags,certification_settings,DiscoverySnapshot

def test_exact_scientific_and_runtime_bindings():
 a=read(OUT/'DW_INTEGRATION_BASE_AUDIT.json');assert a['PASS'] and a['columns']==1244
 assert a['PR147']=='31858f4e35b44caadeee2a72ef2ae2d35b74899b' and a['PR144']=='42204661b8a92e0b1153ade0dc11830d54ec8df5'
 f=read(OUT/'DW_PR144_IMPORT_AUDIT.json');assert f['PASS'] and not f['PR145_imported'] and not f['PR146_imported']
 assert all(sha(ROOT/r['path'])==r['sha256'] for r in f['imports'])
 assert all(sha(ROOT/r['path'])==r['sha256'] for r in read(OUT/'PR147_BYTE_FREEZE.json')['files'])

def test_single_official_threshold_and_floor():
 t=read(SCI/'DW_MATERIAL_THRESHOLD_AUTHORITY.json');a=read(SCI/'ARC_LP_CERTIFIED_RESULT.json')
 assert t['T_cert']==a['native_optimum']+.005 and a['L_arc_cert']==read(OUT/'DW_INTEGRATION_BASE_AUDIT.json')['independent_arc']['L_dual_support']
 assert decision(a['L_arc_cert'],t['T_cert'],t)=='PROVEN_NONMATERIAL'
 assert decision(t['T_cert'],1,t)=='PROVEN_MATERIAL'
 assert decision(a['L_arc_cert'],t['T_cert']+1e-9,t)=='INCONCLUSIVE'

def test_certification_disables_all_discovery_shortcuts():
 snap=DiscoverySnapshot.create(1,[0.],[2.],[1.]*4,[3.]*4,.1,.6)
 cfg=certification_settings('FINAL_CERTIFICATION',snap,RuntimeFlags(True,True,True,True))
 assert not cfg['early_quota_terminate'] and not cfg['incremental_pool_audit'] and not cfg['smoothed_certificate']
 assert cfg['global_BestBd_required'] and cfg['dual_SHA']==snap.dual_SHA

def test_changed_stagnation_trigger_boundary():
 assert early_trigger([1,1,1],[.58,.5799,.5798,.5794999],.57) is None
 assert early_trigger([1,1,1],[.58,.5799,.5798,.5795001],.57)=='THREE_ROUND_IMPROVEMENT_BELOW_0_0005'
 assert early_trigger([0,0],[.58],.57)=='TWO_ZERO_ACCEPTED'
 assert early_trigger([1],[.5714999],.57)=='UPPER_WITHIN_0_0015'

def test_half_second_sampling_still_detects_ten_second_hard_paging():
 rows=[dict(perf=.5*i,hard_page_input_pages_per_sec=1100.,pagefile_used=i*15*1024**2) for i in range(22)]
 assert severe_paging(rows)
 rows[-1]['hard_page_input_pages_per_sec']=0.;assert not severe_paging(rows)

def test_budget_one_grant_and_firewall_source():
 prereg=read(OUT/'DW_ACCELERATED_CG_PREREGISTRATION.json');assert prereg['CG_native_union_budget_seconds']==BUDGET==1800 and not prereg['automatic_extension']
 source=(ROOT/'v42_dw_accelerated/integration.py').read_text();assert "flight['spent_before']+flight['reserved_optimize_seconds']" in source and 'ONE_RUN_ALREADY_FINISHED' in (ROOT/'v42_dw_accelerated/cg.py').read_text()
 worker=(ROOT/'v42_dw_accelerated/worker.py').read_text();assert "job['type']!='DISCOVERY' and model.Status in (2,9)" in worker
 assert "self.converged=bool(c['certified'] and all(p['native_status']==2" in (ROOT/'v42_dw_accelerated/cg.py').read_text()
