"""Freeze 20 literature-size R2 prerequisite cases; Native/AC/Actual all zero."""
from collections import Counter
from pathlib import Path
import argparse
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v42_integration.current_ac_admission import epoch
from v42_integration.m_engine import _write, file_record
from v42_integration.policy import digest
from v42_integration.research_presite_contract import source_authority
from v42_integration.research_presite_transfer_literature import (
    LiteratureTransferProvider, PAYLOAD_MB, make_literature_spec, provider_decision_equivalence)

RC = ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
RAW = Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')
FACTS = RC/'RC03/LITERATURE/LITERATURE_FACTS.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def prepare(output):
    if output.exists():
        raise FileExistsError('LITERATURE_FREEZE_MUST_NOT_OVERWRITE')
    equivalence=provider_decision_equivalence()
    actual_record=file_record(RAW/'ACTUAL_INPUT_BUNDLE.json')
    native_record=file_record(RAW/'NATIVE_INPUT_TEMPLATE_B1.json')
    placement_record=file_record(RC/'RC01/AIDC/REPLAY02/C1/INITIAL_PLACEMENT_LEDGER.json')
    fact_record=file_record(FACTS)
    sources=[actual_record,native_record,placement_record,fact_record,
        *[file_record(ROOT/p) for p in (
            'v42_integration/research_presite_transfer_literature.py',
            'v42_integration/research_presite_contract.py','v42_integration/experimental_qos.py',
            'v42_integration/research_presite_actual.py')],file_record(__file__)]
    native=read(native_record['path']);wan=native['WAN']
    placements=read(placement_record['path'])
    raw=read(actual_record['path'])
    rows_by_uid={str(r['job_uid']):r for r in raw['post_issue_arrivals']}
    begin=epoch('2025-05-01T00:00:00+10:00')
    summary=[]
    output.mkdir(parents=True)
    _write(output/'STATIC_PROVIDER_EQUIVALENCE.json',equivalence)
    for payload in PAYLOAD_MB:
        for bandwidth in (.25,1.):
            for prepare_seconds in (0,900):
                label=f'R2_PER_JOB_{payload}MB_B{bandwidth:g}_T{prepare_seconds}'
                spec=make_literature_spec(payload_MB=payload,bandwidth_fraction=bandwidth,
                    preparation_seconds=prepare_seconds,literature_fact_record=fact_record,
                    source_records=sources,native_wan_sha=digest(wan),shared_sites=sorted(native['capacities']))
                provider=LiteratureTransferProvider(spec,native_wan=wan)
                _write(output/label/'RESEARCH_CONTRACT.json',dict(spec=spec,science_sha=provider.science_sha,
                    case_sha=digest(dict(science_sha=provider.science_sha,source_records=sources)),
                    execution_status='NOT_RUN_PREREQUISITES_ONLY'))
                candidates=[];reasons=Counter();eligible=set();delays=[];transfers=[]
                for event in placements:
                    source=rows_by_uid[event['uid']]
                    now=max(begin,math.ceil(event['time_seconds']/900)*900)
                    m=dict(uid=event['uid'],submit_seconds=epoch(source['submit_time']),gpu=source['GPU_gang'],
                        compatible_sites=source['compatible_sites'],reference_site=event['basic_site'],
                        state='PENDING',origin_unknown=True,accumulated_compute_seconds=0.,
                        t50_seconds=source['Q50_total_seconds'],qos=source.get('qos','UNCONFIRMED'),
                        protected=source.get('protected'),batch_eligible=source.get('batch_eligible'),
                        can_prestart_place=False)
                    # These historical Source descriptors and placement records
                    # have no public episode_id: preserve V1's UID fallback.
                    if source.get('episode_id') is not None:
                        m['episode_id']=source['episode_id']
                    provider.register_observed(m,source_authority(source,actual_record,now=now),now=now)
                    qos=dict(allowed_starts_seconds=[],latest_start_seconds=now,budget_seconds=0.)
                    for site in sorted(set(m['compatible_sites'])-{event['basic_site']}):
                        r=provider.propose(m,site,now,day_begin=begin,qos_receipt=qos)
                        candidates.append(r);reasons[r['reason'] or r['status']]+=1
                        if r['eligible']:
                            eligible.add(m['uid'])
                        if r['ready_at_seconds'] is not None:
                            delays.append(r['ready_at_seconds']-now);transfers.append(r['transfer_seconds'])
                if provider.transfers or any(r['status'] in ('READY','PREPARATION_REQUIRED') for r in candidates):
                    raise ValueError('ZERO_ORIGINAL_QOS_MUST_NOT_AUTHORIZE_R2_TRANSFER')
                item=dict(label=label,science_sha=provider.science_sha,payload_bytes_per_job=payload*1_000_000,
                    bandwidth_fraction=bandwidth,preparation_seconds=prepare_seconds,
                    historical_already_observed_UIDs=len(placements),
                    eligibility_before_resource_and_QoS_checks_UIDs=len(eligible),
                    candidate_prerequisites=len(candidates),reasons=dict(reasons),
                    data_ready_delay_min_seconds=min(delays) if delays else None,
                    data_ready_delay_max_seconds=max(delays) if delays else None,
                    transfer_min_seconds=min(transfers) if transfers else None,
                    transfer_max_seconds=max(transfers) if transfers else None,
                    transfers_committed=0,actual_changed_UIDs='NOT_RUN',Changed_GPUh='NOT_RUN',
                    candidate_AC='NOT_RUN',performance='NOT_RUN')
                _write(output/label/'PREREQUISITE_SENSITIVITY_NOT_ACTUAL.json',dict(**item,
                    scope='RETROSPECTIVE_RC01_ALREADY_OBSERVED_PREREQUISITES_ONLY',
                    retrospective_UID_table_passed_to_controller=False,
                    episode_membership='EXISTING_PUBLIC_EPISODE_IF_PRESENT_OTHERWISE_ORIGINAL_UID_FALLBACK',
                    strict_original_QoS_additional_delay_seconds=0,
                    reissued_QoS_receipts=False,Native_calls=0,AC_calls=0,Actual_calls=0,
                    candidates=candidates))
                summary.append(item)
    unchanged=all(file_record(r['path'])==r for r in sources)
    if not unchanged:
        raise ValueError('SOURCE_CHANGED_DURING_LITERATURE_PREPARATION')
    result=dict(status='PASS_20_FROZEN_CONTRACTS_AND_PREREQUISITES_ONLY',cases=summary,
        case_count=len(summary),unique_science_shas=len({r['science_sha'] for r in summary}),
        Native_calls=0,AC_calls=0,Actual_calls=0,source_records=sources,
        existing_Source_and_Raw_unchanged=unchanged,
        original_WAN_bytes_per_GPU=wan['bytes_per_gpu'],
        original_80GB_per_GPU_is_Kestrel_input_measurement=False,
        payload_model='ASSUMED_PER_JOB_PAYLOAD_FROM_LITERATURE_EXAMPLES',
        Kestrel_task_type_mapping=None,original_QoS_additional_delay_seconds=0,
        all_R2_transfers_rejected_with_original_zero_delay=True,
        official_voltage_gate_or_Actual_certified=False,
        literature_fact_record=fact_record,static_provider_equivalence=equivalence)
    _write(output/'LITERATURE_R2_PREPARATION.json',result)
    print(json.dumps({k:result[k] for k in ('status','case_count','unique_science_shas','Native_calls','AC_calls','Actual_calls')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=RC/'RC03/LITERATURE_TRANSFER/CONTRACTS01')
    prepare(parser.parse_args().output)
