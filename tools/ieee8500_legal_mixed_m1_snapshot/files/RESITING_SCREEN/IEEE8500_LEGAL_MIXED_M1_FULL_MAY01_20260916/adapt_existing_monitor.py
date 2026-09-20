"""Retarget the existing IEEE8500 monitor in place; retain its UI/layout."""
from pathlib import Path
import shutil
H=Path(__file__).absolute().parent
M=H.parents[1]/'monitoring/IEEE8500_MAY01_MESS6_B2B3_20260913'
backup=H/'monitor_before_current_run';backup.mkdir(exist_ok=True)
for name in ('server.py','index.html','SERVER.json'):
 if not(backup/name).exists():shutil.copyfile(M/name,backup/name)
p=M/'server.py';s=p.read_text(encoding='utf-8')
s=s.replace("RUN=W/'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'","RUN=W/'RESITING_SCREEN/IEEE8500_LEGAL_MIXED_M1_FULL_MAY01_20260916'")
start=s.index('def status():');end=s.index('class Handler',start)
s=s[:start]+'''def status():
 sup=read(RUN/'SUPERVISOR_STATUS.json') or {};live=read(RUN/'STATUS.json') or {};stage=sup.get('stage','');now=time.time()
 role='B3_A1' if stage=='B3_A1' else 'B1'
 clk=read(RUN/'SEARCH_CLOCK.json') or {}
 if stage not in ('B1','B3_A1') or clk.get('start_unix',0)<sup.get('updated_unix',0):clk={}
 elapsed=max(0,min(14400,now-clk['start_unix'])) if clk else 0
 inc=read(RUN/'DEADLINE_INCUMBENT.json') or {}
 if inc.get('published_elapsed') is None:inc={}
 checks=[]
 for p in (RUN/role/'timed_checkpoints').glob('*.json'):
  r=read(p)
  if r:checks.append(dict(label=p.stem,seconds=r.get('target_seconds'),P1=r.get('P1')))
 checks.sort(key=lambda r:r['seconds'] or 0)
 rows=[]
 paths={'B0':('B0_REPLAY/AC_VALIDATION.json','B0/Fresh/AC_VALIDATION.json'),'B1':('B1/final_exact/AC_VALIDATION.json','B1/Fresh/AC_VALIDATION.json'),'B2':('B2/final_exact/AC_VALIDATION.json','B2/Fresh/AC_VALIDATION.json'),'B3':('B3/final_exact/AC_VALIDATION.json','B3/independent_clean_exact/AC_VALIDATION.json')}
 for policy,(dp,fp) in paths.items():
  da=read(RUN/dp) or {};fresh=read(RUN/fp) or {}
  if policy=='B2' and da.get('status')=='FAIL':da=read(RUN/'B2/physical_closure/accepted_clean_exact/AC_VALIDATION.json') or da
  metrics=fresh.get('metrics',{});slots=fresh.get('slots',[]);witness=max(slots,key=lambda r:r['max_phase_line_loading_pu']) if slots else {}
  rows.append(dict(policy=policy,fleet='OFF' if policy in ('B0','B1') else '6대',DA=da.get('metrics',{}).get('max_phase_line_loading_pu'),Fresh=metrics.get('max_phase_line_loading_pu'),Vmin=metrics.get('Vmin_pu'),Vmax=metrics.get('Vmax_pu'),txI=metrics.get('max_transformer_phase_current_pu'),txS=metrics.get('max_transformer_winding_kva_pu'),critical_slot=witness.get('slot'),critical_line=witness.get('line_witness'),feasible=fresh.get('status')=='PASS' if fresh else None))
 final=read(RUN/'FULL_RESULT.json') or {}
 done=[rows[0]['feasible'] is True,*[(RUN/r/'COMPLETE.json').exists() for r in ('B1','B2','B3_M1','B3_A1','B3')],bool(final)]
 labels=['B0 · 96-slot / Fresh','B1 · AIDC 4시간','B2 · route / PQ','B3 · M1 route / PQ','B3 · A1 4시간','B3 · MF / Fresh','최종 결과 집계']
 current={'B1':1,'B2':2,'B3_M1':3,'B3_A1':4,'B3_MF':5}.get(stage,0 if stage=='ELECTRICAL_PREPARATION' else 6)
 if final:current=7
 bounds=len(list((RUN/(role+'_electrical_rows')).glob('bounds_*.npz')));active=len(list((RUN/(role+'_electrical_rows')).glob('active_data_*.npz')))
 failure=sup if sup.get('status')=='FAILED' else None
 fleet=read(RUN/'FLEET_AUTHORITY.json') or {}
 return dict(now=now,run=str(RUN),supervisor=sup,live=live,worker=process(sup.get('worker_pid')),failure=failure,clock=clk,clock_role=role,elapsed=elapsed,incumbent=inc,checkpoints=checks,results=rows,steps=[dict(name=n,state='complete' if done[i] else 'running' if i==current else 'pending') for i,n in enumerate(labels)],current=current,complete=bool(final),authorization=dict(initial=fleet.get('initial_locations',{})),preparation=dict(bounds_slots=bounds,active_slots=active),system=dict(available_ram_gib=psutil.virtual_memory().available/2**30),spatial_audit='SUPERSEDED_NONBLOCKING_DIAGNOSTIC',transport_preserved=(read(RUN/'INPUT_AUTHORITY_AUDIT.json') or {}).get('status')=='PASS',final=final,Actual=False)
''' +s[end:]
p.write_text(s,encoding='utf-8')
p=M/'index.html';s=p.read_text(encoding='utf-8')
changes={
'May01 · 6 MESS · B2/B3 모니터':'IEEE8500 · legal_mixed_M1 · May-1 full validation',
'6대 MESS · B2 / B3 실행 모니터':'legal_mixed_M1 · May-1 full validation',
'AIDC 2× · 2,624 GPU · αBG 0.50 · 기존 12-host mapping':'s_DC = 1.00 · s_MESS = 1.00 · αBG 0.574 · αPV 0.50 · 1 worker × 4 threads',
'repeat(6,1fr)':'repeat(7,1fr)',
'Actual slot 진행':'현재 단계 진행',
'<small>B3 A1 · 연속 wall-clock</small>':'<small id="clocklabel">AIDC · 연속 wall-clock</small>',
'<h2>B3 A1 · P1–P5 단계</h2>':'<h2 id="lexlabel">AIDC · P1–P5 단계</h2>',
'<th>Actual exact</th><th>Actual AC</th><th>QSAFE 개입</th>':'<th>Fresh exact</th><th>Fresh AC</th><th>Vmin / Vmax</th><th>Tx I / kVA (pu)</th><th>Critical slot</th>',
'부하율은 %로 표시합니다. B0/B1은 보존된 완료 결과, B2/B3는 이번 6대 실행 결과입니다. —는 아직 결과가 생성되지 않았다는 뜻입니다.':'부하율은 %로 표시합니다. 모든 정책은 이번 infrastructure의 새 96-slot 결과입니다. —는 아직 완료 결과가 없음을 뜻합니다. Actual은 실행하지 않습니다.',
'기존 24개 service location 유지':'선정 6개 STA PCC + 기존 18개 MESS PCC 상속',
'B3: 완료된 B1 A0 재사용 → M1 → A1 → MF<br>각 정책 완료 후 Actual / QSAFE / 독립 AC 검증':'B3: 이번 full B1 → M1 → A1 → MF<br>Fresh exact AC까지 · Actual 제외',
'<h2>A1 저장된 P1 checkpoint</h2>':'<h2>AIDC 저장된 P1 checkpoint</h2>'}
for a,b in changes.items():s=s.replace(a,b)
start=s.index('function render(d)');end=s.index('async function refresh()',start)
s=s[:start]+r'''function render(d){
 const failed=!!d.failure,done=d.complete,p=d.live.MESS_progress||{},role=d.clock_role;
 $('health').textContent=failed?'실행 오류':done?'DA / Fresh 완료':d.worker.alive?'● 실행 중':'프로세스 전환 / 확인 중';
 $('health').style.color=failed?'var(--red)':'var(--green)';
 $('error').hidden=!failed;$('error').textContent=failed?d.failure.error||d.failure.status:'';
 $('phase').textContent=failed?'오류 · 확인 필요':done?'전체 DA / Fresh 완료':d.steps[d.current]?.name||'준비 중';
 $('activity').textContent=d.live.stage||d.supervisor.stage||'—';
 $('progresslabel').textContent=p.mess_index?'MESS route/PQ 후보 진행':'현재 단계 진행';
 if(p.mess_index){$('candidate').textContent='MESS'+String(p.mess_index).padStart(2,'0')+' / 06';$('candidatebar').value=p.candidate_total?p.candidate_done/p.candidate_total:0;$('candidateinfo').textContent=p.candidate_total?`${p.search_level||p.event} · ${p.candidate_done} / ${p.candidate_total} 후보`:'production route/PQ 준비';}
 else if(d.clock.start_unix){$('candidate').textContent=(100*d.elapsed/14400).toFixed(1)+'%';$('candidatebar').value=d.elapsed/14400;$('candidateinfo').textContent='P1–P5 production search · '+(d.live.neighborhood_solve_count??0)+'회 neighborhood solve';}
 else{const n=d.preparation.bounds_slots+d.preparation.active_slots;$('candidate').textContent=done?'완료':n?n+' / 192':'준비 중';$('candidatebar').value=done?1:n/192;$('candidateinfo').textContent=n?'96-slot electrical bounds / certified rows':'모델·전기계수·물리 검증 준비';}
 $('steps').innerHTML=d.steps.map(s=>`<div class="step ${s.state}">${s.name}<br>${s.state==='complete'?'완료':s.state==='running'?(failed?'오류':'진행 중'):'대기'}</div>`).join('');
 $('clocklabel').textContent=role+' · 연속 wall-clock';$('lexlabel').textContent=role+' · P1–P5 단계';
 $('clock').textContent=d.clock.start_unix?dur(d.elapsed)+' / 04:00:00':'탐색 시작 전';
 $('clockdetail').textContent=d.clock.start_unix?'잔여 '+dur(14400-d.elapsed)+' · clock pause 없음':'모델·seed 준비 완료 후 search clock 시작';
 $('a1progress').value=d.elapsed;$('a1dates').textContent=d.clock.start_unix?'종료 예정 '+date(d.clock.deadline_unix):'Search-loop 대기';
 $('incumbent').textContent=`Planning P1 ${num(d.live.P1??d.incumbent.P1)} · incumbent 갱신 ${d.live.incumbent_updates??d.incumbent.incumbent_updates??'—'}`;
 $('resources').textContent=`Worker PID ${d.worker.pid||'—'} · 1 worker × 4 threads${d.worker.rss_gib!=null?' · '+d.worker.rss_gib.toFixed(2)+' GiB':''} · 가용 RAM ${d.system.available_ram_gib.toFixed(1)} GiB`;
 $('exception').hidden=false;$('exception').textContent='Transport authority '+(d.transport_preserved?'PASS':'확인 중')+' · 기존 spatial-correlation audit: SUPERSEDED_NONBLOCKING_DIAGNOSTIC · production / electrical freeze 비차단';
 $('results').innerHTML=d.results.map(r=>`<tr><td>${r.policy}</td><td>${r.fleet}</td><td>${pct(r.DA)}</td><td>${pct(r.Fresh)}</td><td>${r.feasible==null?'—':r.feasible?'PASS':'FAIL'}</td><td>${num(r.Vmin,6)} / ${num(r.Vmax,6)}</td><td>${num(r.txI,6)} / ${num(r.txS,6)}</td><td title="${r.critical_line||''}">${r.critical_slot??'—'}</td></tr>`).join('');
 $('delta').textContent=done?'Strict ordering: '+(d.final.strict_ordering?'PASS':'미충족')+' · B3 < 0.90: '+(d.final.B3_below_090?'PASS':'미충족')+' · electrical freeze 후보: '+(d.final.electrical_freeze_candidate?'YES':'NO'):'B0 > B1 > B2 > B3 및 B3 < 0.90: full 결과 완료 후 판정';
 $('fleet').innerHTML=Object.entries(d.authorization.initial||{}).map(([m,s])=>`<div class="vehicle">${m}<b>${s}</b></div>`).join('');
 $('checkpoints').innerHTML=d.checkpoints.length?d.checkpoints.map(c=>`<tr><td>${c.label}</td><td>${dur(c.seconds||0)}</td><td>${num(c.P1)}</td></tr>`).join(''):'<tr><td colspan="3">저장된 checkpoint 없음</td></tr>';
 $('updated').textContent='화면 갱신 '+date(d.now)+' · worker 기록 '+(d.live.updated_unix?date(d.live.updated_unix):'준비 중');$('run').textContent=d.run;
}
''' +s[end:]
p.write_text(s,encoding='utf-8')
print('EXISTING_MONITOR_RETARGETED',M)
