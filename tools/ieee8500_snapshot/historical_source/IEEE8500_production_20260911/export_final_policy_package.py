"""Post-run export only; does not execute optimization or mutate any authority."""
from pathlib import Path
import json
import ac8500 as ac
H=ac.H
def main():
    receipt=ac.read(H/'FINAL_CAMPAIGN_RECEIPT.json');assert receipt['status']=='PASS'
    out=H/'final_policy_package';out.mkdir(exist_ok=False)
    authority=ac.record(ac.STRESS/'IEEE8500_STRESS_CALIBRATED_B0_AUTHORITY.json');binding=ac.record(ac.s.PCC/'PCC_OVERLAY_INVENTORY.json')
    inp=ac.read(H/'preflight/NON_ELECTRICAL_INPUT_AND_BINDING_AUDIT.json');reference=next(r for r in inp['input_files'] if r['path'].endswith('COMMON_B0_REFERENCE_JOBS.json'))
    policies={}
    for name,aidc,mess,final in [('B0',None,None,'B0'),('B1','B1',None,'B1'),('B2',None,'B2','B2'),('B3','B3_A1','B3_MF','B3_MF')]:
        item=dict(policy=name,operating_point_authority=authority,PCC_and_host_binding=binding,AIDC_decision=reference if aidc is None else ac.record(H/'policies'/aidc/'FINAL_AIDC.json'),MESS_decision='OFF' if mess is None else ac.record(H/'policies'/mess/'FINAL_MESS.json'),final_exact_AC=ac.record(H/'policies'/final/'FINAL_INDEPENDENT_AC/AC_SUMMARY.json'),all_phase_evidence=ac.record(H/'policies'/final/'FINAL_INDEPENDENT_AC/AC_PHASE_ARRAYS.npz'))
        if name=='B3':item.update(A0_exact_B1_reuse=ac.record(H/'policies/B3_A0_EXACT_B1_REUSE.json'),M1=ac.record(H/'policies/B3_M1/FINAL_MESS.json'),A1=ac.record(H/'policies/B3_A1/FINAL_AIDC.json'),MF=ac.record(H/'policies/B3_MF/FINAL_MESS.json'))
        ac.save(out/(name+'_FINAL_DAYAHEAD_SOLUTION.json'),item);policies[name]=item
    ac.save(out/'FINAL_DAYAHEAD_POLICIES.json',dict(status='PASS',date='2025-05-21',policies=policies,metrics=ac.record(H/'SCALABILITY_METRICS.json'),FINAL_operating_point_unchanged=True))
    clarified={}
    for stage in ['B1','B3_A1']:
        result=ac.read(H/'policies'/stage/'FINAL_AIDC.json');iterations=[ac.read(p) for p in (H/'policies'/stage/'iterations').glob('iteration_*.json')];proposals=sum(r['proposal'] is not None for r in iterations);duration=result['timeline']['continuous_loop_seconds'];m=result['metrics']
        clarified[stage]=dict(search_loop_seconds=duration,neighborhood_iterations=len(iterations),whole_day_neighborhood_proposals=proposals,whole_day_proposal_evaluations_per_search_second=proposals/duration,full_domain_option_scoring_operations=m['candidate_evaluations']-proposals,option_scoring_operations_per_search_second=(m['candidate_evaluations']-proposals)/duration,exact_AC_validation_trajectories=m['exact_AC_validation']['count'],slots_per_exact_AC_trajectory=96,LP_MILP_solve_count=m['neighborhood_LP_MILP']['count'])
    ac.save(out/'THROUGHPUT_METRIC_DEFINITIONS.json',dict(note='Option scoring throughput is distinct from complete schedule proposals and exact 96-slot AC validations. Repeated scoring of the same frozen option is counted as another scoring operation, not another unique option.',stages=clarified))
    observed=[]
    for name in ['PROCESS_MONITOR.jsonl','PROCESS_MONITOR.log']:
        p=H/name
        if p.exists():observed.extend(json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip())
    ac.save(out/'PROCESS_MEMORY_AUDIT.json',dict(scope='Production Python process including Gurobi/OpenDSS native libraries; Windows lifetime peak working set observed during campaign',OS_peak_working_set_bytes=max((r.get('OS_peak_working_set_bytes') or 0 for r in observed),default=0),sampled_RSS_peak_bytes=max((r.get('RSS_bytes',0) for r in observed),default=0),observations=len(observed),coefficient_generation_separate_process_peak_memory_not_measured=True))
    files=[ac.record(p) for p in sorted(H.rglob('*')) if p.is_file() and p.name not in ['COMPLETE_EVIDENCE_SHA256.json','COMPLETE_EVIDENCE_SHA256.sha256'] and not p.name.endswith('.tmp')]
    ac.save(H/'COMPLETE_EVIDENCE_SHA256.json',dict(status='FINAL_IMMUTABLE_COMPLETE_PACKAGE',files=files));(H/'COMPLETE_EVIDENCE_SHA256.sha256').write_text(ac.sha(H/'COMPLETE_EVIDENCE_SHA256.json')+'  COMPLETE_EVIDENCE_SHA256.json\n',encoding='ascii');print('FINAL_POLICY_PACKAGE_AND_ALL_LOG_HASHES_FROZEN')
if __name__=='__main__':main()
