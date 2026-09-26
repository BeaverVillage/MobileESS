from pathlib import Path
import json,csv,time
P=Path(__file__).absolute().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
 gate=read(P/'ALIGNED_PLANNING_GATE.json');actual=read(P/'Actual/CAMPAIGN_COMPLETE.json');rows=[]
 for policy in ('B0','B1','B2','B3'):
  d=gate['policies'][policy];a=actual['policies'][policy];s=a['summary'];fresh=read(Path(d['Fresh']['path']));w=max(fresh['slots'],key=lambda x:x['max_phase_line_loading_pu'])
  roles=['B1'] if policy=='B1' else ['B2'] if policy=='B2' else ['B1','B3_M1','B3_A1','B3_MF'] if policy=='B3' else []
  runtimes={role:read(P/(role+'_RUNTIME.json')).get('wall_seconds') if (P/(role+'_RUNTIME.json')).exists() else None for role in roles}
  rows.append(dict(policy=policy,Planning_rho=d['Planning_rho'],Fresh_rho=d['Fresh_rho'],Actual_rho=s['max_phase_line_loading_pu'],Vmin=s['Vmin_pu'],Vmax=s['Vmax_pu'],Fresh_critical_line=w['line_witness'],Fresh_critical_slot=w['slot'],Actual_runtime=a['runtime_seconds'],Q_interventions=a['Q_interventions'],P_interventions=a['P_interventions'],max_abs_delta_P=a['max_abs_delta_P_DA'],energy_recovery_kwh=a['energy_recovery_kwh'],AC_PASS=a['AC_PASS'],surrogate_exact_error=d['Fresh_rho']-d['Planning_rho'],stage_runtimes=json.dumps(runtimes)))
 with (P/'ALIGNED_RESULTS.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 v=dict(status='COMPLETE',all_AC_PASS=all(r['AC_PASS'] for r in rows),rows=rows,ordering_natural_DA=all(rows[i]['Fresh_rho']>rows[i+1]['Fresh_rho'] for i in range(3)),ordering_natural_Actual=all(rows[i]['Actual_rho']>rows[i+1]['Actual_rho'] for i in range(3)),comparison_scope='IEEE123 aligned Planning semantics; IEEE8500 compute budgets; identical Q-first/minimal-P controller source',completed_unix=time.time())
 for name in ('ALIGNED_FINAL_RESULT.json','FINAL_EXPORT_COMPLETE.json'):(P/name).write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
if __name__=='__main__':main()
