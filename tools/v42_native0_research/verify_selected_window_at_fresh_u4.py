"""Read-only direct selected-Dense row evaluation at the authorized fresh U4."""
from fractions import Fraction as F
from pathlib import Path
import hashlib, json
import numpy as np
from select_current_thermal_window import OUT,CASE,DEV,read,rec,exact,load_stage,matrix_sha,domain_sha

def main():
 packet=read(OUT/'CURRENT_THERMAL_LINE_WINDOW_STATIC_AUDIT.json')
 validation=read(DEV/'NATIVE0_VALIDATION.json');point_path=CASE/'FRESH_U4/RAW_00.npz'
 replay_path=point_path.with_suffix('.REPLAY.json');replay=read(replay_path)
 assert replay['PASS'] and replay['case_sha']==packet['current_case_SHA']==validation['case_SHA']
 assert replay['point_path']==str(point_path) and rec(point_path)['sha256']==replay['point_file_sha256']
 assert replay['original_matrix_and_96_slot_physical_replay']['PASS']
 assert replay['strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact']
 assert not replay['point_rounding'] and not replay['point_clipping']
 with np.load(point_path,allow_pickle=False) as z:x=z['point']
 assert hashlib.sha256(x.tobytes()).hexdigest()==replay['point_vector_sha256'] and x.shape==(354277,)
 a,d=load_stage('DENSE_RESPONSE')
 assert matrix_sha(a)==validation['selected_matrix_SHA'] and domain_sha(d)==validation['selected_domain_SHA']
 names=packet['selected_C3A_and_Dense_stage_presence']['DENSE_RESPONSE']['selected_names']
 selected=set(names);rho_index=list(d['names']).index('rho_max');rho=F(float(x[rho_index]));records=[]
 for i,n in enumerate(d['row_names']):
  n=str(n)
  if n not in selected:continue
  l,r=a['indptr'][i:i+2];terms=dict(zip(map(int,a['indices'][l:r]),map(float,a['data'][l:r])))
  assert terms[rho_index]==-1 and d['sense'][i]=='<'
  lhs=sum((F(v)*F(float(x[j])) for j,v in terms.items()),F(0));residual=lhs-F(float(d['rhs'][i]))
  axes=list(map(int,n.split('[',1)[1][:-1].split(',')))
  records.append(dict(row=int(i),name=n,slot=axes[0],branch_index=axes[1],face=axes[2],
   pressure=exact(residual+rho),exact_stored_row_residual=exact(residual)))
 assert len(records)==80 and set(r['name'] for r in records)==selected
 slots=[]
 for t in packet['window_slots']:
  rows=[r for r in records if r['slot']==t];best=max(rows,key=lambda r:F(r['pressure']['exact']))
  slots.append(dict(slot=t,retained_faces=len(rows),maximum_pressure=best['pressure'],active_face=best['face'],
   margin_below_fresh_U4_rho=exact(rho-F(best['pressure']['exact']))))
 pressure=max(F(r['pressure']['exact']) for r in records)
 receipt=dict(PASS=True,schema='AUTHORIZED_FRESH_U4_SELECTED_CURRENT_THERMAL_WINDOW_DIRECT_READ_V1',
  source_SHA=validation['source_SHA'],case_SHA=validation['case_SHA'],selection=packet['selection'],
  fresh_U4_rho=exact(rho),selected_window_peak_pressure=exact(pressure),
  selected_window_mean_slot_peak_pressure=exact(sum((F(r['maximum_pressure']['exact']) for r in slots),F(0))/len(slots)),
  per_slot=slots,all80_retained_actual_Dense_row_evaluations=records,
  actual_current_high_load_selected_line_confirmed=bool(pressure>F(1,2)),
  fresh_U4_original_FULL_and_96slot_physical_replay_PASS=True,
  raw_current_integer_feasible_point_not_an_unrestricted_Root_LP_point=True,
  current_verified_completed_unrestricted_Root_LP_point_available=False,
  current_LP_violation_witness=None,LB_improvement_proven=False,
  source18r_generation_and_matrix_authorities_preserved=True,
  point_lift_or_model_builds=0,Native_calls=0,Gurobi_presolve_calls=0,
  older_Source_points_bounds_or_starts_read=0,
  receipts=[rec(point_path),rec(replay_path),rec(CASE/'DENSE_RESPONSE_A.npz'),rec(CASE/'DENSE_RESPONSE_DATA.npz'),rec(DEV/'NATIVE0_VALIDATION.json')])
 target=OUT/'CURRENT_SELECTED_LINE_WINDOW_FRESH_U4_CONFIRMATION.json'
 target.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 packet['current_verified_LP_point_available']=False
 packet['current_LP_point_availability_scope']='Completed unrestricted Root LP relaxation point; fresh accepted integer U4 point is separately checked, with no lift/model or old point reuse'
 packet['fresh_U4_selected_window_readback']=rec(target)
 packet['fresh_U4_point_read_authorization']='Parent relayed current explicit user permission for read-only fresh Source18r U4; this is not an older-Source point'
 (OUT/'CURRENT_THERMAL_LINE_WINDOW_STATIC_AUDIT.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(PASS=True,path=str(target),selection=receipt['selection'],fresh_U4_rho=float(rho),
  window_peak=float(pressure),window_mean=float(F(receipt['selected_window_mean_slot_peak_pressure']['exact'])),slots=slots)),flush=True)
if __name__=='__main__':main()
