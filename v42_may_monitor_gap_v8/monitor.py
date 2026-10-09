"""Prominent, evidence-backed current Global Gap and explicit waiting reasons."""
from pathlib import Path
from types import SimpleNamespace
from v42_may_mess_build_v7 import monitor as previous
from v42_campaign_monitor import monitor as display
from v42_may_campaign_native90.a_routing import rebound
from v42_pr134_b1.common import read, same_process


def gap_info(row):
    progress = row.get('progress') or {}
    ub, lb, gap = (row.get(name) for name in ('UB', 'independent_Global_LB', 'Certified_Gap'))
    available = (display.finite(ub) and display.finite(lb) and lb <= ub
                 and display.finite(gap) and gap >= 0)
    if available:
        reason = '독립 인증 하한과 검증된 유효 해 기준'
    elif not display.finite(ub):
        reason = '검증된 정수·물리 유효 해(UB) 대기'
    elif not display.finite(lb):
        reason = '원본 전체 도메인 독립 하한(LB) 대기'
    elif lb > ub:
        reason = 'LB > UB: 보고값 확인 필요'
    else:
        reason = '인증 Gap 계산 대기'
    # Local/native solver gaps are explicitly separate from the Global proof.
    solver = display.take(progress, 'Native_MIPGap', 'solver_MIPGap', 'MIPGap', 'native_gap')
    if solver is not None and solver < 0:
        solver = None
    return dict(available=available, value=gap if available else None, reason=reason,
                UB=ub, independent_Global_LB=lb, target=row.get('target_gap'),
                source='CURRENT_DATE_INDEPENDENT_GLOBAL_CERTIFICATE' if available else None,
                solver_gap=solver, solver_gap_is_Global_certificate=False,
                report_UTC=progress.get('timestamp_UTC'), day=row.get('day'), arm=row.get('arm'),
                phase=row.get('phase'), input_SHA=row.get('input_SHA'))


def view(root):
    value = previous.view(root)
    for worker in value['workers']:
        worker['global_gap_display'] = gap_info(worker)
        worker['worker_result_received'] = result_received(worker)
    value['worker_slots'] = [next((w for w in value['workers'] if w['arm'] == 'B2'
        and w['worker_slot'] == slot), dict(arm='B2', worker_slot=slot, day=None,
        phase='IDLE', worker_alive=False)) for slot in (1, 2, 3)]
    heartbeat = display.original.optional_json(Path(root) / 'COORDINATOR_HEARTBEAT.json')
    if same_process(heartbeat.get('process', {})):
        value['state'] = heartbeat.get('state', value['state'])
    value.update(display_version='GAP_DISPLAY_V8_20261009', read_only=True,
                 campaign_source_changed=False, gap_interpolation=False)
    return value


def result_received(row):
    if row.get('worker_alive') or not row.get('request'):
        return False
    request = display.original.optional_json(row['request'])
    result = display.original.optional_json(request.get('result','')) if request.get('result') else {}
    identity = result.get('identity') or {}
    names = ('run_id','arm','day','attempt_id','algorithm_version')
    return bool(result and row.get('input_SHA') and all(request.get(k) is not None and identity.get(k) == request[k] for k in names)
                and result.get('input_SHA') == row.get('input_SHA'))


def run(root):
    from .service import monitor_scope
    with monitor_scope(root) as acquired:
        if acquired:
            proxy = SimpleNamespace(runtime_path=previous.co.runtime_path, load_manifest=previous.co.load_manifest)
            return rebound(display.run, dict(display.run.__globals__, original=proxy,
                view=view, __file__=__file__))(root)
