import json,csv,hashlib
from pathlib import Path
H=Path(__file__).absolute().parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def main():
 from audit_inputs import main as audit
 audit()
 rows=[]
 for policy,da,fresh in [('B0','B0_REPLAY/AC_VALIDATION.json','B0/Fresh/AC_VALIDATION.json'),('B1','B1/final_exact/AC_VALIDATION.json','B1/Fresh/AC_VALIDATION.json'),('B2','B2/final_exact/AC_VALIDATION.json','B2/Fresh/AC_VALIDATION.json'),('B3','B3/final_exact/AC_VALIDATION.json','B3/independent_clean_exact/AC_VALIDATION.json')]:
  d=read(H/da);f=read(H/fresh)
  if policy=='B2' and d['status']!='PASS':d=read(H/'B2/physical_closure/accepted_clean_exact/AC_VALIDATION.json')
  witness=max(f['slots'],key=lambda r:r['max_phase_line_loading_pu'])
  runtime=sum(read(H/(role+'_RUNTIME.json'))['wall_seconds'] for role in (['B3_M1','B3_A1','B3_MF'] if policy=='B3' else [policy])) if policy!='B0' else d['wall_seconds']+f['wall_seconds']
  planning=read(H/policy/'FINAL_AUTHORITY.json')['P1'] if policy!='B0' else d['metrics']['max_phase_line_loading_pu']
  rows.append(dict(policy=policy,DA_planning_rho=planning,DA_rho=d['metrics']['max_phase_line_loading_pu'],Fresh_rho=f['metrics']['max_phase_line_loading_pu'],Vmin=f['metrics']['Vmin_pu'],Vmax=f['metrics']['Vmax_pu'],transformer_current=f['metrics']['max_transformer_phase_current_pu'],transformer_kVA=f['metrics']['max_transformer_winding_kva_pu'],critical_slot=witness['slot'],critical_line=witness['line_witness'],converged_slots=sum(r['converged'] for r in f['slots']),controls_settled_slots=sum(r['controls_settled'] for r in f['slots']),total_runtime_seconds=runtime,DA_runtime=d['wall_seconds'],Fresh_runtime=f['wall_seconds'],AC_PASS=d['status']==f['status']=='PASS'))
 with (H/'FULL_DA_FRESH_METRICS.csv').open('w',newline='',encoding='utf-8-sig') as fp:w=csv.DictWriter(fp,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
 rho=[r['Fresh_rho'] for r in rows];strict=all(a-b>1e-6 for a,b in zip(rho,rho[1:]));ac=all(r['AC_PASS'] for r in rows)
 authority_pass=read(H/'INPUT_AUTHORITY_AUDIT.json')['status']=='PASS'
 candidate=authority_pass and ac and strict and rho[-1]<.90
 result=dict(rows=rows,physical_PASS=ac,strict_ordering=strict,B3_below_090=rho[-1]<.90,Actual_run=False,placement_or_scale_changed_after_results=False,spatial_audit_status='SUPERSEDED_NONBLOCKING_DIAGNOSTIC',spatial_correlation_required=False,transport_authority_preserved=authority_pass,cross_layer_mapping_valid=authority_pass,electrical_freeze_candidate=candidate,infrastructure_freeze_candidate=candidate,Actual_authorized=False)
 (H/'FULL_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
if __name__=='__main__':main()
