"""Display certified bounds and separate restricted LP diagnostics by stage."""
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
import json
import math


@lru_cache(maxsize=128)
def _json(path, size, modified):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def read(path):
    try:
        path=Path(path);stat=path.stat()
        if stat.st_size>8*1024*1024:return {}
        value=_json(str(path),stat.st_size,stat.st_mtime_ns)
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def number(value):
    if isinstance(value,bool) or value is None:return None
    try:
        value=float(Fraction(value))
        return value if math.isfinite(value) and abs(value)<1e90 else None
    except (ValueError,TypeError,ArithmeticError):return None


def text(value):
    return format(value,'.10g') if value is not None else '—'


def gap_text(value):
    if value is None:return '상·하한 검증 대기'
    percent=value*100
    return (format(percent,'.4g') if 0<abs(percent)<.001 else format(percent,'.4f').rstrip('0').rstrip('.'))+'%'


def finish(ub,lb,lp,ub_source,lb_source,pending,certified=False,scope='원본 FULL',provided_gap=None):
    gap=number(provided_gap)
    consistent=ub is None or lb is None or lb<=ub
    if not consistent:gap=None
    elif gap is None and ub is not None and lb is not None:
        gap=(ub-lb)/abs(ub) if ub else 0. if lb==0 else None
    if ub is None or lb is None:gap=None
    ub_pending='FULL 해 검증 대기' if pending in ('독립 K48 하한 계산 중','전체 Pricing 하한 대기') else pending
    ub_status='FULL 정수해 검증 완료' if ub is not None else '정수해 검증 전' if lp is not None else ub_pending
    lb_status='전체 Pricing 독립 하한' if lb is not None and 'P1' in lb_source else '독립 Global 하한' if lb is not None else pending
    lines=[f'검증 UB: {text(ub) if ub is not None else ub_status} · LB: {text(lb) if lb is not None else lb_status}',
           f'Global Gap: {gap_text(gap)}'+(' · 목표 인증 완료' if certified else ' · 목표 인증 전'),
           '적용 범위: '+scope]
    if lp is not None:lines.append(f'P1 LP 목적값: {text(lp)} · 연속 완화 값이며 정수 UB와 별도')
    if not consistent:lines.append('상·하한 순서 불일치 · Global Gap 검산 필요')
    return dict(UB=ub,LB=lb,P1_LP_objective=lp,relative_gap=gap,gap_certified=bool(certified and consistent and gap is not None),
        UB_source=ub_source,LB_source=lb_source,scope=scope,UB_status=ub_status,LB_status=lb_status,
        ub_text=text(ub) if ub is not None else ub_status,lb_text=text(lb) if lb is not None else lb_status,
        gap_text=gap_text(gap) if consistent else '검산 필요',lines=lines)


def a_bounds(folder):
    folder=Path(folder);out=folder/'OUTPUT';result=read(folder/'RESULT.json')
    trace=read(out/'P1_TRACE.json').get('trajectory',[])
    closure=read(out/'P1_RESULT.json');validated=read(out/'VALIDATED_INTEGER_INCUMBENTS.json').get('trajectory',[])
    ub=[];lb=[];lp=None
    for row in trace:
        value=number(row.get('valid_LB'))
        if value is not None:lb.append((value,str(out/'P1_TRACE.json')))
        value=number(row.get('objective'))
        if value is not None:lp=value
    # The next LP can finish before its full Pricing round appends the trace.
    rounds=sorted((out/'P1').glob('S[0-9]*'),key=lambda p:int(p.name[1:]) if p.name[1:].isdigit() else -1)
    for path in reversed(rounds):
        native=read(path/'NATIVE_RESULT.json')
        if native.get('status')==2 and number(native.get('objective')) is not None:
            lp=number(native['objective']);break
    if closure.get('PASS') and closure.get('P1_LP_closure'):
        value=number(closure.get('exact_valid_LB',closure.get('valid_LB')))
        if value is not None:lb.append((value,str(out/'P1_RESULT.json')))
    accepted=[]
    for row in validated:
        if row.get('PASS') and row.get('original_integer_types_restored') and row.get('physical'):
            accepted.append((row,str(out/'VALIDATED_INTEGER_INCUMBENTS.json')))
    if result.get('FULL_feasible') or result.get('relaxed_FULL_feasible'):
        accepted.append((result,str(folder/'RESULT.json')))
    for row,path in accepted:
        value=number(row.get('exact_UB',row.get('UB')))
        if value is not None:ub.append((value,path))
        value=number(row.get('exact_LB',row.get('LB')))
        if value is not None:lb.append((value,path))
    best_ub=min(ub,default=(None,''),key=lambda r:r[0]);best_lb=max(lb,default=(None,''),key=lambda r:r[0])
    zero=read(out/'PHASE_I_ZERO_CERTIFICATE.json')
    pending='전체 Pricing 하한 대기' if zero.get('PASS') else 'Phase I 진행 중' if (out/'PHASE_I_TRACE.json').exists() else '모델 구성 중'
    certified=bool(result.get('independent_Global_LB_validated') and number(result.get('certified_gap')) is not None
        and 0<=number(result['certified_gap'])<=.005)
    if not certified:
        certified=any(r.get('acceptance',{}).get('PASS') for r,p in accepted)
    return finish(best_ub[0],best_lb[0],lp,best_ub[1],best_lb[1],pending,certified,
        'A2 선택행 전압 완화 모델' if result.get('relaxed_FULL_feasible') and not result.get('FULL_feasible') else '원본 FULL · 해당 단계 P1')


def last_trace(path):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(max(0,Path(path).stat().st_size-65536))
            lines=stream.read().decode('utf-8',errors='replace').splitlines()
        for line in reversed(lines):
            try:
                row=json.loads(line)
                if isinstance(row,dict):return row
            except ValueError:pass
    except OSError:pass
    return {}


def m_bounds(folder):
    folder=Path(folder);result=read(folder/'RESULT.json')
    trace_path=folder/'GLOBAL_CONTROL/GLOBAL_GAP_TRACE.jsonl';trace=last_trace(trace_path)
    lower=read(folder/'LOWER_STAGE_RESULT.json');upper=read(folder/'UPPER_STAGE_RESULT.json')
    ub=[];lb=[]
    if trace.get('bound_consistency') is not False:
        value=number(trace.get('Global_UB'))
        if trace.get('FULL_feasible') and value is not None:ub.append((value,str(trace_path)))
        value=number(trace.get('Global_LB'))
        if value is not None:lb.append((value,str(trace_path)))
    if lower.get('Global_LB_valid') or lower.get('K48_Global_LB_valid'):
        value=number(lower.get('Global_LB',lower.get('K48_Global_LB')))
        if value is not None:lb.append((value,str(folder/'LOWER_STAGE_RESULT.json')))
    if upper.get('FULL_validated'):
        value=number(upper.get('BEST_GLOBAL_UB'))
        if value is not None:ub.append((value,str(folder/'UPPER_STAGE_RESULT.json')))
    if result.get('FULL_feasible'):
        value=number(result.get('Global_UB'))
        if value is not None:ub.append((value,str(folder/'RESULT.json')))
    if result.get('Global_LB_valid') or result.get('independent_Global_LB_validated'):
        value=number(result.get('Global_LB'))
        if value is not None:lb.append((value,str(folder/'RESULT.json')))
    best_ub=min(ub,default=(None,''),key=lambda r:r[0]);best_lb=max(lb,default=(None,''),key=lambda r:r[0])
    pending='독립 K48 하한 계산 중' if (folder/'K48_NATIVE_LEDGER.json').exists() else '모델 구성 중'
    return finish(best_ub[0],best_lb[0],None,best_ub[1],best_lb[1],pending,
        bool(result.get('global_gap_certified') or trace.get('global_gap_certified')),
        '원본 FULL · 현재 고정 AIDC 계획')


def display_fields(bounds):
    return dict(incumbent=bounds['ub_text'],bound=bounds['lb_text'],gap=bounds['gap_text'],
        bound_details=bounds,metrics_visible=True,metrics_label='현재 단계 검증 UB / 독립 LB / Global Gap')


def stage_rows(case,active):
    case=Path(case);restored=read(case/'RESTORED_COMPLETED_STAGES.json');rows=[]
    for stage in ('A1','M1','A2','M2'):
        folder=case/stage;reused=False
        if not folder.is_dir() and stage in restored:
            folder=Path(restored[stage].get('root',''))
            if (folder.name!=stage or folder.parent.parent.name!=case.parent.name
                    or folder.parent.parent.parent.name!=case.parent.parent.name):continue
            reused=True
        if not folder.is_dir():continue
        bounds=(a_bounds if stage.startswith('A') else m_bounds)(folder)
        result=read(folder/'RESULT.json')
        status='계산 중' if stage==active and not result else 'Gap 인증' if bounds['gap_certified'] else 'FULL 해 · Gap 미달' if bounds['UB'] is not None else '검증 실패' if result else '대기'
        if reused:status='재사용 · '+status
        rows.append(dict(stage=stage,attempt=folder.parent.name,status=status,source=str(folder),**bounds))
    return rows
