'use strict';
const $=id=>document.getElementById(id), finite=x=>typeof x==='number'&&Number.isFinite(x), fmt=(x,n=0)=>finite(x)?x.toLocaleString('ko-KR',{minimumFractionDigits:n,maximumFractionDigits:n}):'—';
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const duration=x=>!finite(x)?'—':`${String(Math.floor(Math.max(0,x)/3600)).padStart(2,'0')}:${String(Math.floor(Math.max(0,x)%3600/60)).padStart(2,'0')}:${String(Math.floor(Math.max(0,x)%60)).padStart(2,'0')}`;
const priority={PRIMARY_MIN_RHO:0,V41_SECONDARY_MIN_MEAN_H4_SHORTFALL:1,SECONDARY_MIN_MIGRATIONS:2,TERTIARY_COMPLETE_REFERENCE_DEVIATION:3,QUATERNARY_STABLE_TIE:4};
const names=['최대 선로 부하율','4시간 예비 GPU 부족량','Migration 횟수','기준 스케줄 이탈','원래 cohort tie-break'];
const units=['pu · 낮을수록 좋음','평균 GPU·h','건','GPU·slot','cohort 순위 점수'];
let data=null,selected='B1',chosen=false,lastFetch=0,acSelected='B2';
document.querySelectorAll('[data-ac]').forEach(b=>b.addEventListener('click',()=>{acSelected=b.dataset.ac;if(data)render(data)}));
document.querySelectorAll('[data-policy]').forEach(b=>b.addEventListener('click',()=>{selected=b.dataset.policy;chosen=true;if(data)renderHistory(data)}));
function clock(d){
 const s=d.status,active=['B1','B3_A1'].includes(d.role)&&s.search_started;
 let elapsed=active?s.search_elapsed_seconds:null;
 if(active&&d.worker&&!s.search_stopped&&finite(s.search_started_unix))elapsed=Math.min(14400,Date.now()/1000-s.search_started_unix);
 $('elapsed').textContent=duration(elapsed);$('remaining').textContent=duration(finite(elapsed)?14400-elapsed:null);$('progress').value=elapsed||0;
 $('percent').textContent=finite(elapsed)?`${fmt(elapsed/14400*100,1)}% / 4시간`:'4시간 탐색 시계 대기';
 $('deadline').textContent=active&&s.search_started_unix?'탐색 종료 예정 '+new Date((s.search_started_unix+14400)*1000).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}):'단계 완료 후 다음 작업으로 이동';
 $('fresh').textContent=lastFetch?`데이터 ${Math.max(0,Math.floor(Date.now()/1000-d.observed_unix))}초 전 · PID ${s.pid||'—'}`:'연결 확인 중';
 $('elapsedLabel').textContent=active?'A1 탐색 경과':'B3 누적 경과';$('remainingLabel').textContent=active?'남은 탐색 시간':'A1 탐색 예산';
 $('progress').max=14400;
 if(!active){
   $('elapsed').textContent=duration(d.campaign_started_unix?Date.now()/1000-d.campaign_started_unix:null);
   $('remaining').textContent='04:00:00';
   $('progress').max=4;$('progress').value=d.latest_beam?.stage||0;
   $('percent').textContent=d.role==='B3_M1'?`MESS ${d.latest_beam?.stage||0}/4대 단계 완료 · 시간 진행률 아님`:'A1 탐색 시계 대기';
   $('deadline').textContent='A1 진입 후 4시간 시작';
 }
 $('budgetNote').textContent=active?'A1 continuous search 4시간 · 30분 / 1시간 / 2시간 / 4시간 checkpoint':'M1은 경로·P/Q 탐색 단계입니다. A1의 4시간 예산에는 M1 시간이 포함되지 않습니다.';
}
function renderComparison(d){
 $('policyCards').innerHTML=(d.comparison||[]).map(r=>{
  const done=r.status==='FINAL',ac=r.AC?.max_phase_line_loading_pu;
  return `<article class="policy-card ${done?'final':'pending'}"><div class="policy-head"><b>${r.policy}</b><span class="badge ${done?'':r.status==='FAILED'?'bad':'wait'}">${done?r.policy==='B2'?'복구 후 승인':'최종 승인':r.status==='FAILED'?'중단 · 미확정':r.status==='PENDING'?'대기 · 미확정':'진행 중 · 미확정'}</span></div><p>${esc(r.description)}</p><small>최종 모델 목적함수 P1</small><strong class="policy-value">${done?fmt(r.P1,8):'미확정'}</strong><div class="ac-row"><span>Exact AC 최대 선로</span><b>${fmt(ac,8)}</b></div><div class="ac-row"><span>B0 대비 AC 감소율</span><b>${finite(r.AC_change_percent)?fmt(r.AC_change_percent,4)+'%':'—'}</b></div>${!done?`<div class="live-value">현재 ${r.live_kind==='partial_beam'?'부분 beam':r.live_kind==='A0_reference'?'A0 기준':'중간 해'} P1 <b>${fmt(r.live_P1,8)}</b><small>${r.live_kind==='partial_beam'?'부분 fleet · 최종 AC 미검증':'B3 최종값으로 사용하지 않음'}</small></div>`:''}</article>`;
 }).join('');
 $('policyVectors').innerHTML=(d.comparison||[]).map(r=>`<tr><th>${r.policy}</th>${[0,1,2,3,4].map((i)=>`<td>${fmt(r.vector?.[i],i===0?8:i===1?3:0)}</td>`).join('')}</tr>`).join('');
}
function render(d){
 const s=d.status,active=['B1','B3_A1'].includes(d.role),key=d.live.stage||s.stage?.split(':')[1],idx=priority[key];
 if(!chosen&&d.role==='B3_A1')selected='B3_A1';
 const failed=s.status==='FAIL_CLOSE'||!!d.failure,alive=!!d.worker;
 renderComparison(d);
 $('health').textContent=failed?'실행 중단':s.status==='COMPLETE'?'전체 완료':alive?'실행 중':'worker 확인 필요';$('health').className='badge '+(failed?'bad':!alive&&s.status!=='COMPLETE'?'wait':'');
 $('alert').hidden=!failed&&!d.monitor_error&&alive;
 $('alert').textContent=failed?'실행이 중단되었습니다. '+(d.failure?.error||s.error||'실패 기록을 확인하세요.'):(d.monitor_error?'모니터 데이터 갱신 오류: '+d.monitor_error:!alive&&s.status!=='COMPLETE'?'실행 프로세스가 확인되지 않습니다. 마지막으로 저장된 상태를 표시합니다.':'');
 if(s.status==='COMPLETE')$('alert').hidden=true;
 const flow=[['B0','Reference · MESS OFF'],['B1','AIDC 최적화'],['B2','MESS 최적화'],['B3_M1','B3 · MESS 경로 탐색'],['B3_A1','B3 · AIDC 재최적화'],['B3_MF','B3 · 고정 경로 P/Q']];
 $('pipeline').innerHTML=flow.map(([r,label])=>{let done=r==='B3_MF'?d.policies.B3?.status==='PASS':d.policies[r]?.status==='PASS';let current=d.role===r;return `<div class="step ${done?'done':current?'active':''}"><b>${r.replace('B3_','B3 ')} ${done?'✓':''}</b><small>${esc(label)} · ${done?'완료':current?(failed?'중단':'진행 중'):'대기'}</small></div>`}).join('');
 $('policyTag').textContent=(d.role||'—').replace('B3_','B3 ');
 $('stage').textContent=finite(idx)?`${['P1','P2','P3','P4','P5'][idx]} · ${names[idx]} 최소화`:key==='PHYSICS_RANKING'?'전기 영향 기반 ranking 준비':key==='MODEL_BUILD'?'공동 최적화 모델 구성':d.role==='B3_M1'||d.role==='B2'?'MESS 경로·충방전 탐색':d.role==='B3_MF'?'고정 경로 P/Q recourse':s.status==='COMPLETE'?'전체 실험 완료':(s.stage||'실행 상태 확인');
 $('stageHint').textContent=finite(idx)?(idx===0?'가장 우선하는 목표 P1을 개선하고 있습니다.':`P1${idx>1?'–P'+idx:''} lock을 유지하며 다음 목표를 탐색합니다.`):'승인된 고정 운전점과 원래 모델을 사용합니다.';
 const mp=s.MESS_progress||{};
 $('fleetProgress').innerHTML=d.role==='B3_M1'?[1,2,3,4].map(n=>`<span class="${n<=(d.latest_beam?.stage||0)?'done':n===mp.mess_index?'active':''}">MESS ${n<10?'0':''}${n} · ${n<=(d.latest_beam?.stage||0)?'완료':n===mp.mess_index?'탐색 중':'대기'}</span>`).join(''):'';
 if(d.role==='B3_M1'){
   $('stage').textContent=`M1 · MESS ${mp.mess_index||1}/4 경로·P/Q 탐색`;
   $('stageHint').textContent=`${mp.event==='FULL_MILP'?'Full MILP 계산 중':mp.event||'탐색 준비'} · parent ${mp.parent_index||'—'}/${mp.parent_total||'—'} · ${mp.search_level||'K 탐색'} · seed ${mp.seed_done??'—'}/${mp.seed_total??'—'}`;
   if(mp.mess_index<=(d.latest_beam?.stage||0)){
     $('stage').textContent=`M1 · MESS ${d.latest_beam.stage}/4 단계 완료`;
     $('stageHint').textContent='다음 fleet 단계 준비 · 아래 solver event는 마지막 저장 기록입니다.';
   }
 }
 $('p1').textContent=fmt(d.current_P1,8);$('baseline').textContent=fmt(d.baseline_P1,8);
 const gain=finite(d.current_P1)&&finite(d.baseline_P1)?d.baseline_P1-d.current_P1:null;
 $('improvement').textContent=finite(gain)?`${gain>=0?'↓':'↑'} ${fmt(Math.abs(gain)/d.baseline_P1*100,4)}%`:'—';
 $('points').textContent=finite(gain)?`${gain>=0?'−':'+'}${fmt(Math.abs(gain)*100,4)}%p`:'—';
 $('improvement').className=finite(gain)&&gain<0?'':'green';
 $('objectiveLabel').innerHTML=(finite(d.current_P1)?'현재 승인된 목적함수 · P1':'현재 단계 목적값 · 승인 결과 대기')+' <span class="pill">낮을수록 좋음</span>';
 if(d.current_kind==='partial_beam')$('objectiveLabel').innerHTML='M1 보존 beam 최소 P1 <span class="pill amber">부분 fleet · AC 미검증</span>';
 if(d.current_kind==='A0_reference')$('objectiveLabel').innerHTML='B3 시작 기준 A0 · 완료된 B1 <span class="pill">B3 최종값 아님</span>';
 if(['B3_M1_reference','B3_A1_reference'].includes(d.current_kind))$('objectiveLabel').innerHTML=`${d.current_kind==='B3_M1_reference'?'완료된 M1':'완료된 A1'} 기준 P1 <span class="pill">다음 단계 준비</span>`;
 $('objectives').innerHTML=names.map((name,i)=>`<div class="obj ${i===idx?'active':''}"><div class="key"><b>P${i+1}</b><span>${i===idx?'현재 탐색':finite(idx)&&i<idx?'상위 목표 lock':'후순위'}</span></div><div class="name">${name}</div><strong>${fmt(d.vector[i],i===0?8:i===1?3:0)}</strong><small>${units[i]}</small></div>`).join('');
 if(!active&&d.role==='B3_M1')$('objectives').querySelectorAll('.key span').forEach((el,i)=>el.textContent=i===0?'M1 모델 목표':'A0 AIDC 고정');
 const ac=d.exact[acSelected],m=ac?.metrics;
 document.querySelectorAll('[data-ac]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.ac===acSelected)));
 $('acBadge').textContent=ac?.status||'결과 대기';$('acBadge').className='badge '+(ac?.status==='PASS'?'':'wait');
 $('acNote').textContent=ac?`${acSelected} · 최종 승인 해 · 96-slot exact AC PASS`:`${acSelected} 최종 exact AC 결과 대기 · 다른 정책의 값으로 대체하지 않습니다`;
 const items=[['최저 전압',m?.Vmin_pu,9,'pu · ≥ 0.95'],['최고 전압',m?.Vmax_pu,9,'pu · ≤ 1.05'],['최대 선로 부하율',m?.max_phase_line_loading_pu,8,'pu · ≤ 1.00'],['변압기 phase-current',m?.max_transformer_phase_current_pu,8,'pu · ≤ 1.00'],['변압기 winding kVA',m?.max_transformer_winding_kva_pu,8,'pu · ≤ 1.00']];
 $('acMetrics').innerHTML=items.map(([label,value,precision,unit])=>`<div class="metric"><small>${label}</small><strong>${fmt(value,precision)}</strong><em>${unit}</em></div>`).join('');
 const metrics=[['Neighborhood solve',active?s.neighborhood_solve_count:null,0,'완료 횟수'],['Exact AC 검증',active?s.exact_AC_validation_count:null,0,'proposal 검증 횟수'],['Incumbent 갱신',active?s.incumbent_updates:null,0,'승인된 개선 횟수'],['Solve median / P95',null,0,active?`${fmt(s.solve_median_seconds,2)} / ${fmt(s.solve_P95_seconds,2)} 초`:'—'],['AC median / P95',null,0,active?`${fmt(s.exact_AC_median_seconds,2)} / ${fmt(s.exact_AC_P95_seconds,2)} 초`:'—'],['현재 / 최대 RAM',null,0,`${fmt(d.worker?.rss/2**30,2)} / ${fmt(s.peak_RAM_bytes/2**30,2)} GiB`]];
 $('activity').innerHTML=metrics.map(([label,v,n,unit])=>`<div class="metric"><small>${label}</small><strong style="font-size:${v===null?'16':'21'}px">${v===null?unit:fmt(v,n)}</strong>${v!==null?'<em>'+unit+'</em>':''}</div>`).join('');
 if(d.role==='B3_M1')$('activity').innerHTML=[['완료된 fleet 단계',`${d.latest_beam?.stage||0} / 4`],['현재 parent',`${mp.parent_index||'—'} / ${mp.parent_total||'—'}`],['후보 탐색 범위',mp.search_level||'준비 중'],['현재 seed',`${mp.seed_done??'—'} / ${mp.seed_total??'—'}`],['마지막 solver event',mp.event||'준비 중'],['프로세스 RAM',`${fmt(d.worker?.rss/2**30,2)} GiB`]].map(([k,v])=>`<div class="metric"><small>${esc(k)}</small><strong style="font-size:18px">${esc(v)}</strong></div>`).join('');
 $('coverage').textContent=finite(d.live.coverage_fraction)?`후보 노출률 ${fmt(d.live.coverage_fraction*100,2)}% · 완료율이나 전역 optimality gap이 아닙니다.`:'현재 단계의 활동 기록이 생성되면 표시합니다.';
 if(d.role==='B3_M1')$('coverage').textContent='fleet 단계는 계산 순서를 나타냅니다. 마지막 solver event와 부분 beam 값은 최종 B3 승인 결과가 아닙니다.';
 $('run').textContent=`실행 폴더: ${d.run_name} · 3초마다 갱신 · 모니터는 출력 파일을 읽기만 합니다.`;
 $('raw').textContent=JSON.stringify(d,null,2);clock(d);renderHistory(d);
}
function renderHistory(d){
 $('tabB1').setAttribute('aria-pressed',String(selected==='B1'));$('tabA1').setAttribute('aria-pressed',String(selected==='B3_A1'));
 const points=d.series[selected]||[],live=d.lives[selected]||{};let e=live.search_loop_wall_seconds||0;
 if(d.role===selected&&d.worker&&d.status.search_started&&!d.status.search_stopped)e=Math.min(14400,Date.now()/1000-d.status.search_started_unix);
 if(!points.length){$('chart').innerHTML='<div class="empty">이 정책의 탐색이 시작되면 승인 P1 추이가 표시됩니다.</div>'}else{
 const w=1100,h=210,L=77,R=23,T=15,B=32,end=Math.min(14400,Math.max(1800,Math.ceil(e/1800)*1800));
 const vals=points.map(x=>x.P1).concat(finite(d.baseline_P1)?[d.baseline_P1]:[]),lo=Math.min(...vals),hi=Math.max(...vals),pad=Math.max((hi-lo)*.2,.00004),min=lo-pad,max=hi+pad;
 const x=t=>L+(Math.min(end,t)/end)*(w-L-R),y=v=>T+(max-v)/(max-min)*(h-T-B);
 let grid='';for(let i=0;i<4;i++){let v=min+(max-min)*i/3,yy=y(v);grid+=`<line x1="${L}" x2="${w-R}" y1="${yy}" y2="${yy}" stroke="#e7edef"/><text x="${L-10}" y="${yy+4}" text-anchor="end" fill="#71838f" font-size="11">${v.toFixed(6)}</text>`}
 for(let i=0;i<5;i++){let t=end*i/4;grid+=`<text x="${x(t)}" y="${h-5}" text-anchor="middle" fill="#71838f" font-size="11">${Math.round(t/60)}분</text>`}
 let path=`M ${x(0)} ${y(points[0].P1)}`;for(const p of points.slice(1))path+=` H ${x(p.seconds)} V ${y(p.P1)}`;const last=points[points.length-1];path+=` H ${x(Math.max(e,last.seconds))}`;
 $('chart').innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">${grid}${finite(d.baseline_P1)?`<line x1="${L}" x2="${w-R}" y1="${y(d.baseline_P1)}" y2="${y(d.baseline_P1)}" stroke="#a6b5bf" stroke-dasharray="5 5"/>`:''}<path d="${path}" fill="none" stroke="#087c65" stroke-width="2.6" vector-effect="non-scaling-stroke"/>${points.slice(1).map(p=>`<circle cx="${x(p.seconds)}" cy="${y(p.P1)}" r="3" fill="#087c65"><title>${fmt(p.seconds/60,1)}분 · iteration ${p.iteration} · P1 ${p.P1.toFixed(8)}</title></circle>`).join('')}</svg>`;
 }
 $('chartNote').textContent=`${selected.replace('B3_','B3 ')} · checkpoint 저장 시각 기준`;
 $('checkpoints').innerHTML=[['30min','30분'],['1h','1시간'],['2h','2시간'],['4h','4시간']].map(([key,label])=>{const r=d.checkpoints[selected]?.[key];return `<div class="checkpoint"><small>${label} checkpoint</small><strong>${fmt(r?.P1,8)}</strong><span class="checkstate">${r?'✓ 저장 완료 · iteration '+r.iteration:'기록 대기'}</span></div>`}).join('');
}
async function tick(){try{const response=await fetch('/api/dashboard',{cache:'no-store'});if(!response.ok)throw Error('HTTP '+response.status);data=await response.json();lastFetch=Date.now();render(data)}catch(err){$('health').textContent='모니터 연결 끊김';$('health').className='badge bad';$('alert').hidden=false;$('alert').textContent='마지막 수신 값을 유지하고 있습니다. 연결 재시도 중: '+err.message}}
tick();setInterval(tick,3000);setInterval(()=>{if(data)clock(data)},1000);
