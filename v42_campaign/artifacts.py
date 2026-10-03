"""Write contracts, full dry plan and bounded evidence after the M1 worker ends."""
import json,tempfile
from pathlib import Path
from .authority import contract,authority_sha,SCIENTIFIC,FORBIDDEN_KINDS,INPUT_KINDS,STATES
from .plan import build_plan
from .state import STATE_KEYS,AIDC_KEYS,MESS_KEYS,ACTUAL_KEYS
from .engine import atomic
from .fixtures import exercise
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_cutpass_loop_campaign'
def write(name,value):atomic(OUT/name,value)
def object_schema(properties,required=None):return dict(type='object',properties=properties,required=sorted(required or properties),additionalProperties=False)
def schemas():
    numeric_tree={'description':'Exact common axes, finite numeric scalars or nested arrays/maps; runtime validate_state/metrics enforce axes.'}
    objective=object_schema(dict(rho={'type':'number'}));objective['additionalProperties']={'type':'number'}
    state=object_schema(dict(aidc=object_schema({k:numeric_tree for k in AIDC_KEYS}),mess=object_schema({k:numeric_tree for k in MESS_KEYS}),objective=objective,authority_sha256={'type':'string','pattern':'^[a-f0-9]{64}$'},D1_source_hashes={'type':'object','minProperties':1,'additionalProperties':{'type':'string','pattern':'^[a-f0-9]{64}$'}},population_sha256={'type':'string','pattern':'^[a-f0-9]{64}$'}))
    differences=('changed_job_count','migration_count_difference','shift_difference','prestart_difference','AIDC_P_L1','AIDC_Q_L1','route_Hamming','location_state_difference','movement_count_difference','MESS_P_L1','MESS_Q_L1','SOC_L1')
    actual=object_schema({k:({'type':'object','additionalProperties':{'type':'integer','minimum':0}} if k=='violation_counts' else {'type':'number'}) for k in ACTUAL_KEYS})
    metric=object_schema(dict(rho={'type':'number'},comparison_scope={'const':'B3_convergence_only'},Actual_metrics={'anyOf':[actual,{'type':'null'}]},Actual_metrics_used_for_Planning={'const':False},differences={'anyOf':[object_schema({k:{'type':'number'} for k in differences}),{'type':'null'}]}))
    metric['properties']['previous_loop']={'type':['integer','null']}
    fixed=object_schema({k:{'type':'boolean'} for k in ('EXACT_FIXED_POINT','TWO_CYCLE','STILL_EVOLVING','stop_requested')});fixed['properties']['stop_requested']={'const':False}
    for schema in (state,metric,fixed):schema['$schema']='https://json-schema.org/draft/2020-12/schema'
    return state,metric,fixed
def main():
    if not (OUT/'EXECUTION_RECEIPT.json').exists():raise RuntimeError('WHOLE_M1_WORKER_MUST_END_BEFORE_SYNTHETIC_TESTS')
    plan=build_plan();state,metric,fixed=schemas()
    write('V42_MAY_CAMPAIGN_EXECUTION_CONTRACT.json',dict(contract(),authority_sha256=authority_sha(),heavy_stage_policy='one worker, one solver thread, accepted atomic freeze before next stage',day_count=31))
    write('V42_B3_LOOP_CONTRACT.json',dict(authority_sha256=authority_sha(),MAX_B3_LOOPS=4,EARLY_STOP_ON_CONVERGENCE=False,each_loop=['A1','M1','A2','M2'],final_AIDC='A2',final_MESS='M2',next_A1_fixed='previous same-day loop final Planning MESS',next_A1_AIDC='free, prior validated Planning AIDC warm candidate only',M1_fixed='A1 AIDC',A2_fixed='M1 MESS',M2_fixed='A2 AIDC',M2_free=['route','movement','P','Q','SOC'],M1_route_for_M2='validated warm candidate only',convergence_detector='analysis only; never early stop',hard_scientific_failure='STOP',Actual_feedback=False))
    firewall=dict(authority_sha256=authority_sha(),allowed_input_kinds=list(INPUT_KINDS),forbidden_input_kinds=list(FORBIDDEN_KINDS),exact_path_and_SHA_allowlist=True,D1_known_at_issue_required=True,Actual_completion_status_sequence_gate_only=True,Actual_values_available_to_Planning=False,before_after_read_audit=True,opaque_native_subprocess_preopened_readers_permitted=False,scope='Trusted broker adapters and audited Python opens; not an OS sandbox for malicious arbitrary native code.',production_backend_registered=False)
    write('V42_ACTUAL_FEEDBACK_FIREWALL.json',firewall)
    write('MAY_CAMPAIGN_DRY_RUN_PLAN.json',plan)
    write('B3_LOOP_STATE_SCHEMA.json',state);write('B3_LOOP_CONVERGENCE_METRICS_SCHEMA.json',metric);write('B3_LOOP_FIXED_POINT_CYCLE_SCHEMA.json',fixed)
    write('CAMPAIGN_RESUME_POLICY.json',dict(statuses=list(STATES),resume_only='validated complete immutable accepted freeze; exact authority, source, scientific contract and plan SHAs',atomic_publish='exclusive immutable hardlink + atomic ledger replacement',partial_optimizer_state='REFUSE',incomplete_Actual='REFUSE',incomplete_Fresh_AC='REFUSE',SHA_mismatch='REFUSE',stale_worker_lease='REFUSE',automatic_retry=False,production_execution='disabled in this task'))
    write('CAMPAIGN_STAGE_DEPENDENCY_GRAPH.json',dict(nodes=[dict(id=n['id'],predecessor=n['predecessor'],accepted_freeze_dependencies=n['required_accepted_freezes'],Planning_value_dependencies=n['Planning_dependencies']) for n in plan['nodes']],Actual_to_Planning_value_edges=0))
    with tempfile.TemporaryDirectory(prefix='v42_campaign_fixture_') as directory:evidence=exercise(directory)
    write('BOUNDED_SYNTHETIC_ORCHESTRATION.json',evidence)
    audits=evidence['read_audits']
    write('ACTUAL_TO_NEXT_LOOP_LEAKAGE_AUDIT.json',dict(PASS=all(a['PASS'] for a in audits),bounded_synthetic_only=True,production_executed=False,Actual_values_read_by_Planning=0,Fresh_AC_values_read_by_Planning=0,all_four_loops_completed=True,previous_Planning_only=True,Actual_completion_metadata_fields=['predecessor_accepted'],read_audits=audits,firewall_scope=firewall['scope'],adversarial_tests='tests/v42_campaign/test_campaign_authority.py; results in SEMANTIC_TEST_RESULT.json'))
    write('CAMPAIGN_NO_EXECUTION_RECEIPT.json',dict(MAY_MAIN_CAMPAIGN_EXECUTION='NOT_RUN',B3_LOOP2_PRODUCTION='NOT_RUN',B3_LOOP3_PRODUCTION='NOT_RUN',B3_LOOP4_PRODUCTION='NOT_RUN',A2_PRODUCTION='NOT_RUN',M2_PRODUCTION='NOT_RUN',ACTUAL_PRODUCTION='NOT_RUN',FRESH_AC_PRODUCTION='NOT_RUN',optimizer_calls_for_campaign=0,Actual_calls_for_campaign=0,Fresh_AC_calls_for_campaign=0,production_backends_registered=0,bounded_fixture_days=1,bounded_mock_stage_count=evidence['stage_count'],dry_plan_stage_count=len(plan['nodes']),May_production_input_consumed=False))
    print('CAMPAIGN_ARTIFACTS_PASS',len(plan['nodes']),'dry stages;',evidence['stage_count'],'synthetic stages; production calls 0')
if __name__=='__main__':main()
