"""Measured four-day Korean report; no optimizer calls."""
from pathlib import Path
from collections import defaultdict
from time import time
import subprocess
from v42_pr134_b1.common import read,atomic,record,sha,table
from .policy import OUT,OLD,DAYS,ROOT

def maybe(p):return read(p) if p.exists() else {}
def run():
    results=[];lines=['# A-stage 수락 및 4일 검증','',
        'GLOBAL_GAP_ACCEPTANCE는 전체 영역 bound와 원본 physical replay를 바탕으로 gap ≤0.5%를 수락한다. 정확한 정수 최적값 증명과 Native OPTIMAL 상태를 대체하지 않는다.', '',
        'PR134도 shift 727/LB725(0.275103%), prestart 231/LB230(0.432900%)를 수락했다. PR134 freeze는 새 May19 인스턴스에 사용하지 않았다.', '',
        '기존 A1 authoritative 계약은 하루 누적 native 3,600초이다. 새 continuation은 4일 합계 14,400초 native와 별도의 28,800초 wall guard를 갖는다. 30분 실용성 수락은 새 end-to-end wall ≤1,800초와 scientific acceptance를 모두 요구한다. 과거 PR180의 8시간 영수증은 변경하지 않았다.', '',
        '| 날짜 | Phi / Phase-I | P1 LB / UB / gap | migration LB / UB / gap | shift LB / UB / gap | prestart LB / UB / gap | physical | A1_ACCEPTED | scientific | 30분 |',
        '|---|---|---|---|---|---|---|---|---|---|']
    def textgap(c):
        if not c:return 'NOT_RUN'
        L=c.get('LB',c.get('valid_lower_bound',c.get('valid_LB')));U=c.get('UB',c.get('incumbent_integer',c.get('value')))
        gap=c.get('gap');return f'{L} / {U} / '+('N/A' if gap is None else f'{gap*100:.10g}%')
    for day in DAYS:
        f=OUT/day;r=maybe(f/'RESULT.json');accepted=bool(r.get('A1_accepted'))
        if day==DAYS[0]:
            phi=maybe(OLD/'FROZEN64_RESULT.json');p1=maybe(OLD/'VALIDATED_INTEGER_INCUMBENT.json')
            mig=maybe(OLD/'P2_MIGRATION_PROBE_RESULT.json');mg=dict(LB=0,UB=0,gap=0) if mig.get('accepted') else {}
            shift=maybe(f/'SHIFT_GLOBAL_GAP_ACCEPTANCE.json')
        else:
            phi=maybe(f/'PHASE_I_ZERO_CERTIFICATE.json');p1=maybe(f/'INTEGER_RESULT.json').get('incumbent',{})
            mg=maybe(f/'P2/MIGRATION_CERTIFICATE.json')
            if mg.get('PASS'):mg=dict(LB=0,UB=0,gap=0)
            shift=maybe(f/'P2/SHIFT_MAGNITUDE/GLOBAL_GAP_ACCEPTANCE.json')
        pre=maybe(f/'P2/PRESTART_RELOCATION/GLOBAL_GAP_ACCEPTANCE.json');physical=maybe(f/'FINAL_PHYSICAL_REPLAY.json')
        Phi=phi.get('certified_Phi_after',phi.get('Phi'));phipass=phi.get('certified_zero',phi.get('PASS',False))
        status='SCIENTIFIC_ACCEPTED' if accepted else 'INCONCLUSIVE' if r else 'NOT_RUN'
        practical=bool(r.get('practical_runtime_accepted'));runtime=r.get('native_seconds');wall=r.get('wall_seconds')
        lines.append(f"| {day} | {Phi} / {'PASS' if phipass else 'INCONCLUSIVE'} | {textgap(p1)} | {textgap(mg)} | {textgap(shift)} | {textgap(pre)} | {'PASS' if physical.get('PASS') else 'NOT_PASS/NOT_RUN'} | {accepted} | {status} | {'PASS' if practical else 'FAIL'} |")
        row=dict(day=day,Phi=Phi,Phase_I_PASS=phipass,P1=p1,migration=mg,shift=shift,prestart=pre,
            physical_PASS=physical.get('PASS',False),A1_ACCEPTED=accepted,scientific_status=status,
            practical_runtime_status='PRACTICAL_RUNTIME_ACCEPTED' if practical else 'FAILED',
            total_native_Runtime=runtime,total_wall_seconds=wall,peak_RSS_bytes=r.get('peak_RSS_bytes'),
            failure_reason=r.get('failure_reason',r.get('practical_failure_reason','NOT_RUN_PENDING_MAY19_GATE' if not r else None)))
        results.append(row)
    lines+=['','## 측정과 실패 원인','']
    callrows=[]
    for row in results:
        day=row['day'];f=OUT/day;r=maybe(f/'RESULT.json');calls=maybe(f/'NATIVE_CALLS.json').get('calls',[])
        grouped=defaultdict(float)
        for c in calls:
            grouped[c['component']]+=c.get('native_seconds') or 0
            identity=maybe(Path(c['model_identity']['path']))
            callrows.append(dict(day=day,component=c['component'],Runtime=c.get('native_seconds'),Work=c.get('Work'),
                rows=identity.get('rows'),cols=identity.get('cols'),nnz=identity.get('nnz'),status=c.get('status'),
                Nodes=c.get('NodeCount'),peak_RSS=c.get('peak_RSS_bytes'),folder=c['folder'],
                factor_nnz=c.get('max_factor_nnz'),factor_memory_GB=c.get('max_factor_memory_GB')))
        initial=maybe(f/'INITIAL_VERIFICATION.json');pricing=sum(maybe(p).get('pricing_wall_seconds',0) for p in (f/'P1').rglob('FULL_PRICING_RESULT.json')) if (f/'P1').exists() else None
        stages={name:sum(c.get('native_seconds') or 0 for c in calls if name.upper() in c['folder']) for name in ('migration','shift_magnitude','prestart_relocation')}
        build=initial.get('build_seconds');compile=sum(c.get('build_and_snapshot_seconds') or 0 for c in calls)
        lines += [f"### {day}",'',f"Native Runtime {row['total_native_Runtime']} s; wall {row['total_wall_seconds']} s; peak RSS {row['peak_RSS_bytes']} bytes; native calls {len(calls)}.",'',
            f"Initial model build {build} s; native compile/archive {compile} s; Phase-I native {grouped['PHASE_I']} s; local pricing native {grouped['LOCAL_PRICING']} s; full pricing/closure wall {pricing} s; P1 LP {grouped['ORIGINAL_P1']} s; original P1 integer {grouped['INTEGER_CONTROL']} s; ordered P2 native {stages}.",'',
            f"미수락/실용성 원인: {row['failure_reason']}",'']
        if day==DAYS[0]:
            lines += ['May19는 기존 Phi/P1/migration/shift 증거를 독립 감사하고 prestart만 새 native 실행했다. 새 prefix 실행은 fresh end-to-end 측정이 아니다. 과거 PR180 전체 native 22,085.305초(202회)를 재사용 증거와 구분하며 30분 production PASS를 주장하지 않는다.','']
    preserved=maybe(OUT/'HISTORICAL_PR180_BYTE_PRESERVATION_START.json')
    if preserved:
        changed=[p for p,h in preserved['files'].items() if not Path(p).exists() or sha(p)!=h]
        atomic(OUT/'HISTORICAL_PR180_BYTE_PRESERVATION_FINAL.json',dict(PASS=not changed,changed=changed,files=len(preserved['files'])))
        if changed:raise ValueError('HISTORICAL_PR180_ARTIFACT_BYTES_CHANGED')
    lines+=['## 최종 판정','',f"Scientific accepted: {sum(r['A1_ACCEPTED'] for r in results)}/4. Practical runtime accepted: {sum(r['practical_runtime_status']=='PRACTICAL_RUNTIME_ACCEPTED' for r in results)}/4.",'',
        '범위: A-stage 네 날짜만. M1/A2/M2/Planning/Actual/Fresh AC는 실행하지 않았다. Threads=1, 한 native process, 날짜별 후보·입력 identity와 전체 row/column closure guard를 적용했다.','',
        '변경: 별도 global gap 수락 계약, May19 shift bound 독립 재구성, replay-PASS MIP Start, 원래 prestart 목적 실행, 날짜 순서 및 scope guards, 새 누적 budget/source freeze. exact-optimality certificate 정의와 물리·계수·목적·tolerance는 유지했다.','']
    for day in DAYS:
        a=maybe(OUT/day/'A1_RESULT.json')
        if a.get('frozen_A1'):lines.append(f"Frozen {day}: `{a['frozen_A1']['sha256']}`")
    atomic(OUT/'FOURDAY_FINAL_RESULT.json',dict(days=results,accepted_days=sum(r['A1_ACCEPTED'] for r in results),
        practical_accepted_days=sum(r['practical_runtime_status']=='PRACTICAL_RUNTIME_ACCEPTED' for r in results),
        immutable_budget=record(OUT/'CONTINUATION_BUDGET.json'),actual_new_native_seconds=sum(c['Runtime'] or 0 for c in callrows),
        total_continuation_wall_seconds=time()-read(OUT/'CONTINUATION_BUDGET.json')['start_unix']))
    table(OUT/'ALL_NEW_NATIVE_SOLVES.csv',callrows,['day','component','Runtime','Work','rows','cols','nnz','status','Nodes','peak_RSS','factor_nnz','factor_memory_GB','folder'])
    (OUT/'REPORT_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
    print('FOURDAY_REPORT',sum(r['A1_ACCEPTED'] for r in results),sum(c['Runtime'] or 0 for c in callrows),flush=True)
if __name__=='__main__':run()
