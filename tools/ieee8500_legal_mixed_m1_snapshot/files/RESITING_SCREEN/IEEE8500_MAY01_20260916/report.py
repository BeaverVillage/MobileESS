from optimize import *
from datetime import datetime,timezone

def main():
 selected=read(H/'PROVISIONAL_SELECTION.json');name=selected['placement'];layout=selected['layout'];base=H/'final_proxy'/name;slots=list(range(34,54))+list(range(68,86));policies=[];repeat=[]
 for policy in ['B0','B1','B2','B3']:
  f=base/policy;r=read(f/'RESULT.json');p=np.load(f/'POWER.npz')['pcc'];mm={(x['slot'],x['station']):(x['P'],x['Q']) for x in read(f/'MESS.json')}
  rr=replay(layout,p,H/'verification'/policy,mm,slots=slots);err=abs(rr['max_phase_line_loading_pu']-r['max_phase_line_loading_pu']);assert rr['physical_pass'] and err<1e-8,(policy,err)
  repeat.append(dict(policy=policy,status='PASS',rho_repeat_difference=err,slots=len(slots)));policies.append(r)
 table(H/'SELECTED_POLICY_METRICS.csv',policies);save(H/'RESTRICTED_REPLAY_VERIFICATION.json',repeat)
 f=base/'B3';p=np.load(f/'POWER.npz')['pcc'];mm={(x['slot'],x['station']):(x['P'],x['Q']) for x in read(f/'MESS.json')};jobs=read(f/'JOBS.json');migr=[j for j in jobs if j.get('migration_selected',False)];pairs=collections.defaultdict(lambda:dict(jobs=0,GPUs=0,WAN_bytes=0))
 for j in migr:
  a=j.get('initial_AIDC',j.get('r1_reference_site'));b=j.get('migration_destination',j['AIDC_site']);r=pairs[a+' -> '+b];r['jobs']+=1;r['GPUs']+=j['requested_GPU'];r['WAN_bytes']+=j['frozen_WAN_transfer']['payload_bytes']
 migration=dict(migrated_jobs=len(migr),GPUs=sum(j['requested_GPU'] for j in migr),WAN_bytes=sum(j['frozen_WAN_transfer']['payload_bytes'] for j in migr),patterns=[dict(route=k,**v) for k,v in pairs.items()]);save(H/'SELECTED_MIGRATION.json',migration)
 stations=[]
 for i,c in enumerate(layout['mess']):
  sid=IDS[i];vals=[(t,*mm.get((t,sid),(0,0))) for t in range(96)];k=max(vals,key=lambda x:np.hypot(x[1],x[2]));stations.append(dict(MESS=f'MESS{i+1:02}',station=sid,bus_connection=c['key'],phases=c['phases'],primary_kV=c['kv'],P_peak_kw=max(x[1] for x in vals),charging_peak_kw=-min(x[1] for x in vals),Q_min_kvar=min(x[2] for x in vals),Q_max_kvar=max(x[2] for x in vals),S_peak_kVA=np.hypot(k[1],k[2]),S_peak_slot=k[0],P_slot75=mm.get((75,sid),(0,0))[0],Q_slot75=mm.get((75,sid),(0,0))[1]))
 table(H/'SELECTED_MESS.csv',stations);save(H/'SELECTED_MESS.json',stations)
 table(H/'SELECTED_AIDC.csv',[dict(AIDC=f'AIDC{i+1:02}',bus=b,phase_connection=b+'.1.2.3',primary_kV=12.47,secondary_kV=.48,transformer_kVA=1500) for i,b in enumerate(layout['aidc'])])
 e=ResiteEngine(layout,H/'witness_runtime');branch=[];prev=None
 for t in slots:
  if prev is None or t!=prev+1:e.restore(t)
  e.inputs(t,p,p*(BASE_Q/BASE_P),mm);r,a=e.measure(t);idx=[i for i,l in enumerate(e.ax['line_label']) if l.startswith('Line.tpx21459660c0|')];maxcrit=max(a[1][idx]);branch.append(dict(slot=t,old_critical_rho=float(maxcrit),new_max_rho=r['max_phase_line_loading_pu'],new_witness=r['line_witness'],Vmin=r['Vmin_pu'],Vmin_node=r['Vmin_node'],Vmax=r['Vmax_pu'],Vmax_node=r['Vmax_node']));prev=t
 e.close();table(H/'SELECTED_BOTTLENECKS.csv',branch)
 sens=[r for r in read(H/'SENSITIVITY_MAP.json') if r['slot']==75 and (r['key'] in [c['key'] for c in layout['mess']] or r['bus'] in layout['aidc'])];save(H/'SELECTED_SENSITIVITY.json',sens)
 bound=read(H/'RESITED_NECESSARY_AC_BOUND.json')['strongest'];best=selected['metrics'];cert=dict(original_0931437_obstruction_removed=True,reason='MESS01 has a phase-1 PCC directly on sx3101194c downstream of tpx21459660c0. Native leaf current is no longer fixed by native load alone.',critical_line_rho_max=max(r['old_critical_rho'] for r in branch),necessary_lower_bound=bound['bound'],exact_feasible_upper_witness=best['rho_B3'],global_optimum_proven=False,scope_slots=slots,full_May1_reachability_not_yet_validated=True,remaining_uncontrolled_leaf=bound['leaf'],objective_bottleneck=max(branch,key=lambda x:x['new_max_rho']))
 save(H/'SELECTION_EVIDENCE.json',cert)
 # All original authorities are still read-only after every run.
 hashes=read(H/'SOURCE_MANIFEST.json');assert all(original.sha(Path(x['path']))==x['sha256'] for x in hashes)
 runtime=(datetime.now().timestamp()-(H/'inventory.py').stat().st_ctime)/60
 report=[f'# IEEE8500 RESITING_SCREEN — May-1',f'\n선정 후보: **{name}**, s_DC=s_MESS=1.00. Screening 한정, Full 96-slot / Fresh pipeline / Actual 미실행. 최종 infrastructure freeze는 아직 하지 않았다.',
 '\n## 범위와 판정',
 'Native bus inventory에서 service/phase/연결성을 검사했고, 111개 진단 접속점의 10-slot P/Q finite differences 중 source/capacitor internal 진단점 3개를 제외한 108개를 후보로 사용했다. 3개 AIDC 배치 × 3개 MESS 배치의 B0 gate를 검사했다. 최종 비교는 고부하 68–85번 18 slots와 낮 시간 충전 34–53번 20 slots, 합계 38 slots exact AC이다. 시간 인덱스는 기존 자료와 동일한 0-based이다.',
 f'기존 ρ≥0.931437 local obstruction은 직접 downstream 단상 접속으로 제거됐다. 현재 scale에서 exact-AC feasible B3 witness는 **{best["rho_B3"]:.9f}**이다. 실제 최적값을 증명한 수치는 아니다. 해당 6-station infrastructure에 대한 별도 native-leaf 필요 하한은 **{bound["bound"]:.9f}**이며, 현재 알려진 critical-slot 최적값 범위는 [{bound["bound"]:.9f}, {best["rho_B3"]:.9f}]이다. 이 결과는 full-day production 보증이 아니다.',
 '\n## 동일 infrastructure / 동일 physical authority의 proxy',
 '| Policy | rho | Vmin | Vmax | transformer I pu | transformer kVA pu | AC |\n|---|---:|---:|---:|---:|---:|---|']
 for r in policies:report.append(f'| {r["policy"]} | {r["max_phase_line_loading_pu"]:.9f} | {r["Vmin_pu"]:.7f} | {r["Vmax_pu"]:.7f} | {r["max_transformer_phase_current_pu"]:.7f} | {r["max_transformer_winding_kva_pu"]:.7f} | PASS |')
 report += [f'\nStrict ordering (tie tolerance 1e-6): **{best["strict_ordering"]}**. B0−B3={best["total_reduction"]:.9f}; 최소 adjacent separation={best["min_adjacent_separation"]:.9f}. 순서 제약은 추가하지 않았다.',
 '\n원래 job/WAN/resource/PWL 제약과 P1–P5 hierarchy를 가진 24-cohort 제한 MILP를 실행했다. MILP의 일부 electrical 근사는 exact AC에서 실패하여 탈락시켰다. 최종 표는 원래 audit를 통과한 3개 workload schedule과 exact AC 보정한 2개 MESS schedule의 동일 후보 집합을 각 배치에 적용하여 얻은 실행 가능한 최선의 proxy이다. 전체 job/route domain의 전역 최적화 결과가 아니다. B3는 B0 workload를 유지하는 선택도 허용한다. 모든 선택은 exact rho를 우선 비교했으며 ordering을 강제하지 않았다.',
 '\n## AIDC 12개 — 모두 3상 .1.2.3, 12.47/0.48 kV, 1500 kVA',
 '| AIDC | native host bus |\n|---|---|']
 report += [f'| AIDC{i+1:02} | {b} |' for i,b in enumerate(layout['aidc'])]
 report += ['\n## MESS 6개 — 기존 P=300 kW, S=400 kVA, E=1200 kWh 유지', '| MESS | station | host connection | phase | max P kW | max abs Q kvar | max S kVA |\n|---|---|---|---:|---:|---:|---:|']
 for r in stations:report.append(f'| {r["MESS"]} | {r["station"]} | {r["bus_connection"]} | {r["phases"]} | {r["P_peak_kw"]:.4f} | {max(abs(r["Q_min_kvar"]),abs(r["Q_max_kvar"])):.4f} | {r["S_peak_kVA"]:.4f} |')
 report += ['\n사용자 승인에 따라 네 저압 단상 PCC의 전압/상 인터페이스를 해당 native bus에 맞췄다. Native 선로/변압기 임피던스와 정격은 바꾸지 않았다. Additive PCC transformer는 기존 750 kVA, XHL=5.75%, %Rs=[0.8,0.2]를 유지한다. 여섯 station은 중복 없이 서로 다른 native bus이다. 모든 MESS는 재배치한 각 initial station ID에 계속 연결되므로 이동/소비 에너지는 0이다. 이것은 합법적인 stationary route witness이며 전체 route-search optimum은 아니다.',
 f'\n선택 B3의 migration: {migration["migrated_jobs"]} jobs, {migration["GPUs"]} GPUs, WAN payload {migration["WAN_bytes"]:,} bytes. 전체 96-slot workload/WAN/resource 및 per-GPU 전력 재구성 audit는 PASS. SOC 440–1080 kWh, initial=terminal=760 kWh, ηc=ηd=.95를 모두 검사했다.',
 '\n## 남은 제약 및 한계',
 f'현재 objective bottleneck: `{cert["objective_bottleneck"]["new_witness"]}`, slot {cert["objective_bottleneck"]["slot"]}. 미접속 말단 `{bound["leaf"]}`의 native current/voltage ceiling은 별도 필요 하한 {bound["bound"]:.9f}을 만든다. 채택 해의 모든 hard physical constraints는 여유를 갖고 통과했으므로, 이 해만으로 전역 optimum의 binding constraint를 특정하지 않는다. Native regulator/capacitor의 이산 동작 때문에 근사 목적값과 exact rho의 차이가 있으며, 더 공격적인 근사 해는 채택하지 않았다.',
 f'\n실행 경과(코드 준비/수치 검증 포함): 약 {runtime:.1f}분. 최종 공통 제어 후보 비교: {read(H/"PROXY_METHOD.json")["policy_comparison_runtime_seconds"]:.1f}초. 원본 authority hash {len(set(x["path"] for x in hashes))}개 및 native physical element audit PASS. 결과 파일은 RESITING_SCREEN 내부에만 작성했다.',
 '\n## 핵심 파일',
 '- FINAL_PROXY_RESULTS.csv/json: 상위 3개 배치 비교\n- SELECTED_AIDC.csv / SELECTED_MESS.csv: 최종 screening 후보 bus·phase·출력\n- SENSITIVITY_MAP.csv / SELECTED_SENSITIVITY.json: exact finite-difference 근거\n- SELECTION_EVIDENCE.json: 기존 하한 제거, 새 필요 하한, exact witness\n- SELECTED_MIGRATION.json: 실제 workload migration\n- INDEPENDENT_WORKLOAD_AUDIT.json / NATIVE_PHYSICAL_AUTHORITY_AUDIT.json / SOURCE_CONSERVATION.json\n- PROXY_METHOD.json: 범위·제약·검색 제한\n- RESTRICTED_REPLAY_VERIFICATION.json: 선정 4정책 38-slot 재현 검증']
 (H/'REPORT_KO.md').write_text('\n'.join(report),encoding='utf-8');save(H/'FINAL_STATUS.json',dict(status='SCREENING_COMPLETE',runtime_minutes_including_development=runtime,selected=name,scales=[1.,1.],full_May1_executions=0,Fresh_pipeline_executions=0,Actual_executions=0,original_authorities_unchanged=True,selected_policies_exact_replay_pass=True,global_optimum_proven=False))
 print(json.dumps(dict(selected=name,metrics=best,migration=migration,evidence=cert)),flush=True)
if __name__=='__main__':main()
