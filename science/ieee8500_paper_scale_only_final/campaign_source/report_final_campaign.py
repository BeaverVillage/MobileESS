"""Produce the final, exact-scope paper-PCC May-1 comparison after all gates."""
from bootstrap import *
import csv


ORDER=('B0','B2','B1','B3')
EXACT={
 'B0':'B0/DA_exact/AC_VALIDATION.json',
 'B2':'B2/independent_clean_exact/AC_VALIDATION.json',
 'B3':'B3/final_exact/AC_VALIDATION.json',
 'B1':'B1/final_exact/AC_VALIDATION.json',
}


def runtime(policy):
 if policy=='B0':return (read(H/'B0_RUNTIME_RECORD.json') or {}).get('wall_seconds') if (H/'B0_RUNTIME_RECORD.json').exists() else None
 if policy=='B2':return read(H/'B2/COMPLETE.json').get('wall_seconds')
 if policy=='B3':return sum(read(H/f'{name}_STAGE_RUNTIME.json')['wall_seconds'] for name in ('B3_A1_AIDC','B3_M1_ROUTE_PQ','B3_A2_AIDC','B3_M2_PQ'))
 return read(H/'B1_RUNTIME.json')['wall_seconds']


def main():
 rows=[]
 for policy in ORDER:
  da=read(H/EXACT[policy]);fresh=read(H/policy/'Fresh/AC_VALIDATION.json')
  actual=read(H/'Actual'/policy/'COMPLETE.json')
  assert da['status']==fresh['status']=='PASS' and actual['AC_feasible']
  slots=da['slots'];critical=max(slots,key=lambda row:row['max_phase_line_loading_pu'])
  planning=(read(H/policy/'FINAL_AUTHORITY.json')['P1'] if policy!='B0'
            else evaluate_grid(Coefficients(),np.c_[np.load(H/'MAY01_B0_AIDC_POWER.npz')['pcc'],np.zeros((96,48))],AX['nodes'])['rho_max'])
  row=dict(policy=policy,Planning_rho=planning,
           DA_exact_rho=da['metrics']['max_phase_line_loading_pu'],
           Fresh_rho=fresh['metrics']['max_phase_line_loading_pu'],
           Actual_rho=actual['summary']['max_phase_line_loading_pu'],
           Vmin=da['metrics']['Vmin_pu'],Vmax=da['metrics']['Vmax_pu'],
           transformer_current=da['metrics']['max_transformer_phase_current_pu'],
           transformer_kva=da['metrics']['max_transformer_winding_kva_pu'],
           critical_line=critical['line_witness'],critical_slot=critical['slot'],
           runtime_seconds=runtime(policy),exact_AC_PASS=True)
  rows.append(row)
 by={r['policy']:r for r in rows}
 reductions={scope:{name:by[left][scope]-by[right][scope]
   for name,left,right in (('B0_minus_B1','B0','B1'),('B0_minus_B2','B0','B2'),
                            ('B0_minus_B3','B0','B3'),('B2_minus_B3','B2','B3'))}
   for scope in ('DA_exact_rho','Actual_rho')}
 certs=[read(path) for path in (H/'MESS_grid_certificates').glob('*.json')]
 assert certs and all(c['status']=='PASS' and c['domain_changes']==0 for c in certs)
 active_certificates=[]
 for stage in ('B2','B3_M1'):
  root=H/stage/'active_grid'
  calls=sorted(path for path in root.glob('call_*') if path.is_dir())
  assert calls,(stage,'NO_ACTIVE_GRID_CALLS')
  for call in calls:
   seed=read(call/'SEED_BUILD.json')
   closure=read(call/'FULL_SEPARATION_CLOSURE.json')
   assert seed['full_logical_rows']==31945536 and seed['no_active_row_cap']
   assert closure['status']=='PASS' and closure['checked_rows']==31945536
   assert closure['maximum_violation']<=closure['tolerance']
   assert closure['termination_authority']=='PAPER_SOLVER_TERMINATION'
   assert closure['solver_status'] in (2,9,13,16)
   assert closure['no_active_row_cap'] and closure['no_route_pruning']
   active_certificates.append(record(call/'FULL_SEPARATION_CLOSURE.json'))
 for p in ('B2','B3'):
  final=read(H/p/'FINAL_AUTHORITY.json');slots=final['trajectory_slots']
  assert len(slots)==576
  by[p]['MESS_max_abs_P_kW']=max(abs(r['p_kw']) for r in slots)
  by[p]['MESS_max_abs_Q_kvar']=max(abs(r['q_kvar']) for r in slots)
  by[p]['SOC_min']=min(r['soc_fraction'] for r in slots)
  by[p]['SOC_max']=max(r['soc_fraction'] for r in slots)
  by[p]['route_count']=len({(r['mess_id'],tuple(r.get('route_link_ids',[]))) for r in slots if r.get('route_link_ids')})
 report=dict(status='PASS',date='2025-05-01',policy_order=list(ORDER),results=rows,
  reductions=reductions,full_separation_certificate_files=len(certs)+len(active_certificates),
  sparse_full_separation_certificates=active_certificates,
  full_separation_closure='PASS' if all(r['exact_AC_PASS'] for r in rows) else 'FAIL',
  PAPER_PCC_CONFIG_USED=True,BG_SCALE=.552,AIDC_ABSOLUTE_SCALE=2.4,MESS_SCALE=2.,
  RESITING_USED=False,FEEDER_MODIFIED=False,AIDC_DOUBLE_SCALING=False,
  B2_SEARCH_DOMAIN_CHANGED=False,workers=1,threads=4,
  MESS_termination='PAPER_SOLVER_TERMINATION',
  MESS_MIPGap_target=.001,MESS_TimeLimit_seconds=600.,MESS_WorkLimit_tiers=[60.,180.,300.],
  termination_authority=record(H/'PAPER_SOLVER_TERMINATION_AUTHORITY.json'),
  paper_overlay_sha256=sha(H/'IEEE8500_PCC_Overlay.dss'),
  preflight=record(H/'B2_PERFORMANCE_PREFLIGHT.json'),
  actual_controller='original violation-triggered Q-only')
 save(H/'FINAL_CAMPAIGN_RESULT.json',report)
 with (H/'FINAL_CAMPAIGN_TABLE.csv').open('w',encoding='utf-8',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
  writer.writeheader();writer.writerows(rows)
 print('FINAL_CAMPAIGN_PASS',report['reductions'],flush=True)


if __name__=='__main__':main()
