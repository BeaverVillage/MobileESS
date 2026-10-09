"""The existing display reads the explicit V5 checkpoint and attempt journal."""
from types import SimpleNamespace
from pathlib import Path
from v42_may_campaign import monitor as base
from v42_campaign_monitor import monitor as display
from v42_may_campaign_native90.a_routing import rebound
from . import coordinator as co


def _base_view(root):
    original_optional=base.optional_json
    def optional(path, *args):
        path=Path(path)
        mapping={'CHECKPOINT.json':'CHECKPOINT_V7.json','ACTIVE.json':'ACTIVE_V7.json'}
        if path.name in mapping:
            path=path.with_name(mapping[path.name])
        return original_optional(path,*args)
    namespace=dict(base.view.__globals__,load_manifest=co.load_manifest,optional_json=optional,
        read_actives=co.read_actives,worker_snapshot=co.worker_snapshot,counts=co.counts)
    return rebound(base.view,namespace)(root)


def view(root):
    result=rebound(display.view,dict(display.view.__globals__,original=SimpleNamespace(view=_base_view),
                                   enrich_worker=enrich_worker))(root)
    cp=co.read(Path(root)/'CHECKPOINT_V7.json')
    for rows in result['date_tables'].values():
        for row in rows:
            row['summary']=co.normalized_summary(row)
    result.update(algorithm_version='B2_BUILD_INPUT_REUSE_V7_20261009',
        recovery_queue=[r['day'] for r in cp['dates'].values()
            if r.get('original_attempt') and r['status'] not in co.TERMINAL],
        original_failures_preserved=True,terminal_date_retries=1)
    result['terminal_date_retries'] = 0
    result['active_worker_versions'] = {
        worker['arm'] + '/' + worker['day']: co.read(worker['request']).get('algorithm_version')
        for worker in result.get('workers', [])}
    result['B2_build_validation'] = base.optional_json(Path(root) / 'B2_BUILD_FULL_VALIDATION_V7.json')
    return result


def enrich_worker(row, epoch):
    result=display.enrich_worker(row,epoch)
    request=base.optional_json(row.get('request',''))
    ledger=base.optional_json(Path(request['result']).parent/'NATIVE_RUNTIME_LEDGER.json') if request.get('result') else {}
    # The completed Native ledger is authoritative even when the last solver
    # report still contains an earlier Runtime. Do not interpolate optimize.
    measured=ledger.get('measured_Native_Runtime')
    if display.finite(measured):
        result.update(Native_Runtime_seconds=measured,native_remaining_seconds=max(0.,5400.-measured),
                      remaining_seconds=max(0.,5400.-measured))
    calls=ledger.get('calls',[])
    result.update(Native_calls=len(calls),native_inflight=bool(ledger.get('inflight')),
        latest_native_component=calls[-1].get('component') if calls else None,
        input_SHA=co.sha(Path(request['input_folder'])/'NATIVE_INPUT.json') if request.get('input_folder') else None)
    detail=result.get('build_detail') or {}
    counters=result['build']['counters']
    for name,key in [('검증한 물리 클래스','physical_classes_verified'),('생성한 물리 클래스','physical_classes_complete')]:
        if display.finite(detail.get(key)):counters[name]=detail[key]
    result['attempt_path']=str(Path(request['result']).parent) if request.get('result') else None
    result['last_internal_progress_UTC']=detail.get('build_detail_UTC') if not result['build']['complete'] else result.get('last_internal_progress_UTC')
    return result


def run(root, port=None):
    proxy=SimpleNamespace(runtime_path=co.runtime_path,load_manifest=co.load_manifest)
    return rebound(display.run,dict(display.run.__globals__,original=proxy,view=view,__file__=__file__))(root,port)
