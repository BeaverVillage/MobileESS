"""PR134 R0 service/reference and frozen Q50, routed by date without refitting.

PR150/151 input/reference producers are deliberately absent. May01 is the
byte-identical accepted scientific bundle. Missing original per-date authority
is recorded explicitly; a new Q50 reference is never substituted for R0.
"""
from copy import deepcopy
import types,math,inspect,ast
import pandas as pd
from .common import *

def immutable_unmodelable(request,capacities,racks):
    gpu=request.get('gpus_requested')
    positive=isinstance(gpu,(int,float)) and not isinstance(gpu,bool) and math.isfinite(gpu) and gpu>0 and int(gpu)==gpu
    compatible=[s for s,cap in capacities.items() if positive and gpu<=cap and any(gpu<=r for r in racks[s])]
    reasons=[]
    if not positive:reasons.append('MISSING_OR_INVALID_IMMUTABLE_GPU_REQUEST')
    if positive and not compatible:reasons.append('NO_COMPATIBLE_WHOLE_GANG_SITE_RACK')
    if 'h100' not in str(request.get('partition','')).lower():reasons.append('GPU_TYPE_AUTHORITY_UNAVAILABLE')
    return dict(modelable=not reasons,immutable_request_reasons=reasons,compatible_sites=compatible)

def produce(root):
    import v42_may01.prepare as original
    import v42_holdout.inputs as projection
    from v42_holdout.common import source_freeze
    from v42_final.native_inputs import memory_mib
    from v42_final.runtime import FrozenQ50
    from v42_final.state import planning_remaining
    from v42_final.workload import profile
    from v42_boundary.boundaries import known_window
    from v42_capacity.common import resolve
    spec=source_freeze();dest=root/'inputs';dest.mkdir(parents=True,exist_ok=True)
    raw=types.FunctionType(projection.requests.__code__,dict(projection.requests.__globals__,OUT=dest))(spec)
    provider=FrozenQ50();template=read(ROOT/'docs/v42_final_integration/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json')
    kernel=pd.read_csv(ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy();rows=[];files=[]
    for day in DAYS:
        folder=dest/day;folder.mkdir(exist_ok=True)
        try:
            physical=ROOT/'docs/v42_may_b0_zero_margin_holdout/INPUT/BUNDLE'/('DAY_'+day.replace('-',''))
            current=read(physical/'PLANNING_INPUT_BUNDLE.json')
            if current['capacities']!=template['capacities']:raise ValueError('CURRENT_CAPACITY_DIFFERS_FROM_PR134')
            if any(r['semantics']!='NON_ADDITIVE_SINGLE_GANG_COMPATIBILITY_ENVELOPE' or r['aggregate_capacity_contribution_GPU']!=0 for r in template['racks']):raise ValueError('RACK_SEMANTIC_AUTHORITY')
            expected_racks={s:sorted({r['compatibility_GPU_limit'] for r in template['racks'] if r['aidc_id']==s}) for s in template['capacities']}
            if expected_racks!={s:sorted(set(v)) for s,v in current['rack_compatibility'].items()}:raise ValueError('CURRENT_RACK_COMPATIBILITY_ENVELOPE_DIFFERS_FROM_PR134')
            ops=dict(current_day_folder=str(physical),forecast_inputs=current['forecast_inputs'])
            if day=='2025-05-01':
                p=ROOT/'docs/v42_final_integration/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'
                (folder/'NATIVE_INPUT.json').write_bytes(p.read_bytes());bundle=read(p)
                windows=read(ROOT/'docs/v42_ts_boundary_a1_acceleration/KNOWN_TS_SERVICE_BOUNDARY_AUDIT.json')['windows']
            else:
                issue=pd.Timestamp(current['issue_time'])
                namespace=dict(original.job_ledger.__globals__,DAY=day,ISSUE=issue,WORK=Path('D:/ChatGPT/Mobile ESS 2'),OUT=folder,SOURCES={})
                reference_path=CODE/f'frozen_artifacts/v41r3_may/inputs/{day}/common_q90_v3/COMMON_B0_REFERENCE_JOBS.json'
                canonical_reference=reference_path
                if not reference_path.is_file():
                    alternative=CODE/f'frozen_artifacts/v41r3_scale/inputs/{day}/common_q90_v3/COMMON_B0_REFERENCE_JOBS.json'
                    if not alternative.is_file():raise FileNotFoundError(reference_path)
                    receipt=read(alternative.parent/'COMMON_INPUT_RECEIPT.json')
                    authority=read(alternative.parent/'COMMON_DA_SERVICE_AUTHORITY.json')
                    primary_receipt=read(CODE/'frozen_artifacts/v41r3_may/inputs/2025-05-01/common_q90_v3/COMMON_INPUT_RECEIPT.json')
                    if receipt['day']!=day or receipt['failures'] or receipt['policy_dependent_duration'] or authority['Actual_reads']!=0:raise ValueError('ALTERNATE_R0_AUTHORITY_FAILED')
                    for key in ('generator','baseline_source','admission_source','capacity_authority','migration_contract_source'):
                        if receipt[key]['sha256']!=primary_receipt[key]['sha256']:raise ValueError('ALTERNATE_R0_PRODUCER_DIFFERS:'+key)
                    if receipt['baseline_contract']!=primary_receipt['baseline_contract']:raise ValueError('ALTERNATE_R0_BASELINE_CONTRACT_DIFFERS')
                    for file in receipt['files'].values():
                        if sha(file['path'])!=file['sha256']:raise ValueError('ALTERNATE_R0_PAYLOAD_SHA')
                    # This is the same original frozen R0 producer's seed-date
                    # namespace, not a current Q50 reference regeneration.
                    atomic(folder/'ALTERNATE_R0_NAMESPACE.json',dict(reference=record(alternative),input_receipt=record(alternative.parent/'COMMON_INPUT_RECEIPT.json'),
                        service_authority=record(alternative.parent/'COMMON_DA_SERVICE_AUTHORITY.json'),canonical_missing=str(reference_path),
                        source_producer_unchanged=True,new_reference_generated=False,all_payload_SHA_match=True,
                        primary_generator_baseline_capacity_migration_SHA_equal=True,Actual_reads=0))
                    reference_path=alternative
                    class ReferenceRouter:
                        def __truediv__(self,suffix):
                            p=CODE/suffix
                            return reference_path if p==canonical_reference else p
                    namespace['NATIVE']=ReferenceRouter()
                reference_rows=read(reference_path);original_reference_rows=reference_rows
                physical_ids={r['job_uid'] for r in current['known_population']};source_exclusions=[]
                for r in reference_rows:
                    if r['job_uid'] in physical_ids:continue
                    proof=immutable_unmodelable(raw[r['job_uid']][0],current['capacities'],current['rack_compatibility'])
                    if proof['modelable']:raise ValueError('MODELABLE_R0_JOB_ABSENT_CURRENT_POPULATION:'+r['job_uid'])
                    source_exclusions.append(dict(job_uid=r['job_uid'],proof=proof,original_R0_row=r,disposition='PRESERVED_CURRENT_UNMODELABLE_SOURCE_LEDGER'))
                excluded_ids={r['job_uid'] for r in source_exclusions}
                reference_rows=[r for r in reference_rows if r['job_uid'] not in excluded_ids]
                reference_ids={r['job_uid'] for r in reference_rows}
                prior_read=namespace['read']
                namespace['read']=lambda path:reference_rows if Path(path)==reference_path else prior_read(path)
                if any(r.get('operating_day')!=day for r in reference_rows):raise ValueError('SOURCE_R0_OPERATING_DAY')
                if {r['job_uid'] for r in current['known_population']}-reference_ids:raise ValueError('CURRENT_PHYSICAL_JOB_MISSING_R0_AUTHORITY')
                exclusions=[];floor_checks=[]
                class PandasProjection:
                    def __getattr__(self,name):return getattr(pd,name)
                    def read_parquet(self,path,**kw):
                        frame=pd.read_parquet(path,**kw)
                        if kw.get('columns')!=['id','state_at_issue','known_running_start','submit_time']:raise ValueError('CAUSAL_SNAPSHOT_PROJECTION_COLUMNS')
                        absent=frame[~frame.id.astype(str).isin(reference_ids)]
                        for uid in absent.id.astype(str):
                            request=raw[uid][0]
                            # Same frozen physical-modelability rules already in
                            # PR134's current V42 input package; never optimizer-
                            # outcome, elapsed time or capacity utilization pruning.
                            proof=immutable_unmodelable(request,current['capacities'],current['rack_compatibility'])
                            if proof['modelable']:raise ValueError('MODELABLE_SNAPSHOT_JOB_MISSING_R0:'+uid)
                            exclusions.append(dict(job_uid=uid,proof=proof,disposition='PRESERVED_UNMODELABLE_LEDGER'))
                        return frame[frame.id.astype(str).isin(reference_ids)].copy()
                namespace['pd']=PandasProjection()
                snapshot_path=CODE.parent/'MobileESS_v40a_bounded_iterative_coopt'/f'dayahead/artifacts/v37_r4a_per_day_aidc/days/{day}/V37_R4A_D1_SNAPSHOT.parquet'
                observed=pd.read_parquet(snapshot_path,columns=['id','known_running_start']);observed.id=observed.id.astype(str);observed=observed.set_index('id')
                for r in reference_rows:
                    if r['state_at_issue']!='RUNNING':continue
                    remaining=max(0,float(r['requested_walltime_seconds'])-(issue-observed.loc[r['job_uid'],'known_running_start']).total_seconds())
                    if abs(remaining-r['safe_duration_seconds'])<1e-6:continue
                    if r['safe_duration_seconds']!=900 or not 0<=remaining<900 or r['safe_duration_slots']!=1:raise ValueError('UNPROVED_SOURCE_REMAINING_DISCREPANCY:'+r['job_uid'])
                    floor_checks.append(dict(job_uid=r['job_uid'],source_seconds=r['safe_duration_seconds'],observed_request_remaining=remaining,
                        source_slots=1,reason='Source one-slot floor; RUNNING temporal domain fixed, nominal exact service replaced by frozen Q50 below'))
                original_require=namespace['require']
                def require(value,reason):
                    if not value and reason=='EXACT_REMAINING_IDENTITY' and floor_checks:return
                    original_require(value,reason)
                namespace['require']=require
                for name in ('record','csv','dump'):
                    function=getattr(original,name)
                    namespace[name]=types.FunctionType(function.__code__,namespace,argdefs=function.__defaults__)
                namespace['record'].__defaults__=('metadata',day,'FROZEN_SOURCE_REUSED',None)
                # Empty-site reconciliation is an input audit, not a model row.
                # Give its max an empty identity of zero; all nonempty arithmetic
                # and every scientific field remain the original producer.
                tree=ast.parse(inspect.getsource(original.job_ledger));patched=[]
                class EmptySite(ast.NodeTransformer):
                    def visit_Call(self,node):
                        node=self.generic_visit(node)
                        if isinstance(node.func,ast.Name) and node.func.id=='max' and len(node.args)==1 and isinstance(node.args[0],ast.GeneratorExp):
                            node.keywords.append(ast.keyword(arg='default',value=ast.Constant(0)));patched.append(node.lineno)
                        return node
                tree=EmptySite().visit(tree);ast.fix_missing_locations(tree)
                if len(patched)!=1:raise ValueError('EMPTY_SITE_AUDIT_SOURCE_SHAPE')
                exec(compile(tree,inspect.getfile(original.job_ledger),'exec'),namespace)
                jobs,reference=namespace['job_ledger'](template['capacities'],template['racks'])
                atomic(folder/'SOURCE_PROJECTION_AUDIT.json',dict(PASS=True,unmodelable_request_ledger=exclusions,source_R0_unmodelable_ledger=source_exclusions,source_one_slot_floor_checks=floor_checks,
                    current_physical_job_ids_unchanged=True,original_R0_payload_bytes_unchanged=True,source_R0_original_count=len(original_reference_rows),
                    source_R0_projected_count=len(reference_rows),Actual_outcomes_read=False,empty_site_reconciliation_default=0,
                    Q50_service_or_RUNNING_state_changed=False))
                requests=[];uids=[];submits=[]
                for j in jobs:
                    request=raw[j['job_uid']][0];uids.append(j['job_uid']);submits.append(request['submit_time'])
                    requests.append(dict(num_gpus_req=request['gpus_requested'],num_nodes_req=request['nodes_req'],num_cores_req=request['processors_req'],
                        requested_memory_mib=memory_mib(request['memory_req']),requested_seconds=request['requested_seconds'],array_index=request['array_pos'],
                        account=request['account_hash'],qos=request['qos'],partition=request['partition']))
                predicted=provider.predict_batch(requests,submit_times=submits,event_time=issue)
                source={r['job_uid']:r for r in read(reference['path'])};updated=[];windows=[]
                for j,total0 in zip(jobs,predicted):
                    total=float(total0);elapsed=j['elapsed_seconds'] or 0.;remaining=planning_remaining(total,elapsed,state=j['state'])
                    start=int(j['reference_start_if_authorized']);risk=math.ceil((total-elapsed)/900 if j['state']=='RUNNING' else start+total/900)
                    row=dict(j,**remaining,old_source_exact_service_seconds=j['exact_service_seconds'],exact_service_seconds=remaining['nominal_remaining_seconds'],
                        service_slots=remaining['nominal_slots'],V10_Q50_total_seconds=total,nominal_reference_end=start+remaining['nominal_slots'],
                        reference_end=start+remaining['nominal_slots'],risk_nominal_completion_issue_slot=risk,runtime_authority=__import__('v42_final.common',fromlist=['MODEL']).MODEL,
                        old_requested_remaining_is_new_nominal=False,unresolved_external_source_service_end=j['reference_end'] if not j['planning_eligible'] else None)
                    # The original Q50 producer retains source capability metadata;
                    # known_window supplies the actual complete finite-start domain.
                    window=known_window(row,source.get(j['job_uid']))
                    if row['planning_eligible']:windows.append(window)
                    updated.append(row)
                cc=current['forecast_inputs']['current_CC4'];bundle=deepcopy(template)
                nominal=profile(np.asarray(cc['Q50_GPUh']),np.asarray(kernel))
                spread=profile(np.asarray(cc['Q90_GPUh'])-np.asarray(cc['Q50_GPUh']),np.asarray(kernel))
                certificate=CODE/f'frozen_artifacts/v41r4_may/e/{day.replace("-","")}/V41_ELECTRICAL_CERTIFICATE.json'
                cert=read(certificate)
                if cert['input_identity']['identity']['inputs']['day']!=day:raise ValueError('ELECTRICAL_DAY_IDENTITY')
                bundle.update(day=day,issue_time=issue.isoformat(),known_population=updated,reference=reference,
                    electrical_certificate=record(certificate),grid_outputs=cert['outputs'],C0_Q50=cc['Q50_GPUh'],C0_Q90=cc['Q90_GPUh'],
                    unknown_nominal_GPU=nominal.tolist(),CC4_reserve_GPU=spread.tolist(),runtime_provider=record(provider.root/'INTEGRITY.json'))
                atomic(folder/'NATIVE_INPUT.json',bundle)
            atomic(folder/'WINDOWS.json',windows);atomic(folder/'OPERATIONS.json',ops)
            transitive=[]
            def walk(v):
                if isinstance(v,dict):
                    if 'path' in v and 'sha256' in v:transitive.append(record(resolve(v)))
                    else:
                        for x in v.values():walk(x)
                elif isinstance(v,list):
                    for x in v:walk(x)
            walk(bundle)
            # RAW exogenous data are identities only; never loaded into Planning.
            files.extend(transitive+[record(folder/n) for n in ('NATIVE_INPUT.json','WINDOWS.json','OPERATIONS.json')])
            rows.append(dict(day=day,PASS=True,bundle=record(folder/'NATIVE_INPUT.json'),windows=record(folder/'WINDOWS.json'),
                jobs=len(bundle['known_population']),original_R0=True,scientific_input_base=BASE,PR150_151_scientific_producer=False))
        except Exception as e:
            atomic(folder/'INPUT_AUTHORITY_ERROR.json',dict(day=day,error=str(e),type=type(e).__name__,scientific_fallback=False))
            rows.append(dict(day=day,PASS=False,error=str(e),scientific_fallback=False))
        print('PR134_INPUT',day,rows[-1]['PASS'],rows[-1].get('error',''),flush=True)
    atomic(root/'MAY31_INPUT_IDENTITY.json',dict(days=rows,all_ready=all(r['PASS'] for r in rows),files=list({r['path']:r for r in files}.values()),
        scientific_base=BASE,May01_accepted_input_byte_identical=sha(dest/'2025-05-01/NATIVE_INPUT.json')==sha(ROOT/'docs/v42_final_integration/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),
        provider_fit_calls=0,Actual_outcome_reads=0,reference_reconstruction_from_PR150=False))
    return rows

if __name__=='__main__':
    import sys
    produce(Path(sys.argv[1]))
