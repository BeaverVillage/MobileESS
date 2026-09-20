from pathlib import Path
import json,hashlib
H=Path(__file__).absolute().parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
r=read(H/'SLOT_RESULT.json');e=r['event']
port=H.parents[1]/'IEEE123_AIDC_STA_RESITING_20260913_154639/worktree/tools/qsafe_v2_shell'
p=read(port/'PREFLIGHT.json')
assert r['status']=='IEEE8500_QSAFE_V2_SEARCH_PASS'
assert p['status']=='IEEE123_QSAFE_V2_SHELL_BINDING_PREFLIGHT_PASS'
assert sha(H/'shared/qsafe_shell.py')==sha(port/'qsafe_shell.py')
for item in read(H/'RULE_FREEZE.json')['files']:assert sha(item['path'])==item['sha256']
shells='\n'.join(f"| {x['shell_index']} | {x['deviation']:.9f} | {x['candidates']} | {x['feasible_candidates']} |" for x in e['shells'])
q=', '.join(f'{x:.12f}' for x in r['selected_Q'])
text=f'''# IEEE8500 QSAFE v2 — legacy exact replay / deviation shells

**IEEE8500_QSAFE_V2_SEARCH_PASS** — May01 B2 Actual slot 43 (44번째 slot).

Checkpoint-based evaluator는 폐기했습니다. 모든 후보는 기존 Electrical.apply/Engine을 사용해 별도 clean context에서 slot 0–43을 chronological replay했습니다. 원래의 확정 prefix 전압 및 tap 상태를 매번 확인했습니다. 같은 shell과 차분 계산의 독립 평가에는 4개 프로세스를 사용했고, 결과 수집은 후보 순서를 보존합니다.

| Shell (0-based) | 기존 Q-deviation (kvar²) | 후보 수 | feasible 수 |
|---|---:|---:|---:|
{shells}

최초 feasible shell은 **2 (세 번째 shell)**입니다. 그 shell 전체를 평가한 뒤 lexicographic Q tie-break로 선택했고, 더 큰 shell은 평가하지 않았습니다. 전체 가능한 coarse domain은 15,625개이며 이번 Q1에서는 3개만 평가했습니다. 동일 deviation은 기존 float objective 값의 정확한 equality로 묶으며 새 반올림/허용오차를 추가하지 않습니다.

Q2는 기존 local_refinement SLSQP의 objective, domain, max_starts=4, separation>0.025, maxiter=75, ftol=1e-10, bound-aware 0.25 kvar central differences를 유지했습니다. 이번에는 feasible seed 1개로 4 iterations, exact 평가 49회를 수행해 정상 종료했습니다. Sobol/Powell/global coarse scanning은 새로운 Q1 shell stage로 대체하며, coarse가 local refinement를 차단하는 global evaluation/time cap은 없습니다. 전역 AC 최적해를 주장하지 않습니다.

| Metric | Result |
|---|---:|
| Shells visited | {e['shells_visited']} |
| Coarse candidates | {e['coarse_candidates']} |
| Frozen-Q initial check | 1 |
| Refinement exact evaluations | {e['refinement_evaluations']} |
| Uncached final full chronological validation | 1 |
| Total exact replay count | {r['total_exact_replay_count']} |
| Total explicit AC solves | {r['total_AC_solves']} |
| Prefix / current-slot solves | {r['prefix_AC_solves']} / {r['current_slot_AC_solves']} |
| Wall time | {r['wall_seconds']:.3f} s |
| Final Q deviation | {r['final_Q_deviation']:.12f} kvar² |
| Vmin / Vmax | {r['Vmin']:.12f} / {r['Vmax']:.12f} pu |
| Max phase-line loading | {r['line_max']:.12f} pu |
| Max transformer phase current | {r['transformer_current_max']:.12f} pu |
| Max transformer kVA loading | {r['transformer_kVA_max']:.12f} pu |

MESS01–06 selected Q (kvar):

```text
[{q}]
```

마지막 uncached full chronological replay가 hard gates를 통과했고, 선택 시 저장한 전압/current/tap 결과와 일치했습니다. P, SOC/energy, route/location, AIDC, background/PV, source/Vreg, tap/cap 설정, ratings, battery parameters는 변경하지 않았습니다. 원래 DA/Actual input SHA 보존 검증이 PASS했습니다. Tap/cap은 매번 native automatic control로 작동합니다.

## IEEE123 binding

**IEEE123_QSAFE_V2_SHELL_BINDING_PREFLIGHT_PASS**. 공통 core SHA256:

`{sha(H/'shared/qsafe_shell.py')}`

IEEE123의 새 준비 worktree `tools/qsafe_v2_shell/`에 동일 core와 activation adapter를 연결했습니다. 기존 full-prefix engine 및 runner bytecode를 유지하면서 Q search 함수만 교체하는 binding을 검증했고, 4대의 coarse domain 625 및 공통 6개 회귀 테스트가 PASS했습니다. `activate.activate(robust_search_module, frozen_worker_module)`가 새 campaign loader의 연결 지점입니다. 과거 frozen snapshot/worker는 수정하지 않았습니다. **IEEE123 production 실행은 0회**이며 기존 새 mapping/input/electrical release gate는 여전히 필요합니다.

## Full B2 Actual

이 slot 검증과 IEEE123 binding 완료 후, 앞서 승인된 B2 전체 Actual을 이 namespace의 `full_actual.py`로 재개했습니다. 이 문서의 PASS와 수치는 **문제 slot 검증 결과**이며 전체 96-slot 완료 주장이 아닙니다. 전체 진행/결과는 `STATUS.json`, `B2/COMPLETE.json`, `B2_ACTUAL_COMPLETE.json`으로 확인합니다. 전체 B2 PASS 전에는 B3를 승격하지 않습니다.
'''
(H/'REPORT.md').write_text(text,encoding='utf-8')
files=[H/name for name in ('runtime.py','legacy_slot.py','slot_runner.py','full_actual.py','test_shell.py','shared/qsafe_shell.py','shared/qsafe_binding.py','RULE_FREEZE.json','SLOT_RESULT.json','SELECTED_EXACT_ARRAYS.npz','EXACT_TRIALS.json','REPORT.md')]+[p for p in port.iterdir() if p.is_file()]
(H/'VALIDATED_SLOT_AND_PORT_SHA.json').write_text(json.dumps(dict(status='PASS',files=[dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for p in files]),indent=2),encoding='utf-8')
print('SLOT_AND_IEEE123_BINDING_REPORT_PASS')
