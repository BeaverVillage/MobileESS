import json,pickle
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v42_integration.production_case import STATIC,ARCHIVE,TIMING
from v42_integration.partial_canary import SOURCE_DIR,source_known_records
from v42_integration.planning_inputs import prepare_planning
from v42_integration.policy import digest
from v42_integration.unified_contract import load_contracts,REPORT
from v42_integration.aidc_sensitivity_runtime import Research60QoSProvider,build_issue_only_dday_reference,select_cc4_headroom_seed_choices
with STATIC.open('rb') as f:data=pickle.load(f)
shared=load_contracts();source=json.loads((SOURCE_DIR/'SOURCE_FREEZE_DDAY_GRID_V5.json').read_text(encoding='utf-8'))
prepared=prepare_planning(ARCHIVE/'raw/2025-05-01',data,source_freeze=source,
    strict_stats=SOURCE_DIR/'QOS_EMPIRICAL_STATS_STRICT.json',case_sha='READ_ONLY_SOURCE_DESCRIPTOR_NAMESPACE',
    provider_sha=digest(data[0]['runtime_provider']))
strict=prepared['qos_provider']
raw=json.loads((ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json').read_text(encoding='utf-8'))
records=source_known_records(strict,raw)
issue=prepared['issue_epoch_seconds'];begin=prepared['day_begin_epoch_seconds']
records,audit=build_issue_only_dday_reference(records,data,issue_seconds=issue,begin_seconds=begin,namespace_sha=shared['bindings']['science_sha'])
provider=Research60QoSProvider(strict,case_sha=shared['bindings']['case_sha'],
    frozen_spec=json.loads((REPORT/'TIME_SHIFT_60MIN_QOS_CONTRACT.json').read_text(encoding='utf-8')))
for uid,j in records.items():provider.register_observed(uid);provider.issue(j)
from v42_integration.qos import receipt_slot_domain
jobs={u:replace(j,reference_start=int((records[u].reference_start_seconds-issue)/900),
    reference_site=audit['assignments'][u]['reference_site']) if j.state=='PENDING' else j for u,j in data[1].items()}
windows={u:(j.reference_start,) if j.state=='RUNNING' else tuple(t for t in receipt_slot_domain(provider.receipts[u],axis_origin_seconds=issue)
    if t>=24 and t<=data[2][u].latest_completion-j.service_slots) for u,j in jobs.items()}
case=SimpleNamespace(arm='B1',stage='A1',case_sha='DESCRIPTOR_ONLY_SAME_STUDY_GEOMETRY_NOT_NATIVE_CERTIFICATE',
    data=(data[0],jobs)+data[2:],qos_receipts={u:provider.receipts[u] for u in jobs},window_slots=windows,
    grid=SimpleNamespace(timing_lower=pd.read_csv(TIMING).Q10.to_numpy()),unified_bindings=shared['bindings'])
result=select_cc4_headroom_seed_choices(case,issue_seconds=issue,pairs=21,output=REPORT/'KNOWN_CC4_HEADROOM_SOURCE_ONLY_CANDIDATE.json')
print(json.dumps(dict(status=result['status'],selected_pairs=result['selected_pairs'],selected_UIDs=len(result['selected_UIDs']),
    pairs_by_site=result['same_site_pair_counts'],CDF_necessary_PASS=result['all_necessary_CDF_capacity_PASS'],
    first_slots=result['cumulative_capacity_audit'][:8],Full=result['Full_grid_and_CDF'])))
