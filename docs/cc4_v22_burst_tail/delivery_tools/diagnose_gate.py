"""Historical gate feasibility diagnostic; never changes a threshold or selection."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
f=pd.read_parquet(ROOT/'PREDICTIONS.parquet');p=json.loads((ROOT/'PROTOCOL.json').read_text(encoding='utf-8'));b=p['burst_threshold']['value'];gate=p['risk_gate']['probability'];rows=[]
for role,g in f[f.model.eq('C0')].groupby('role'):
 burst=g.actual>b;active=g.risk>=gate;covered=g.actual<=g.Q90
 rows.append(dict(role=role,N_burst=int(burst.sum()),gated_burst=int((burst&active).sum()),baseline_covered_burst_outside_gate=int((burst&covered&~active).sum()),
  gate_recall=float(active[burst].mean()),optimistic_burst_coverage_ceiling=float((active|covered)[burst].mean()),
  explanation='If every gated burst were covered, with all outside-gate predictions fixed to C0; fixed-gate diagnostic only, no claim about alternative gates or features'))
pd.DataFrame(rows).to_csv(ROOT/'GATE_FEASIBILITY.csv',index=False)
lines=['# 고정 risk gate의 historical 진단','',
 '아래 ceiling은 gate 안의 모든 burst를 완벽하게 덮더라도, gate 밖 예측을 C0로 유지할 때 달성 가능한 optimistic burst coverage다. 실제 outcome을 이용한 사후 진단이며 선택·threshold·예측을 변경하지 않는다. 다른 gate/feature의 가능성을 제한하는 주장이 아니다.','',
 '| 구간 | burst 수 | gate 내 burst | 밖에서 C0가 덮은 burst | gate recall | optimistic ceiling |','|---|---:|---:|---:|---:|---:|']
for r in rows:lines.append(f"| {r['role']} | {r['N_burst']} | {r['gated_burst']} | {r['baseline_covered_burst_outside_gate']} | {r['gate_recall']:.2%} | {r['optimistic_burst_coverage_ceiling']:.2%} |")
lines+=['','May C1의 전체 coverage·positive coverage·requirement ratio는 선호 범위를 만족하고 pinball point estimate도 C0보다 낮다. 그러나 burst coverage는 최소 60%에 미달하며 pinball delta CI가 0을 포함한다. C2도 burst minimum에 미달하고 pinball point estimate가 소폭 높다. DEV/CAL에서 고정한 C0 유지 결정을 바꾸지 않는다.','',
 'Burst coverage delta의 95% CI가 양수인 사실과 운영 minimum을 충족한다는 주장은 구분한다. 여기서는 작은 burst 개선은 관측되지만, 고정 risk gate가 포착하는 burst 수가 부족하다.','',
 '![고정 모델 비교와 paired CI](COMPARISON.png)','']
(ROOT/'GATE_DIAGNOSTIC_KO.md').write_text('\n'.join(lines),encoding='utf-8')
(ROOT/'GATE_DIAGNOSTIC_RECEIPT.json').write_text(json.dumps(dict(input_sha256=hashlib.sha256((ROOT/'PREDICTIONS.parquet').read_bytes()).hexdigest(),post_evaluation_display_only=True,threshold_changed=False,selection_changed=False),indent=2),encoding='utf-8')
