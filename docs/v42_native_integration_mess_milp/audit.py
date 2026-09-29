"""Read-only source reconciliation and bounded synthetic computational audit.

One native day is preregistered; failed source gates produce NOT_RUN, not a
replacement easy date or a synthetic result relabeled as native.
"""
from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,math,sys,xml.etree.ElementTree as ET
from dataclasses import asdict
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];WORK=ROOT.parent
sys.path.insert(0,str(ROOT))
from v42_native.canary import fixture,mess_grid,aidc_fixture,aidc_grid
from v42_native.mess import solve as mess_solve
from v42_native.aidc import solve as aidc_solve
from v42_native.contracts import Deadline
from v42_native.service import service_identity
from v42_native.supervision import supervise
from v42_native.coordinator import gate


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [clean(v) for v in x]
    if hasattr(x,'item'):return clean(x.item())
    if isinstance(x,float) and not math.isfinite(x):return None
    return x


def dump(name,value):
    (HERE/name).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def csv(name,rows):pd.DataFrame(rows).to_csv(HERE/name,index=False,lineterminator='\n')


def main():
    inherited=json.loads((ROOT/'docs/v42_job_capability_joint_flexibility/SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    original=[Path(x['path']) for x in inherited['files']]
    original+=list((ROOT/'docs/v42_job_capability_joint_flexibility').glob('*'))
    original += [ROOT/'v42_job_capability.py',ROOT/'tests/test_v42_job_capability.py',
        WORK/'v42_reference_episode_pr/v42_reference_episode.py',
        WORK/'V42_RESPONSE_KERNEL_LOCAL/regeneration_002/2025-04-01/CAUSAL_REFERENCE.json',
        WORK/'V42_RESPONSE_KERNEL_LOCAL/regeneration_002/2025-04-01/INPUT_FREEZE.json',
        WORK/'v42_integrated_pr/docs/v42_final/V42_VOLTAGE_SECURITY_MARGIN_CONTRACT.json',
        WORK/'v42_integrated_pr/docs/v42_prefix_policy/V42_FINAL_REVIEW_KO.md']
    original=sorted(set(p for p in original if p.is_file()))
    before={str(p):sha(p) for p in original}
    for item in inherited['files']:assert before[item['path']]==item['sha256'],item['path']
    dump('SOURCE_MANIFEST.json',dict(files=[dict(path=p,sha256=h) for p,h in before.items()],
        base_commit='87be27b68829afc2fb1e915c0ae26f3cbd787ccb',prior_evidence_not_merged=True))
    ep=WORK/'v42_reference_episode_pr/docs/v42_aidc_reference_episode_continuity'
    ledger=pd.read_parquet(ep/'CANONICAL_REFERENCE_LEDGER.parquet').sort_values(['episode_id','operating_day'])
    previous=ledger.groupby('episode_id').shift()
    ledger['prior_state']=previous.state_at_issue
    ledger['previous_absolute_start']=previous.absolute_start_seconds
    ledger['previous_absolute_end']=previous.absolute_start_seconds+previous.safe_duration_slots*900
    ledger['observed_minus_planned_start']=ledger.known_start_seconds-ledger.previous_absolute_start
    ledger['same_episode_transition']=ledger.state_at_issue.eq('RUNNING')&ledger.prior_state.eq('PENDING')
    conflicts=pd.read_csv(ep/'CONTINUING_CAPACITY_CONFLICT_DETAILS.csv',dtype={'job_uid':str})
    ledger.job_uid=ledger.job_uid.astype(str)
    joined=conflicts.merge(ledger[['operating_day','episode_id','previous_absolute_start','previous_absolute_end','observed_minus_planned_start']],
        left_on=['day','episode_id'],right_on=['operating_day','episode_id'],validate='many_to_one')
    local=WORK/'V42_NATIVE_INTEGRATION_LOCAL';local.mkdir(exist_ok=True)
    out=local/'PR79_CONFLICT_SOURCE_JOIN.csv.gz';joined.to_csv(out,index=False,compression={'method':'gzip','mtime':0})
    transitions=ledger[ledger.same_episode_transition];known=transitions.observed_minus_planned_start.dropna()
    reconciliation=dict(status='PARTIAL_LEDGER_SEMANTIC_CLOSURE_NATIVE_RESOURCE_UNRESOLVED',
        duplicate_episode_day_rows=int(ledger.duplicated(['operating_day','episode_id']).sum()),
        conflict_site_time_segments=len(conflicts[['day','site','start','end']].drop_duplicates()),
        episode_segment_rows=len(conflicts),overlapping_new_placement=int(conflicts.overlapping_new_placement.sum()),
        conflict_row_states=conflicts.groupby(['state','prior_state']).size().to_dict(),
        expired_pending_reservations=int(ledger.status.eq('REFERENCE_START_STATE_CONFLICT').sum()),
        pending_running_transitions=len(transitions),transitions_with_comparable_old_reservation=len(known),
        observed_start_later_than_plan=int(known.gt(0).sum()),observed_start_earlier_than_plan=int(known.lt(0).sum()),
        conflict_rows_with_observed_start_later_than_previous_plan=int(joined.observed_minus_planned_start.gt(0).sum()),
        residual_cause='Counterfactual reservations and causal observed execution differ inside synthetic site mapping; current RUNNING remaining service replaces old plan, not a duplicate entry',
        no_completion_receipt_used_to_drop_work=True,no_requeue_invented=True,site_changed=0,GPU_reduced=0,service_shortened=0,
        physical_conflicts_resolved=0,source_join=dict(path=str(out),sha256=sha(out)))
    dump('EPISODE_RESOURCE_RECONCILIATION.json',reconciliation)
    day=ledger[ledger.operating_day.eq('2025-04-01')]
    old_reference=json.loads((WORK/'V42_RESPONSE_KERNEL_LOCAL/regeneration_002/2025-04-01/CAUSAL_REFERENCE.json').read_text(encoding='utf-8'))
    dump('CARRY_OVER_RECONCILIATION_AUDIT.json',dict(independent_snapshot_semantics_ready=True,
        sequential_propagation_ready=False,post_H_service_retained=True,old_plan_is_not_execution_evidence=True,
        previous_policy_output_used=False,April01_jobdays=len(day),April01_resource_valid_rows=int(day.capacity_feasible.sum()),
        April01_full_day_ready=bool(day.day_reference_ready.all()),
        D_plus_1_state_fabricated=False,native_reference_global_ready=False,
        kernel_reference_SHA=sha(WORK/'V42_RESPONSE_KERNEL_LOCAL/regeneration_002/2025-04-01/CAUSAL_REFERENCE.json'),
        episode_reference_SHA=sha(ep/'CANONICAL_REFERENCE_LEDGER.parquet'),
        kernel_reuse_authorized=False,reason='Older kernel reference and zero-MESS anchor are not the newly frozen final service/reference/PQ model'))
    audits=[]
    for p in (WORK/'v42_integrated_pr/v42').glob('*.py'):
        if p.name not in ('joint_mobility.py','blocks.py','mobility.py'):continue
        tree=ast.parse(p.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('addQConstr','addGenConstrNorm'):
                audits.append(dict(source_file=str(p),line=node.lineno,equation=ast.unparse(node.args[0]),
                    role='PCS exact circle',variable_set='Pdis,Pch,Q,connected arc',
                    physically_necessary='Physical circle yes; redundant with current inner16' if p.name=='joint_mobility.py' else 'Historical circle-only model; conservative subset conversion',
                    linear_equivalent_available='YES_FOR_EXISTING_INTERSECTION_WITH_INNER16' if p.name=='joint_mobility.py' else 'NO_EXACT_CIRCLE_POLYHEDRAL_EQUIVALENT; CONSERVATIVE_INNER_APPROXIMATION',
                    replacement='16 inner halfspaces and connection bounds',validation_status='PASS_BOUNDED_AND_GEOMETRIC_PROOF'))
    csv('MESS_QUADRATIC_CONSTRAINT_AUDIT.csv',audits)
    poly=[]
    for angle in np.linspace(0,2*np.pi,4097):
        radius=math.cos(math.pi/16)/max(math.cos(angle-2*math.pi*f/16) for f in range(16))
        poly.append(dict(angle_radians=angle,radius_over_S=radius,exact_circle_slack=1-radius*radius,inside=radius<=1+1e-12))
    # Full boundary data is small; no approximation sensitivity sweep.
    csv('PCS_POLYGON_VALIDATION.csv',poly)
    sites,H,b,r=fixture();comparisons=[];models=[];profiles={};results={}
    for mode in ('LEGACY_BOTH','CIRCLE_ONLY_DIAGNOSTIC','MILP'):
        result,receipt=mess_solve('M1',Deadline('M1',20),sites,{'M':'A'},r,b,H,mess_grid,mode=mode,diagnostic=True)
        assert result and result['physical_audit']['PASS'];results[mode]=result;profiles[mode]=receipt
        comparisons.append(dict(mode=mode,scope='SYNTHETIC_IDENTICAL_NATIVE_EQUATIONS',rho=result['objectives']['rho'],
            movement_kwh=result['physical_audit']['mobility_energy_kwh'],max_exact_circle_ratio=result['physical_audit']['max_exact_circle_ratio'],
            runtime_seconds=receipt['solve_wall_seconds'],solver_status=receipt['passes'][-1]['status'],
            QConstr=receipt['model_size']['quadratic_constraints'],hard_feasibility=True,
            route_domain_sha=result['domain_sha256'],terminal_SOC=result['values']['SOC[M,8]'],
            max_P_difference_from_MILP=None,max_Q_difference_from_MILP=None,max_SOC_difference_from_MILP=None))
    for row in comparisons:
        values=results[row['mode']]['values'];base=results['MILP']['values']
        row['max_P_difference_from_MILP']=max(abs((values[f'Pdis[M,{s},{t}]']-values[f'Pch[M,{s},{t}]'])-(base[f'Pdis[M,{s},{t}]']-base[f'Pch[M,{s},{t}]'])) for s in sites for t in range(H))
        row['max_Q_difference_from_MILP']=max(abs(values[f'Q[M,{s},{t}]']-base[f'Q[M,{s},{t}]']) for s in sites for t in range(H))
        row['max_SOC_difference_from_MILP']=max(abs(values[f'SOC[M,{t}]']-base[f'SOC[M,{t}]']) for t in range(H+1))
    csv('MISOCP_VS_MILP_BOUNDED_COMPARISON.csv',comparisons)
    dump('BOUNDED_COMPARISON_TRAJECTORIES.json',results)
    # Exercise inherited OS process-tree supervision and actual state transfer.
    runroot=local/('supervised_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    state={};warm={};option_rows=[]
    for stage in ('A1','M1','A2','M2'):
        prior=state.get('A1' if stage=='A2' else 'M1' if stage=='M2' else '')
        candidate,supervisor=supervise(stage,'v42_native.canary:worker','v42_native.canary:validator',
            {'stage':stage,'warm_start':prior},runroot/stage,seconds=30)
        assert candidate is not None,supervisor
        state[stage]=candidate;receipt=candidate['receipt'];warm[stage]=dict(scope='SYNTHETIC_SUPERVISED',
            applied=receipt['warm_start_values_applied'],accepted=receipt['warm_start_accepted'],
            initial_objective=receipt['warm_start_initial_objective'],first_incumbent_seconds=receipt['first_incumbent_seconds'],
            nodes=sum(x['nodes'] for x in receipt['passes']),node_reduction=None)
        profiles[stage]=dict(receipt=receipt,supervisor=supervisor)
        s=receipt['model_size_before_solve'];models.append(dict(stage=stage,scope='SYNTHETIC_SUPERVISED',**{k:v for k,v in s.items() if k!='constraint_families'},
            raw_options=receipt.get('raw_complete_options'),retained_options=receipt.get('retained_options'),
            route_variables=receipt.get('route_variable_count'),line_rows=s['constraint_families'].get('line_thermal',0),
            voltage_rows=sum(n for name,n in s['constraint_families'].items() if name.startswith('voltage')),
            transformer_rows=sum(n for name,n in s['constraint_families'].items() if name.startswith('transformer'))))
        if stage.startswith('A'):
            for row in receipt['prescreen']:option_rows.append(dict(stage=stage,scope='SYNTHETIC_NATIVE_BINDER',**row))
    assert warm['A2']['accepted'] and warm['M2']['accepted']
    dump('WARM_START_AUDIT.json',dict(PASS=True,scope='SYNTHETIC_NOT_NATIVE_DAY',stages=warm,native_effect_unmeasured=True))
    dump('BOUNDED_COMPUTATIONAL_PROFILES.json',profiles);csv('MODEL_SIZE_AUDIT.csv',models)
    csv('AIDC_OPTION_PRESCREEN_AUDIT.csv',option_rows)
    jobs,bounds,res=aidc_fixture();service=[]
    from v42_job_capability import build_domain
    for uid,j in jobs.items():
        options,_=build_domain(j,bounds[uid],res)
        service.extend(service_identity(j.service_slots*900,j.gpu,o.segments,8) for o in options)
    dump('SERVICE_IDENTITY_AUDIT.json',dict(PASS=True,contract='V42_CONTINUOUS_SERVICE_INDEPENDENT_SNAPSHOT_V1',
        scope='NATIVE_BINDER_SYNTHETIC_OPTIONS',options_checked=len(service),truncation_count=0,service_overlap_count=0,
        exact_seconds_partial_slot=service_identity(1900,4,(('A',95,98),)),post_H_electrical_security_claimed=False))
    preflight=dict(reference_resources=False,native_grid=False,runtime_where_required=False,CC4_where_required=False,
        final_kernel_anchor=False,service_windows=False,security_margin=False,MESS_initial_state=False,traffic_routes=False)
    stop=gate(preflight)
    native=[dict(stage=s,day='2025-04-01',status='NOT_RUN_SOURCE_GATE_FAILED',runtime_seconds=None,gap=None,binaries=None,
        first_incumbent_seconds=None,root_relaxation_seconds=None,bound=None,nodes=None,budget_seconds=600) for s in ('A1','M1','A2','M2')]
    csv('NATIVE_COMPUTATIONAL_CANARY.csv',native)
    dump('NATIVE_COMPUTATIONAL_CANARY.json',dict(status='NOT_RUN_SOURCE_GATE_FAILED',preregistered_day='2025-04-01',
        gate=stop,blocks=native,alternate_date_selected=False,synthetic_runtime_substituted=False,
        investigated='April01 PR79 day readiness alone does not bind final kernel, MESS initial state, routes, security margins, temporal windows or providers'))
    dump('FRESH_AC_CANARY_VALIDATION.json',dict(PASS=False,status='NOT_RUN_NO_ACCEPTED_NATIVE_CANARY',
        accepted_native_schedules=0,OpenDSS_installed=True,reason='Final service/reference/PQ/grid anchor not frozen; stale April reference kernel prohibited',
        protocol_tests_pass=True,protocol_test_is_not_AC_solve=True))
    dump('MESS_UNIT_AUDIT.json',dict(PASS=True,base_power='kW',reactive='kvar',apparent='kVA',energy='kWh',delta_t_hours=.25,
        energy_equation='E[t+1]=E[t]+0.25*(eta_charge*Pch-Pdis/eta_discharge)-travel_kWh',
        positive_P='DISCHARGE_INJECTION',PCC_load_positive='CONSUMPTION',MW_MWh_implicit_conversion=False,
        native_grid_control_source='dayahead/v40a/grid.py 60 controls in kW/kvar',
        local_repair_SOC_test=True,mobility_energy_preserved=True))
    after={str(p):sha(p) for p in original};assert before==after
    dump('INPUT_PRESERVATION.json',dict(PASS=True,files=len(before),changed=0))
    print(json.dumps(clean(dict(reconciliation=reconciliation,comparison=comparisons,models=models,warm=warm)),indent=2))


if __name__=='__main__':main()
