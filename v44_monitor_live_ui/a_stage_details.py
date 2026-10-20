"""Read-only A1/A2 evidence, time attribution and bounded nonblocking sampling."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from functools import lru_cache
from fractions import Fraction
from decimal import Decimal,localcontext
import json,time,threading,shutil,subprocess
import psutil

_samples={};_cpu={};_mutex=threading.Lock()
SPY=shutil.which('py-spy')

def small(path):
    try:
        path=Path(path)
        if path.stat().st_size>2*1024*1024:return {}
        return json.loads(path.read_text(encoding='utf8'))
    except (OSError,ValueError):return {}

def age(stamp):
    try:return max(0.,time.time()-datetime.fromisoformat(stamp).timestamp())
    except (TypeError,ValueError):return None

def duration(seconds):
    if seconds is None:return '미확인'
    m,s=divmod(max(0,int(seconds)),60);h,m=divmod(m,60)
    return f'{h}시간 {m:02d}분 {s:02d}초' if h else f'{m}분 {s:02d}초'

def phi_display(value):
    """Display the rational's value, preserving tiny nonzero values as such."""
    try:
        exact=Fraction(value)
        with localcontext() as context:
            context.prec=12
            number=Decimal(exact.numerator)/Decimal(exact.denominator)
            rendered=format(number,'.8g')
        if '.' in rendered and 'e' not in rendered.lower():rendered=rendered.rstrip('0').rstrip('.')
        return rendered
    except (ValueError,TypeError,ArithmeticError):return '미확인'


def classify(frames):
    names={f['name'] for f in frames};files=[f.get('filename','').replace('\\','/') for f in frames]
    if any(p.endswith('/v44/common.py') for p in files) and names&{'verify','sha','record'}:return 'Source·Permit 경로·SHA 무결성 검사'
    if names&{'verify_dual','corrected_certificate','exact_local_bound','_transpose_exact'}:return '후보 하한·유리수 독립 검산'
    if names&{'artificial_free_inclusion','inclusion_witness','compact_inverse'}:return '후보 반영 후 이전 해 보존·포함 검증'
    if names&{'materialize','assemble_original','native_block'}:return '선형 모델·행렬 구성'
    if any(p.endswith('/json/encoder.py') for p in files):return '검증 영수증·해시 JSON 생성'
    if names&{'primal_replay','verify_primal','verify_zero'}:return '원본 전체 제약 독립 재검산'
    if names&{'update_graph','batch_graphs','expanded_graph','build'}:return '후보 반영·모델 재구성'
    if names&{'native_optimize','optimize'}:return 'Native 최적화 호출'
    if 'full_pricing' in names:return '전체 후보 검증·후속 처리'
    return '후보·모델 준비 또는 검산'

def live_sample(pid,created):
    key=(pid,created);now=time.time()
    with _mutex:
        state=_samples.get(key,{})
        if now-state.get('attempt',0)<15:return state
        state=dict(state,attempt=now);_samples[key]=state
        if len(_samples)>32:_samples.pop(next(iter(_samples)))
    if not SPY:return dict(state,error='READ_ONLY_SAMPLER_UNAVAILABLE')
    try:
        process=psutil.Process(pid)
        if abs(process.create_time()-created)>.001:return dict(state,error='PID_IDENTITY_CHANGED')
        result=subprocess.run([SPY,'dump','--pid',str(pid),'--nonblocking','--json','--full-filenames'],
            capture_output=True,text=True,encoding='utf8',timeout=2,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        rows=json.loads(result.stdout);row=next((r for r in rows if r.get('active')),rows[0])
        frames=row['frames'];state.update(observed=time.time(),label=classify(frames),
            function=frames[0]['name'],file=frames[0]['filename'],line=frames[0]['line'],nonblocking=True,error=None)
    except (OSError,ValueError,KeyError,IndexError,subprocess.TimeoutExpired,psutil.Error) as error:state['error']=type(error).__name__
    with _mutex:_samples[key]=state
    return state

def cpu_activity(pid,created):
    try:
        p=psutil.Process(pid)
        if abs(p.create_time()-created)>.001:return None
        now=time.monotonic();cpu=sum(p.cpu_times()[:2]);key=(pid,created)
        with _mutex:
            old=_cpu.get(key)
            if old is None:_cpu[key]=(now,cpu,None);return None
            if now-old[0]>=1:
                percent=max(0.,100*(cpu-old[1])/(now-old[0]));_cpu[key]=(now,cpu,percent)
                return percent
            return old[2]
    except psutil.Error:return None

@lru_cache(maxsize=32)
def pricing_summary(path,size,mtime):
    if size>64*1024*1024:return {}
    value=json.loads(Path(path).read_text(encoding='utf8'))
    return {k:value.get(k) for k in ['PASS','classes','negative_blocks','no_negative_omitted_block_certified','pricing_wall_seconds']}

def details(folder,worker,ledger,native,alive):
    folder=Path(folder);out=folder/'OUTPUT';start=small(folder/'START.json');result=small(folder/'RESULT.json')
    prep=small(out/'A_PREPARE_RECEIPT.json');zero=small(out/'PHASE_I_ZERO_CERTIFICATE.json')
    phase=small(out/'PHASE_I_TRACE.json').get('trajectory',[]);p1=small(out/'P1_TRACE.json').get('trajectory',[])
    lp=small(out/'P1_RESULT.json');integer=small(out/'INTEGER_RESULT.json')
    full={};last=out/'P1_TRACE.json';round_dir=None
    if p1:
        round_dir=out/'P1'/f'S{len(p1)-1}';price=round_dir/'PRICE/FULL_PRICING_RESULT.json'
        try:
            stat=price.stat();full=pricing_summary(str(price),stat.st_size,stat.st_mtime_ns)
        except (OSError,ValueError):pass
    identity=small(round_dir/'MODEL_IDENTITY.json') if round_dir else {}
    if not identity and phase:identity=small(out/'PHASE_I'/f'S{phase[-1]["solve"]}/MODEL_IDENTITY.json')
    elapsed=age(start.get('UTC'))
    if ledger.get('checkpoint_resume'):
        carried=float(ledger.get('wall_seconds',0.))+(age(ledger.get('UTC')) or 0.)
        elapsed=max(elapsed or 0.,carried)
    used=native['Native_completed_seconds']+(native.get('Native_current_call_seconds') or 0.)
    nonnative=None if elapsed is None else max(0.,elapsed-used)
    steps=[('입력·모델',bool(prep.get('PASS'))),('인공변수 0',bool(zero.get('PASS'))),
           ('P1 전체 후보 검증',bool(lp.get('P1_LP_closure'))),('정수해·Gap',bool(integer.get('P1_accepted'))),('최종 동결',bool(result.get('PASS')))]
    active=next((i for i,(_,ok) in enumerate(steps) if not ok),len(steps)-1)
    sample={};activity=None
    if alive:
        try:
            created=psutil.Process(worker['pid']).create_time()
            process_start=small(folder.parent/'START.json')
            if abs(created-process_start['process_created'])<.001:
                sample=live_sample(worker['pid'],created);activity=cpu_activity(worker['pid'],created)
        except (psutil.Error,KeyError,TypeError):pass
    valid_sample=sample.get('observed') is not None and time.time()-sample['observed']<=45
    component=(ledger.get('inflight') or {}).get('component')
    title=sample['label'] if valid_sample else {
        'PHASE_I':'인공변수·가능해 구성','ORIGINAL_P1':'P1 목적함수 최적화',
        'LOCAL_PRICING':'개별 후보 최적화','INTEGER_CONTROL':'정수해 최적화','NODE_LP':'정수 탐색 하한 계산'}.get(component,
        'P1 후보 반영·모델 갱신/검산 (기록 기준)' if p1 else 'Phase I 후보 반영·검산 (기록 기준)' if phase else '입력·모델 준비')
    lines=[f'현재 작업: {title}'+(f' · {int(time.time()-sample["observed"])}초 전 표본' if valid_sample else ''),
           f'경과 {duration(elapsed)} = Native {duration(used)} + 모델·후보·검산 등 {duration(nonnative)}',
           '시간 구분: Native 호출 사이의 준비·검산도 전체 경과에 포함됩니다.']
    lines.append(f'Native 완료 누적 {native["Native_completed_seconds"]:.1f}초'+
        (f' + 현재 호출 약 {native["Native_current_call_seconds"]:.0f}초 (Solver 로그 기준)' if native.get('Native_current_call_seconds') is not None else ' · 현재 호출 Runtime 로그 대기' if native.get('Native_inflight') else ' · 현재 호출 없음'))
    if ledger.get('checkpoint_resume'):
        lines.append(f'체크포인트 재개: 기존 Native {ledger.get("inherited_Native_seconds",0.):.1f}초 승계 · 총 예산 {ledger.get("Native_ceiling_seconds",0.):.0f}초 유지 · 경과는 이전 실행 포함')
    initial=next((c for c in ledger.get('costs',[]) if c.get('label')=='A_complete_model_build'),None)
    if initial:lines.append(f'최초 모델 구성: {duration(initial["wall_seconds"])}')
    if zero.get('PASS'):
        try:phi=float(Fraction(zero['zero']['replayed_phi']));lines.append(f'인공변수: 0 검증 PASS · 독립 재생 Φ={phi:.3g} · 정수해 인증은 별도')
        except (KeyError,ValueError,ZeroDivisionError):lines.append('인공변수: 0 검증 PASS')
    elif phase:
        value=phase[-1].get('exact_Phi',phase[-1].get('Phi'))
        lines.append(f'인공변수: 마지막 Φ≈{phi_display(value)} · 원본 전체 0 인증 대기')
    if full:
        lines.append(f'직전 P1 전체 후보 검사: {full.get("classes","미확인")}개 작업군 완료 · 개선 가능 블록 {full.get("negative_blocks","미확인")}개')
        lines.append('다음: 후보 반영·포함 검증 → 다음 P1 계산' if not full.get('no_negative_omitted_block_certified') else '다음: P1 종료 검증 → 정수해·독립 Gap 인증')
    lines.append(f'반복 기록: Phase I {len(phase)}회 · P1 전체 후보 검사 {len(p1)}회 · Native 완료 {len(ledger.get("calls",[]))}회')
    if identity:lines.append(f'마지막 원본 P1 모델: {identity.get("rows",0):,}행 · {identity.get("cols",0):,}변수 · {identity.get("nnz",0):,}개 계수')
    try:
        if not last.exists():last=out/'PHASE_I_TRACE.json'
        if last.exists():lines.append(f'최근 단계 완료 기록: {datetime.fromtimestamp(last.stat().st_mtime,timezone(timedelta(hours=9))).strftime("%H:%M:%S")} KST · {duration(time.time()-last.stat().st_mtime)} 전')
    except OSError:pass
    lines.append(f'CPU 활동: {activity:.0f}% (100%=1코어)' if activity is not None else 'CPU 활동: 다음 관측 대기')
    if not native.get('Native_inflight'):lines.append('지금은 Solver 호출 사이의 작업이므로 Native 누적시간은 증가하지 않습니다.')
    return dict(title=title,lines=lines,stage_elapsed_seconds=elapsed,Native_seconds=used,
        other_wall_seconds=nonnative,initial_model_seconds=initial['wall_seconds'] if initial else None,
        phase_I_zero_PASS=bool(zero.get('PASS')),phase_I_solves=len(phase),P1_pricing_rounds=len(p1),
        last_pricing=full,model_identity={k:identity.get(k) for k in ['rows','cols','nnz']},
        cpu_percent=activity,nonblocking_stack_sample=sample,completion_percentage=None,
        steps=[dict(label=label,state='pass' if ok else 'active' if i==active else '',percent=None) for i,(label,ok) in enumerate(steps)])
