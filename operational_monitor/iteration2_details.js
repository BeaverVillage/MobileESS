function renderIteration2(data){
 const by=id=>document.getElementById(id),card=by('iteration2-card');card.hidden=!data?.available;if(card.hidden)return;
 const node=(tag,text,cls)=>{const e=document.createElement(tag);e.textContent=text??'—';if(cls)e.className=cls;return e};
 const numeric=n=>Number.isFinite(n)?n.toFixed(6):'—',gap=n=>Number.isFinite(n)?(100*n).toFixed(3)+'%':'인증 대기';
 by('iteration2-status').textContent=data.label;
 by('iteration2-title').textContent=(['WAIT_B2','WAIT_B2_RESOURCES'].includes(data.phase)?'후속 캠페인':'반복 공동최적화')+' · V44_iteration2';
 by('iteration2-summary').textContent=`M4 검증 ${data.planning_pass}/31 · Actual/Fresh PASS ${data.actual_pass}/31 · 후속 Worker ${(data.workers||[]).filter(w=>w.alive).length} · 감독기 ${data.supervisor_alive?'연결':'확인 필요'}`;
 const body=by('iteration2-days'),opened=new Set([...body.querySelectorAll('details[open]')].map(e=>e.dataset.key));
 body.replaceChildren(...(data.rows||[]).map(row=>{const tr=node('tr','');tr.append(node('th',row.day.slice(5).replace('-','/')));
 for(const s of row.stages){const td=node('td',''),d=node('details',''),key=row.day+'_'+s.stage;d.dataset.key=key;d.open=opened.has(key);
 const summary=node('summary',s.label,s.status==='PASS'?'case-loading-pass':s.status==='RUNNING'?'case-loading-live':s.status==='QUEUED'?'case-loading-pending':'case-loading-fail');
 d.append(summary);const bounds=node('div',`UB ${numeric(s.UB)} / LB ${numeric(s.LB)} / Gap ${gap(s.Gap)}`);bounds.style.fontSize='11px';d.append(bounds);
 d.append(node('small',Number.isFinite(s.Native_seconds)?`Native ${s.Native_seconds.toFixed(1)} s`:'Native 미실행 / 수신 대기'));
 const sha=node('small',s.plan_sha||s.case_sha||'SHA 수신 대기');sha.style.cssText='max-width:160px;white-space:normal;overflow-wrap:anywhere';d.append(sha);if(s.error)d.append(node('small',s.error));td.append(d);tr.append(td)}
 const a=row.actual,td=node('td',a.label,a.overall_PASS?'case-loading-pass':a.status==='RUNNING'?'case-loading-live':a.status==='QUEUED'?'case-loading-pending':'case-loading-fail');
 if(Number.isFinite(a.line_percent))td.append(node('small',`최대 선로 ${a.line_percent.toFixed(3)}%`));if(Number.isFinite(a.Vmin))td.append(node('small',`V ${a.Vmin.toFixed(5)}~${a.Vmax.toFixed(5)}`));td.title=a.error||row.error||a.root||'';tr.append(td);return tr}));
 by('iteration2-workers').replaceChildren(...(data.workers||[]).map(w=>{const tr=node('tr','');for(const v of [w.day+' '+w.stage,`PID ${w.pid} · ${w.alive?'실행':'프로세스 종료'}`,w.Native_text||'Actual / Fresh · 신규 최적화 없음',w.bounds?`${w.bounds.ub_text} / ${w.bounds.lb_text} / ${w.bounds.gap_text}`:'최적화 Gap 해당 없음'])tr.append(node('td',v));tr.title=w.root;return tr}));
 by('iteration2-slots').textContent=(data.slots||[]).map(s=>`슬롯 ${s.slot}: ${s.day||s.status}${s.pid?' (PID '+s.pid+')':''}`).join(' · ');
 const r=data.resources;by('iteration2-resources').textContent=r?`RAM 여유 ${(r.available_RAM_bytes/2**30).toFixed(1)} GB · 예비 ${(r.reserve_RAM_bytes/2**30).toFixed(1)} GB · 추가 Worker 예상 ${(r.additional_worker_RAM_estimate_bytes/2**30).toFixed(1)} GB · 디스크 여유 ${(r.free_disk_bytes/2**30).toFixed(1)} GB · ${r.admit?'자원 진입 가능':'신규 진입 대기'}`:'B2가 최종 종료되고 PID·Lock·원장 정리가 확인된 후 자동 시작합니다.';
 by('iteration2-error').textContent=data.error||'';
}
