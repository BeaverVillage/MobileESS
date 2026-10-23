function renderIteration2(data){
 const by=id=>document.getElementById(id),card=by('iteration2-card');card.hidden=!data?.available;if(card.hidden)return;
 const node=(tag,text,cls)=>{const e=document.createElement(tag);e.textContent=text??'—';if(cls)e.className=cls;return e};
 const numeric=n=>Number.isFinite(n)?n.toFixed(6):'—',gap=n=>Number.isFinite(n)?(100*n).toFixed(3)+'%':'—';
 const tone=s=>['PASS','COMPLETE'].includes(s)?'case-loading-pass':s==='RUNNING'?'case-loading-live':['FAIL','BLOCKED'].includes(s)?'case-loading-fail':'case-loading-pending';
 const worker=data.current_validation_process;
 by('iteration2-status').textContent=data.label+(!data.official_campaign_started&&worker?' · 현재 검증 Worker Wall '+worker.age_seconds.toFixed(0)+' s / CPU '+worker.CPU_seconds.toFixed(0)+' s':'');
 by('iteration2-summary').textContent='A1 전체 Native0 '+(data.A1_preparation?'PASS':'대기')+' · Job 시작시간 권위 '+(data.timing_authority?'PASS':'대기')+' · 필수 검증 '+data.preparation_pass+'/'+data.preparation_total+' · 공식 Native '+data.official_measured_Native_seconds.toFixed(1)+' s · 격리 진단 Native 호출 '+data.diagnostic_Native_optimize_calls+'회';
 const body=by('v2-preparation'),opened=new Set([...body.querySelectorAll('details[open]')].map(e=>e.dataset.key));
 body.replaceChildren(...data.preparation.map(r=>{const tr=node('tr','');tr.append(node('td',r.name),node('td',({PASS:'통과',RUNNING:'진행 중',FAIL:'오류',QUEUED:'대기'})[r.status]||r.status,tone(r.status)),node('td',Number.isFinite(r.wall_seconds)?r.wall_seconds.toFixed(1)+' s':'—'));
 const td=node('td','');if(r.detail){const d=node('details','');d.dataset.key=r.name;d.open=opened.has(r.name);d.append(node('summary','기록 보기'));const p=node('pre',r.detail);p.style.cssText='max-width:520px;max-height:220px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:10px';d.append(p);td.append(d)}else td.textContent=r.group;tr.append(td);return tr}));
 by('iteration2-days').replaceChildren(...data.rows.flatMap(r=>r.stages.map(s=>{const tr=node('tr','');tr.append(node('th',r.arm+' · '+s.stage),node('td',s.label,tone(s.status)),node('td',s.Native.text));
 const b=node('td','UB '+numeric(s.UB)+' / LB '+numeric(s.LB)+' / '+gap(s.Gap));b.style.whiteSpace='nowrap';
 if(['A1','A2','A1_REUSE','M1','M2'].includes(s.stage)&&s.status!=='QUEUED')b.append(node('small',s.gap_certified?'목표 Gap 인증':'목표 Gap 미인증',s.gap_certified?'case-loading-pass':'case-loading-pending'));tr.append(b);
 const c=s.costs,td=node('td',Number.isFinite(c.non_Native_preparation_validation_IO_and_score_wall_seconds)?c.non_Native_preparation_validation_IO_and_score_wall_seconds.toFixed(1)+' s':'—');
 if(s.stage==='A1_REUSE')td.append(node('small',s.reused_exact_A1?'B1 A1 재사용 검증 완료':'B1 FULL A1 재사용 예정'));
 if(s.phase_I){const p=s.phase_I.Phi;td.append(node('small','Phase I Φ '+(Number.isFinite(p)&&p!==0&&Math.abs(p)<1e-5?p.toExponential(5):numeric(p))+' · '+(s.phase_I.zero_PASS?'zero PASS':'zero 검증 대기')))}
 if(s.physical){const f=s.physical;td.append(node('small','Fresh '+(f.PASS?'PASS':'FAIL')+' · V '+numeric(f.Vmin)+'~'+numeric(f.Vmax)));if(Number.isFinite(f.line_percent))td.append(node('small','최대 선로 '+f.line_percent.toFixed(3)+'%'))}
 if(s.error)td.append(node('small',s.error,'case-loading-fail'));tr.title=[s.root,s.case_sha||'',s.B1_A1_result_sha||''].join('\n');tr.append(td);return tr})));
 by('iteration2-workers').replaceChildren(...data.workers.map(w=>{const tr=node('tr','');tr.append(node('td',w.waiting?'검증/실행 감독기':data.official_campaign_started?'공식 캠페인 Worker':'실제 검증 Worker'),node('td',String(w.pid)));const c=node('td',w.command);c.style.cssText='max-width:420px;overflow-wrap:anywhere;font-size:10px';tr.append(c);return tr}));
 by('iteration2-error').textContent=data.error||'';
}
