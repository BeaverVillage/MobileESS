function renderIteration2(data){
 const by=id=>document.getElementById(id),card=by('iteration2-card');card.hidden=!data?.available;if(card.hidden)return;
 const node=(tag,text,cls)=>{const e=document.createElement(tag);e.textContent=text??'—';if(cls)e.className=cls;return e};
 const numeric=n=>Number.isFinite(n)?n.toFixed(6):'—',gap=n=>Number.isFinite(n)?(100*n).toFixed(3)+'%':'인증 대기';
 const phi=n=>Number.isFinite(n)?n!==0&&Math.abs(n)<1e-5?n.toExponential(5):numeric(n):'—';
 by('iteration2-status').textContent=data.label;
 by('iteration2-title').textContent='V44_iteration2 · 31일 단계별 결과';
 by('iteration2-summary').textContent=`단계 PASS ${data.stages_pass||0}/155 · M4 동결 ${data.planning_pass}/31 · Actual/Fresh PASS ${data.actual_pass}/31 · 확인 필요 ${data.failed_dates||0}일 · Native 합계 ${data.Native_total_estimated?'약 ':''}${(data.Native_total_seconds||0).toFixed(1)} s · 감독기 ${data.supervisor_alive?'연결':'확인 필요'}`;
 const current=(data.workers||[]).find(w=>w.alive),voltage=current?.voltage,phase=current?.phase_I;
 by('iteration2-policy').textContent=current?`${current.stage} · ${voltage?voltage.voltage_band.join('~')+' pu · '+voltage.label+(voltage.lower_rows?' · 하한/상한 각 '+voltage.lower_rows.toLocaleString()+'행':''):current.stage==='ACTUAL'?'Actual120 → 독립 Fresh120 · 0.95~1.05 pu':'AIDC FULL · 독립 Gap 0.5%'} · ${data.fresh_M2_zero_start?'전 날짜 M2·Native 0초 시작':'현재 캠페인 원장 기준'}`:'M2/M3 0.955~1.045 pu · M4/Actual/Fresh 0.95~1.05 pu · 날짜별 새 Native 계정';
 by('iteration2-phase').textContent=phase?`Phase I · Φ ${phi(phase.Phi)} · zero ${phase.zero_PASS?'PASS':'검증 대기'} (기준 1e-8) · Native ${(phase.Native_seconds||0).toFixed(1)} / 1500 s (A 5400 s에 포함) · 정밀도 1e-9${Number.isInteger(phase.solve)?' · solve '+phase.solve:''}`:'';
 const body=by('iteration2-days'),opened=new Set([...body.querySelectorAll('details[open]')].map(e=>e.dataset.key));
 body.replaceChildren(...(data.rows||[]).map(row=>{const tr=node('tr','');tr.append(node('th',row.day.slice(5).replace('-','/')));
 for(const s of row.stages){const td=node('td',''),d=node('details',''),key=row.day+'_'+s.stage;d.dataset.key=key;d.open=opened.has(key);
 const summary=node('summary',s.label,s.status==='PASS'?'case-loading-pass':s.status==='RUNNING'?'case-loading-live':s.status==='QUEUED'?'case-loading-pending':'case-loading-fail');
 d.append(summary);const bounds=node('div',`UB ${numeric(s.UB)} / LB ${numeric(s.LB)} / Gap ${gap(s.Gap)}`);bounds.style.fontSize='11px';d.append(bounds);
 const nativeLabel=node('small',Number.isFinite(s.Native_seconds)?`${s.Native_estimated?'약 ':''}Native ${s.Native_seconds.toFixed(1)} s`:'미실행');
 if(s.voltage){d.append(node('small',s.voltage.voltage_band.join('~')+' pu'));d.append(node('small',s.voltage.label));if(Number.isFinite(s.K48_Native_seconds))d.append(node('small',`K48 ${s.K48_Native_seconds.toFixed(1)}/300 · Joint ${s.Joint_Native_seconds.toFixed(1)}/900 s`))}
 if(s.phase_I)d.append(node('small',`Phase I Φ ${phi(s.phase_I.Phi)} · ${s.phase_I.zero_PASS?'zero PASS':'zero 대기'} · ${(s.phase_I.Native_seconds||0).toFixed(1)}/1500 s`));
 const sha=node('small',s.plan_sha||s.case_sha||'SHA 수신 대기');sha.style.cssText='max-width:160px;white-space:normal;overflow-wrap:anywhere';d.append(sha);if(s.error)d.append(node('small',s.error));td.append(d,nativeLabel);tr.append(td)}
 const a=row.actual,td=node('td',a.label,a.overall_PASS?'case-loading-pass':a.status==='RUNNING'?'case-loading-live':a.status==='QUEUED'?'case-loading-pending':'case-loading-fail');
 if(Number.isFinite(a.line_percent))td.append(node('small',`평가96 최대 선로 ${a.line_percent.toFixed(3)}%`));if(Number.isFinite(a.transformer_percent))td.append(node('small',`변압기 ${a.transformer_percent.toFixed(3)}%`));if(Number.isFinite(a.Vmin))td.append(node('small',`V ${a.Vmin.toFixed(5)}~${a.Vmax.toFixed(5)}`));td.title=a.error||row.error||a.root||'';tr.append(td);return tr}));
 by('iteration2-workers').replaceChildren(...(data.workers||[]).map(w=>{const tr=node('tr','');for(const v of [w.day+' '+w.stage,`PID ${w.pid} · ${w.alive?'실행':'프로세스 종료'}`,w.Native_text||'Actual / Fresh · 신규 최적화 없음',w.bounds?`${w.bounds.ub_text} / ${w.bounds.lb_text} / ${w.bounds.gap_text}`:'최적화 Gap 해당 없음'])tr.append(node('td',v));tr.title=w.root;return tr}));
 by('iteration2-slots').textContent=(data.slots||[]).map(s=>`슬롯 ${s.slot}: ${s.day||s.status}${s.pid?' (PID '+s.pid+')':''}`).join(' · ');
 const r=data.resources;by('iteration2-resources').textContent=(r?`진입 검사 시 RAM ${(r.available_RAM_bytes/2**30).toFixed(1)} GB · 예비 ${(r.reserve_RAM_bytes/2**30).toFixed(1)} GB · 추가 Worker 예상 ${(r.additional_worker_RAM_estimate_bytes/2**30).toFixed(1)} GB · 디스크 ${(r.free_disk_bytes/2**30).toFixed(1)} GB · ${r.admit?'진입 허용':'신규 진입 대기'}`:'자원 진입 검사 대기')+` · 현재 상태 갱신 ${Number.isFinite(data.age_seconds)?data.age_seconds.toFixed(0)+'초 전':'대기'}`;
 by('iteration2-error').textContent=data.error||'';
}
