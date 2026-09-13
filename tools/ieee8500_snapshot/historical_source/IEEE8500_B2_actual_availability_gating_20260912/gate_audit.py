"""Freeze then read-only IEEE123 mobility/final-Q compatibility gate. No AC runs."""
import sys
sys.dont_write_bytecode = True
import ast, csv, hashlib, json, math, time
from pathlib import Path
from datetime import datetime,timezone
import availability_gating as g

H = Path(__file__).resolve().parent
W = Path(r'D:\ChatGPT\Mobile ESS 2')
R = Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
F = R/'frozen_artifacts'
OLD = W/'IEEE8500_actual_20260912_r3'
AUDIT = W/'IEEE123_ACTUAL_DEPARTURE_COLLISION_AUDIT_20260912'

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(name,value):
    p=H/name
    assert p.resolve().is_relative_to(H)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def record(p):
    p=Path(p).resolve();return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns)
def protect():
    def guard(event,args):
        p=None
        if event=='open':
            path,mode,flags=args
            if mode and any(c in mode for c in 'wax+'):p=path
            if flags and flags & (1|2|64|512|1024):p=path
        elif event in ('os.remove','os.rmdir','os.mkdir','os.rename','os.replace'):
            raise PermissionError('NO_SOURCE_FILESYSTEM_MUTATION')
        if p is not None and isinstance(p,(str,bytes,Path)):
            assert Path(p).resolve().is_relative_to(H),'READ_ONLY_SOURCE_WRITE_BLOCKED'
    sys.addaudithook(guard)
def project():
    p=R/'dayahead/v40d_actual/mess_replay.py'
    t=ast.parse(p.read_text(encoding='utf-8'))
    f=next(x for x in t.body if isinstance(x,ast.FunctionDef) and x.name=='project_command')
    ns=dict(math=math,ReplayError=RuntimeError,P_LIMIT_KW=300.,PCS_KVA=400.)
    exec(compile(ast.Module(body=[f],type_ignores=[]),str(p),'exec'),ns)
    return ns['project_command']
def freeze():
    assert not (H/'RULE_FREEZE.json').exists()
    refs={}
    def add(p,expected=None):
        z=record(p)
        if expected:assert z['sha256']==expected,str(p)
        refs[z['path']]=z
    for p in H.glob('*.py'):add(p)
    for x in read(AUDIT/'INPUT_READ_ONLY_MANIFEST.json'):add(x['path'],x['sha256_after'])
    for x in read(OLD/'RULE_FREEZE.json')['source_files']:add(x['path'],x['sha256'])
    for p in ['RULE_FREEZE.json','RULE_FREEZE_SHA256.json','FINAL_SHA256_MANIFEST.json','actual8500.py',
              'B2/ACTUAL_MOBILITY_PRE_REPLAY.json','B2/ACTUAL_INPUT_FAILURE.json','CAMPAIGN_COMPLETE.json']:
        add(OLD/p)
    for x in read(F/'v41r4_restoration_revision_v1/FINAL_AUDIT.json')['rows']:
        rep=(F/'v41r4_revision_monitor_view/replays'/x['day']/x['policy']).resolve()
        receipt=read(rep/'CANDIDATE_RECEIPT.json')
        stage='CONTROL_COMMON_BINDING' if x['policy'] in ('B0','B1') else 'ETA95_ACTUAL'
        rel=stage+'\\ACTUATOR.json';add(rep/rel,receipt['files'][rel])
    rule=dict(rule='REALIZED_MOBILITY_CAUSAL_AVAILABILITY_GATING',status='FROZEN_BEFORE_REGRESSION_NOT_PRODUCTION_APPROVED',
              date='2025-05-21',scope='IEEE8500 B2 Actual only, after IEEE123 124-policy-day behavioral-equivalence PASS',
              actual_departure='max(planned_departure_of_move_k, previous_move_actual_connection_ready_slot)',
              previous_ready_index='k-1 identifies previous move; it does not subtract one slot',
              frozen_command_clock='unchanged; unavailable or different/no planned PCC means P=Q=0; discard, never catch up',
              movement='frozen vehicle/visit-order/origin/destination/route; causal realized SUMO traversal at actual departure',
              connection_delay_seconds=600,slot_seconds=900,
              qsafe='Original robust V2 search and executed P immutable; physically connected AND frozen-PCC eligible mask',
              explicit_interpretation='The P=Q=0 per-slot gate remains binding after QSAFE. Frozen service_id=None is no planned PCC. This interpretation must pass existing final-Q regression before any B2 replay.',
              battery='Original 0.95 efficiencies, 1200 kWh capacity, 440..1080 kWh bounds; actual travel plus executed P, no terminal compensation',
              operating_point=dict(source_pu=1.04,Vreg_V=123.5,alpha8500=.5,CAPBank3='OFF'),
              hard_limits=dict(Vmin=.95,Vmax=1.05,line=1.,transformer_phase_current=1.,transformer_kVA=1.),
              forbidden_counters={k:0 for k in g.FORBIDDEN},
              fail_close='Any regression difference stops before IEEE8500 mobility/AC; no reinterpretation or tuning to force PASS',
              original_rule_sha=sha(OLD/'RULE_FREEZE.json'),source_files=list(refs.values()),frozen_utc=datetime.now(timezone.utc).isoformat())
    save('RULE_FREEZE.json',rule);save('RULE_FREEZE_SHA256.json',record(H/'RULE_FREEZE.json'))
    print('FROZEN',len(refs),sha(H/'RULE_FREEZE.json'),flush=True)

def run():
    assert not (H/'GATE_RESULT.json').exists(),'NO_OVERWRITE_EXISTING_GATE'
    rule=read(H/'RULE_FREEZE.json');assert sha(H/'RULE_FREEZE.json')==read(H/'RULE_FREEZE_SHA256.json')['sha256']
    for rec in rule['source_files']:assert sha(rec['path'])==rec['sha256'],rec['path']
    protect()
    projector=project();all_rows=[];witnesses=[];availability_differences=[]
    totals=dict(policy_days=0,moves=0,baseline_behavior_differences=0,departure_shifts=0,
                final_Q_gate_violations=0,final_P_gate_violations=0,availability_mask_changes=0)
    for auth in read(F/'v41r4_restoration_revision_v1/FINAL_AUDIT.json')['rows']:
        day,policy=auth['day'],auth['policy'];rep=(F/'v41r4_revision_monitor_view/replays'/day/policy).resolve()
        common=rep.parents[2]/'common_inputs'/day/policy
        saved=read(common/'ACTUAL_MESS_AUDIT.json')
        initial={s['vehicle_id']:s['frozen_initial_location'] for s in saved['initial_states']}
        old_moves={(m['mess_id'],m['departure_slot']):m for m in saved['moves']}
        def saved_same_departure(c,dep):
            # All IEEE123 moves are unshifted. No realized-data reconstruction needed.
            assert dep==c['departure_slot'],'REGRESSION_REQUIRES_SHIFTED_TRAVERSAL'
            return old_moves[c['mess_id'],dep]
        new_moves=g.realize_sequence(saved['frozen_commands'],initial,saved_same_departure)
        out=g.replay(saved['frozen_commands'],new_moves,saved['initial_energy'],initial,projector,
                     capacity_kwh=1200.,e_min=440.,e_max=1080.,pcs_kva=400.,eta_charge=.95,eta_discharge=.95,dt_hours=.25)
        base_stage='CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_ACTUAL'
        final_stage='CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_QSAFE_ACTUAL'
        baseline=read(rep/base_stage/'ACTUATOR.json')['trajectory']
        final=read(rep/final_stage/'ACTUATOR.json')['trajectory']
        by={(r['mess_id'],r['slot']):r for r in out['trajectory']}
        mask={(r['mess_id'],r['slot']):r for r in out['availability']}
        assert len(by)==len(baseline)==len(final)==384
        base_diffs=[]
        for old in baseline:
            new=by[old['mess_id'],old['slot']]
            delta={k:dict(old=v,new=new.get(k)) for k,v in old.items() if new.get(k)!=v}
            if delta:base_diffs.append(dict(day=day,policy=policy,mess_id=old['mess_id'],slot=old['slot'],differences=delta))
        local_final=[]
        for old in final:
            m=mask[old['mess_id'],old['slot']]
            if m['qsafe_eligible'] != old['connected']:
                availability_differences.append(dict(day=day,policy=policy,**m,original_QSAFE_connected=old['connected'],
                                                     existing_P_EXEC=old['P_EXEC'],existing_Q_EXEC=old['Q_EXEC']))
            if not m['command_eligible'] and (old['P_EXEC']!=0 or old['Q_EXEC']!=0):
                w=dict(day=day,policy=policy,mess_id=old['mess_id'],slot=old['slot'],
                       frozen_PCC=old['frozen_service_id'],actual_PCC=old['actual_service_id'],
                       frozen_P_CMD=old['P_CMD'],frozen_Q_CMD=old['Q_CMD'],
                       original_P_EXEC=old['P_EXEC'],original_Q_EXEC=old['Q_EXEC'],
                       required_gated_P=0.,required_gated_Q=0.,
                       absolute_Q_difference_kvar=abs(old['Q_EXEC']),
                       absolute_reactive_energy_difference_kvarh=abs(old['Q_EXEC'])*.25,
                       original_final_actuator=str(rep/final_stage/'ACTUATOR.json'),
                       original_final_actuator_sha=sha(rep/final_stage/'ACTUATOR.json'),
                       movement=[m for m in new_moves if m['mess_id']==old['mess_id']],
                       reason='Original QSAFE acts on early physically-connected MESS during frozen no-PCC slot; strict availability gate forces Q=0')
                local_final.append(w);witnesses.append(w)
        totals['policy_days']+=1;totals['moves']+=len(new_moves)
        totals['baseline_behavior_differences']+=len(base_diffs)
        totals['departure_shifts']+=sum(m['departure_shift_slots']>0 for m in new_moves)
        totals['final_P_gate_violations']+=sum(w['original_P_EXEC']!=0 for w in local_final)
        totals['final_Q_gate_violations']+=sum(w['original_Q_EXEC']!=0 for w in local_final)
        all_rows.append(dict(day=day,policy=policy,moves=len(new_moves),baseline_equal=not base_diffs,
                             baseline_differences=base_diffs,final_gate_compatible=not local_final,
                             final_difference_count=len(local_final),forbidden_counters=out['counters']))
    totals['availability_mask_changes']=len(availability_differences)
    unchanged=[]
    for rec in rule['source_files']:
        after=record(rec['path']);assert after==rec,rec['path'];unchanged.append(after)
    gate_pass=not(totals['baseline_behavior_differences'] or totals['final_P_gate_violations'] or totals['final_Q_gate_violations'])
    assert not gate_pass or totals['availability_mask_changes']==0,'QSAFE_DOMAIN_CHANGE_REQUIRES_FURTHER_EQUIVALENCE_VALIDATION'
    result=dict(status='PASS' if gate_pass else 'FAIL_CLOSE',classification='IEEE123_FINAL_QSAFE_BEHAVIORAL_EQUIVALENCE_FAILURE' if not gate_pass else 'EQUIVALENT',
                totals=totals,IEEE8500_B2_mobility_replay_started=False,IEEE8500_B2_AC_replay_started=False,
                QSAFE_optimization_calls=0,DA_optimization_calls=0,
                current_result='No B2 replacement result created. Original FAIL-CLOSE and all DA/Actual authorities retained.',
                distinction='Baseline command/energy trajectory is byte-value identical on all 124 cases. Full final Actual behavior is not equivalent because an existing QSAFE correction is excluded.',
                limitation='No QSAFE search or electrical replay was performed: a saved final injection violates the new strict eligibility rule, which is already a sufficient counterexample to zero behavioral change.',
                interpretation_requires_resolution='A physically connected early-arrival MESS has no frozen PCC during planned transit. Preserving original QSAFE availability there would be an explicit exception to the strict final P=Q=0 interpretation, not silently adopted.',
                input_files_SHA_and_mtime_unchanged=len(unchanged),rule_SHA=sha(H/'RULE_FREEZE.json'),finished_utc=datetime.now(timezone.utc).isoformat())
    save('IEEE123_REGRESSION_ROWS.json',all_rows);save('IEEE123_FINAL_QSAFE_DIFFERENCE_WITNESSES.json',witnesses)
    save('IEEE123_QSAFE_AVAILABILITY_MASK_DIFFERENCES.json',availability_differences)
    save('INPUT_PRESERVATION_VERIFICATION.json',dict(status='PASS',files=unchanged))
    save('B2_ORIGINAL_COLLISION_REFERENCE.json',dict(source=record(OLD/'B2/ACTUAL_INPUT_FAILURE.json'),evidence=read(OLD/'B2/ACTUAL_INPUT_FAILURE.json')))
    save('GATE_RESULT.json',result)
    save('B2_REQUESTED_METRICS.json',dict(status='NOT_RUN_REGRESSION_GATE_FAILED',
         actual_departure_shift_count=None,max_departure_shift_slots=None,unavailable_command_slots=None,
         missed_nonzero_PQ_command_slots=None,curtailed_active_kWh=None,curtailed_reactive_kvarh=None,
         per_move_departure_arrival_ready=None,final_SoC=None,battery_audit=None,QSAFE_intervention_count=None,
         Vmin=None,Vmax=None,max_line=None,max_transformer_phase_current=None,max_transformer_kVA=None,
         exact_AC_96_slot=None,independent_clean_replay=None,all_frozen_source_SHA_preserved=True,
         null_reason='B2 execution prohibited until IEEE123 full behavioral-equivalence PASS; null is not zero.'))
    report=['# REALIZED_MOBILITY_CAUSAL_AVAILABILITY_GATING — gate result','',
            '**FAIL-CLOSE: IEEE123 final QSAFE behavioral-equivalence gate 실패. IEEE8500 B2 replay는 시작하지 않았습니다.**','',
            '요청한 PCC gating을 최종 Actual Q에도 적용하는 엄격한 해석으로 rule/code/input SHA를 먼저 동결했습니다. '
            '실제 연결되었어도 frozen service_id=None인 계획상 이동/connection-delay slot에서는 QSAFE가 이 zero gate를 덮어쓰지 못하도록 했습니다. '
            '이는 명시한 해석이며, 기존 QSAFE 예외를 임의로 새로 허용하지 않았습니다.','',
            '| 검증 항목 | 결과 |','|---|---:|',
            f"| policy-days / moves | {totals['policy_days']} / {totals['moves']} |",
            f"| baseline command/P/Q/energy/SoC 기록 차이 | {totals['baseline_behavior_differences']} |",
            f"| actual departure shift (IEEE123) | {totals['departure_shifts']} |",
            f"| QSAFE availability mask 변경 vehicle-slot | {len(availability_differences)} |",
            f"| 기존 final Q와 충돌하는 vehicle-slot | {totals['final_Q_gate_violations']} |",'',
            '## 반례','',
            '2025-05-11 / B3 / MESS01 / slot 43 (운영일 10:45). STA01 → STA03 이동의 계획 출발은 slot 41, '
            '계획 ready는 slot 44지만 actual arrival=42.13833158836331, actual ready=43입니다. '
            '따라서 이 slot은 frozen PCC=None / 실제 연결 PCC=STA03입니다. Frozen P=Q=0이지만 기존 QSAFE final Q=-20.39341192385541 kvar입니다. '
            '새 strict gating의 Q=0과 20.39341192385541 kvar (15분 절대 에너지 차이 5.098352980963853 kvarh) 다릅니다.','',
            '이 반례는 late-arrival collision이 아니라 early-arrival QSAFE입니다. 이전 collision audit의 0건 결론과 모순되지 않습니다. '
            '순수 mobility/command baseline은 124건 모두 동일하지만, 최종 QSAFE 동작까지 포함한 zero-change gate는 통과하지 못했습니다. '
            '이미 저장된 final injection이 새 eligibility를 위반하므로 이를 증명하기 위해 QSAFE/AC를 재실행할 필요가 없습니다.','',
            '## IEEE8500 B2 상태','',
            '기존 MESS04 STA08 → IDC05의 actual ready 42가 다음 계획 출발 41보다 늦은 collision evidence를 참조로 보존했습니다. '
            'B2 clean mobility/전기 replay는 gate 이전이라 수행하지 않았습니다. 따라서 departure shifts, missed P/Q, energy, SoC, '
            'QSAFE intervention, Vmin/Vmax, thermal maxima 및 independent replay 결과는 모두 NOT_RUN이며 0/PASS로 보고하지 않습니다.','',
            '동결한 이동식은 `max(planned departure_k, previous move actual ready)`이며 P/Q clock은 이동하지 않습니다. '
            '이번 실행에서는 source text/JSON 조회 및 메모리상의 IEEE123 mobility regression만 수행했습니다. '
            'SUMO/AC/DA/MESS optimization 및 기존 결과 생성은 수행하지 않았습니다.','',
            f"읽은 입력 {len(unchanged)}개 SHA256 및 수정시각 전후 동일. 모든 생성 파일은 이 새 폴더에만 있습니다.",'',
            '진행하려면 계획상 PCC가 없는 early-arrival slot에서도 기존 QSAFE의 실제 연결 PCC 제어를 예외로 유지할지 명확한 rule이 필요합니다. '
            '현재 gate를 임의로 완화하거나 PASS로 바꾸지 않았습니다.','']
    (H/'REPORT.md').write_text('\n'.join(report),encoding='utf-8')
    save('OUTPUT_SHA256_MANIFEST.json',{p.name:sha(p) for p in sorted(H.iterdir()) if p.is_file() and p.name!='OUTPUT_SHA256_MANIFEST.json'})
    print(json.dumps(result,ensure_ascii=True,indent=2),flush=True)

if __name__=='__main__':
    if sys.argv[1:] == ['freeze']:freeze()
    elif sys.argv[1:] == ['regression']:run()
    else:raise SystemExit('Use freeze then regression. No IEEE8500 execution entrypoint before gate PASS.')
