"""Compile date-bound R1 data environments, never future Unknown decisions.

Only a contract, public planning identity and immutable file hashes are saved.
There are no eligible UID rosters, assignments, fresh permissions or QoS grants.
"""
from pathlib import Path
import gc
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
from v42_integration.policy import digest
from v42_integration.research_presite_contract import make_spec,ResearchPresiteProvider

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
OUT=BASE/'RC03/CAMPAIGN_R1_CONTRACTS'
RAW=Path('D:/v42_may_joint_repair_campaign_20261013/raw')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    if OUT.exists():raise FileExistsError('DATE_RESEARCH_CONTRACTS_MUST_NOT_OVERWRITE')
    import gurobipy as gp
    methods={name:getattr(gp.Model,name) for name in ('__init__','optimize','presolve','computeIIS')}
    attempts=[]
    def forbidden(*args,**kwargs):
        attempts.append('MODEL_OR_NATIVE');raise RuntimeError('CONTRACT_PREPARATION_MODEL_AND_NATIVE_FORBIDDEN')
    start=time.perf_counter();days=[];policies={};OUT.mkdir(parents=True)
    facts=file_record(BASE/'RC03/LITERATURE/LITERATURE_FACTS.json')
    core=[file_record(ROOT/name) for name in ('v42_integration/research_presite_contract.py',
        'v42_integration/experimental_qos.py','tools/prepare_v42_campaign_presite_contracts.py')]
    try:
        for name in methods:setattr(gp.Model,name,forbidden)
        for index in range(1,32):
            day=f'2025-05-{index:02d}'
            manifest=read(BASE/'RC02/DATE_CASES/COMPILE01'/day/'CASE/D0_CASE_MANIFEST.json')
            native_record=file_record(RAW/day/'NATIVE_INPUT_TEMPLATE_B1.json')
            actual_record=file_record(RAW/day/'ACTUAL_INPUT_BUNDLE.json')
            native=read(native_record['path'])
            spec=make_spec(scenario='R1',source_records=[actual_record,native_record,facts,*core],
                native_wan_sha=digest(native['WAN']),shared_sites=sorted(native['capacities']),ready_delay_slots=0)
            spec['date_contract']=dict(day=day,planning_identity=manifest['identity'],
                planning_source_sha=manifest['source_sha'],future_UID_roster_in_contract=False)
            spec['literature_fact_record']=facts
            provider=ResearchPresiteProvider(spec,native_wan=native['WAN'])
            path=OUT/day/'R1_SHARED_INPUT_SPEC.json';_write(path,spec)
            policy=dict(mode='R1',variant='C1',research_contract=file_record(path))
            policies[day]=policy
            days.append(dict(day=day,status='RESEARCH_CONTRACT_PREPARED_NOT_ACTUAL_CERTIFIED',
                planning_identity=manifest['identity'],planning_source_sha=manifest['source_sha'],
                science_sha=provider.science_sha,spec=file_record(path),policy_sha=digest(policy),
                Source_Actual_record=actual_record,source_permission_or_ready_facts_added=False,
                future_UID_decisions=0,Actual_runs=0,AC_solves=0,Native_calls=0))
            print(day,'R1_CONTRACT_PREPARED',flush=True)
            del native,provider;gc.collect()
    finally:
        for name,method in methods.items():setattr(gp.Model,name,method)
    if attempts:raise ValueError('FORBIDDEN_NATIVE_OR_MODEL_ENTRY')
    assert all(file_record(r['path'])==r for r in core+[facts])
    _write(OUT/'MAY31_R1_CONTRACT_PREPARATION.json',dict(schema='MAY31_DATE_BOUND_R1_RESEARCH_CONTRACTS_V1',
        status='PASS_CONTRACT_PREPARATION_ONLY',days=days,prepared=len(days),actual_policy_by_day=policies,
        default_research_scenario='R1',Native_calls=0,AC_solves=0,Actual_runs=0,model_builds=0,
        future_UID_decisions=0,original_QoS_or_source_permissions_changed=False,
        R1_shared_input_is_ASSUMED=True,actual_WAN_or_customer_approval_claim=False,
        original_Source_Raw_unchanged=True,canary_or_full96_evidence_created=False,
        wall_seconds=time.perf_counter()-start,blocked_native_attempts=attempts,
        data_environment_does_not_certify_GPU_Rack_AC_or_actual_movement=True))


if __name__=='__main__':main()
