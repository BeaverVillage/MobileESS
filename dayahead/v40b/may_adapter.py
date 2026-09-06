"""Date admission and input routing only; all V40A optimization code is unchanged."""
from contextlib import contextmanager
from pathlib import Path
import pandas as pd
from .common import REPO, ROOT, V40A, DAYS, read, write, sha, digest

def traffic_authority(day):
    from dayahead.v35.execution import daily_traffic_authority
    from dayahead.v35.contracts import PHASE_MAY
    from dayahead.v37.runner import ADMISSION
    cache=REPO/'dayahead/cache/v37_may_locked_final/traffic'
    paths=[cache/'shared/traffic'/day/name for name in ('TRAFFIC_FORECAST.npz','ROUTE_TABLE.json.gz')]
    if not all(p.is_file() for p in paths):raise ValueError('MISSING_FROZEN_MAY_TRAFFIC')
    bundle,graph,table,files=daily_traffic_authority(REPO,cache,PHASE_MAY,day,ADMISSION)
    if not bundle.causality_pass or bundle.future_actual_read_count or bundle.max_input_timestamp>bundle.issue_time:
        raise ValueError('MAY_TRAFFIC_CAUSALITY')
    return {'day':day,'files':list(files),'forecast_SHA':bundle.canonical_sha256,
       'route_table_SHA':table.canonical_sha256,'road_graph_SHA':graph.route_graph_sha,
       'issue_time':bundle.issue_time.isoformat(),'max_input_timestamp':bundle.max_input_timestamp.isoformat(),
       'future_actual_read_count':bundle.future_actual_read_count,'causality_pass':bundle.causality_pass}

@contextmanager
def admit_day(day):
    if day not in DAYS:raise ValueError('UNAUTHORIZED_MAY_DAY')
    from dayahead.v35 import execution
    from dayahead.v35.contracts import PHASE_MAY
    from dayahead.v37.runner import ADMISSION
    from dayahead.v35r3 import algorithm as r3
    from dayahead.v35r3e import algorithm as r3e
    original=execution.daily_traffic_authority,r3.assert_apr01_only,r3e.assert_apr01_only
    def selected(target):
        if target!=day:raise ValueError('CROSS_DAY_ADMISSION')
    def traffic(_repo,_cache,_phase,target,_admission):
        selected(target)
        return original[0](REPO,REPO/'dayahead/cache/v37_may_locked_final/traffic',PHASE_MAY,target,ADMISSION)
    try:
        execution.daily_traffic_authority=traffic
        r3.assert_apr01_only=r3e.assert_apr01_only=selected
        yield
    finally:
        execution.daily_traffic_authority,r3.assert_apr01_only,r3e.assert_apr01_only=original

def accepted_a0(day,context):
    from dayahead.v40a.accepted_initial import materialize_accepted_a0
    from dayahead.v39e.campaign_adapter import freeze_path
    path=freeze_path(REPO,day,'B3')
    snapshot=read(V40A/'V40A_PRESTOP_CAMPAIGN_SNAPSHOT.json')
    expected=snapshot['production_authority_fingerprints'][path.relative_to(REPO).as_posix()]
    source=REPO/'dayahead/artifacts/v37_r4a_per_day_aidc/days'/day
    ledger=pd.read_parquet(source/'V37_R4A_JOB_LEDGER.parquet')
    result=materialize_accepted_a0(path,expected,ledger.to_dict('records'),context)
    result['RSP_base_materialization_seconds']=0.0
    return result

def seal_method():
    from dayahead.v40a.contracts import CONTRACTS
    from .common import audit,now_utc
    path=ROOT/'V40B_V40A_METHOD_FREEZE.json'
    if path.exists():return read(path)
    sealed=read(V40A/'V40A_ARTIFACT_SHA256.json')
    sources=sealed['V40A_source_files']
    if audit(REPO,sources)['status']!='PASS':raise ValueError('V40A_CORE_DRIFT')
    contracts={name:sha(V40A/name) for name in CONTRACTS}
    identity={'method':'BOUNDED_ITERATIVE_AIDC_MESS_CO_OPTIMIZATION','V40A_source_files':sources,
      'contract_files':contracts,'B3_sequence':['A0','M1_ROUTE_PQ','A1_FEEDBACK','MF_FIXED_ROUTE_PQ'],
      'coordination_depth':1,'full_route_search_passes':1,'second_route_search':0,
      'A1_RUNNING_rule':'FEASIBLE_BASE_STATE_NO_ADDITIONAL_RUNNING_MIGRATION_FOR_OBJECTIVE_IMPROVEMENT',
      'max_parallel_day_workers':4,'Gurobi_threads_per_model':4,
      'May_date_adapter_source_SHA':sha(Path(__file__)),
      'accepted_A0':'V39K-bound per-day frozen DA decisions; historical B3 MESS/results excluded',
      'traffic_input_manifest_SHA':sha(ROOT/'V40B_D1_INPUT_COPY_MANIFEST.json')}
    result={'status':'PASS','sealed_at_utc':now_utc(),'method_SHA':digest(identity),
       'identity':identity,'MAY_RESULT_BASED_TUNING_ALLOWED':'NO','immutable':True}
    write(path,result);return result
