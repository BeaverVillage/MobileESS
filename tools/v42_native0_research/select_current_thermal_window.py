"""Current saved-CSR static line/window selection, with no solver imports.

The selection pressure is a fixed-control coefficient diagnostic, not an LP
point, an incumbent, a candidate inequality, or an optimization bound receipt.
Only the selected response is expanded using exact stored binary rationals.
"""
from collections import defaultdict, Counter
from fractions import Fraction as F
from pathlib import Path
import gc, hashlib, json, math, re, time
import numpy as np

OUT=Path(__file__).resolve().parent
DEV=Path(r'D:\v42_dense_response_development_repair_20261011')
CASE=DEV/'dates/B2/2025-05-01/attempts/native0_restored/output'
COEFF=Path(r'D:\v42_svr11_may_20261011_16/models/2025-05-01/COEFFICIENTS.npz')
CERT=COEFF.with_name('ELECTRICAL_CERTIFICATE.json')
SOURCE=Path(r'D:\v42_svr11_epoch19_20261011')
WINDOW=8
POOL=5

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def rec(p):
 p=Path(p)
 with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 return dict(path=str(p),sha256=h,bytes=p.stat().st_size)
def exact(x):
 x=F(x)
 return dict(exact=str(x),numerator=str(x.numerator),denominator=str(x.denominator),
  dyadic=x.denominator&(x.denominator-1)==0,approximate=float(x))
def scalar(x):return exact(F(float(x)))
def family(name):return str(name).split('[',1)[0]
def load_stage(prefix):
 with np.load(CASE/(prefix+'_A.npz'),allow_pickle=False) as z:
  a={k:z[k] for k in ('shape','indptr','indices','data')}
 with np.load(CASE/(prefix+'_DATA.npz'),allow_pickle=False) as z:
  d={k:z[k] for k in z.files}
 return a,d
def matrix_sha(a):
 h=hashlib.sha256(np.asarray(a['shape'],dtype='<i8').tobytes())
 for key in ('indptr','indices','data'):
  x=a[key];h.update(x.dtype.str.encode('ascii'));h.update(memoryview(np.ascontiguousarray(x)).cast('B'))
 return h.hexdigest()
def domain_sha(d):
 h=hashlib.sha256()
 for key in sorted(d):
  x=d[key];h.update(key.encode());h.update(x.dtype.str.encode());h.update(np.asarray(x.shape,dtype='<i8').tobytes());h.update(memoryview(np.ascontiguousarray(x)).cast('B'))
 return h.hexdigest()
def terms(a,d,i):
 l,r=a['indptr'][i:i+2]
 return {str(d['names'][j]):F(float(v)) for j,v in zip(a['indices'][l:r],a['data'][l:r])}
def row(a,d,i):
 return dict(row=int(i),name=str(d['row_names'][i]),sense=str(d['sense'][i]),rhs=scalar(d['rhs'][i]),
  NNZ=int(a['indptr'][i+1]-a['indptr'][i]),terms={n:exact(v) for n,v in terms(a,d,i).items()})

def main():
 began=time.perf_counter();OUT.mkdir(parents=True,exist_ok=True)
 validation=read(DEV/'NATIVE0_VALIDATION.json');identity=read(CASE/'SCIENTIFIC_CASE_IDENTITY.json')
 assert validation['PASS'] and validation['case_SHA']==identity['case_sha']
 physical=read(CASE/'EXACT_PHYSICAL_PRESCREEN.json');grid=read(CASE/'EXACT_GRID_OUTER_PRESCREEN.json')
 anchor=read(CASE/'FIXED_AIDC_ANCHOR.json');certificate=read(CERT)
 for r in validation['fresh_input_sources']:assert rec(r['path'])==r
 assert rec(COEFF)==certificate['output']
 with np.load(COEFF,allow_pickle=False) as z:
  branches=list(map(str,z['branch_names']));controls=list(map(str,z['control_names']))
 assert controls==anchor['control_names'] and len(anchor['controls'])==96 and len(controls)==60
 assert all(len(x)==60 and all(float(x[k])==0 for k,n in enumerate(controls) if n.startswith('mess_')) for x in anchor['controls'])
 assert all(r[0]==t and r[2]==controls and r[3]==anchor['controls'][t] for t,r in enumerate(grid['current_coefficients_and_fixed_controls']))
 a,d=load_stage('FULL')
 assert matrix_sha(a)==validation['original_matrix_SHA'] and domain_sha(d)==validation['original_domain_SHA']
 lookup={str(n):j for j,n in enumerate(d['names'])};assert len(lookup)==len(d['names'])
 bind={};faces=np.full((96,len(branches),16),-1,dtype=np.int64);zero=np.zeros(len(d['names']))
 binding_pattern=re.compile(r'response_line_(P|Q|correction)_binding\[(\d+),(\d+)\]')
 face_pattern=re.compile(r'line_thermal_face\[(\d+),(\d+),(\d+)\]')
 for i,label in enumerate(d['row_names']):
  label=str(label)
  if label.startswith('response_line_'):
   m=binding_pattern.fullmatch(label)
   if m:
    kind,t,k=m[1],int(m[2]),int(m[3]);j=lookup[f'response_line_{kind}[{t},{k}]']
    assert d['sense'][i]=='=' and terms(a,d,i)[str(d['names'][j])]==1
    bind[kind,t,k]=i;zero[j]=d['rhs'][i]
  elif label.startswith('line_thermal_face['):
   m=face_pattern.fullmatch(label);t,k,f=map(int,m.groups());faces[t,k,f]=i
 baseline=np.full((96,len(branches)),-np.inf);active=np.full((96,len(branches)),-1,dtype=np.int8)
 for t,k,f in zip(*np.where(faces>=0)):
  i=int(faces[t,k,f]);l,r=a['indptr'][i:i+2]
  js=a['indices'][l:r];vs=a['data'][l:r]
  assert all(str(d['names'][j])=='rho_max' or str(d['names'][j]).startswith(('response_line_P[','response_line_Q[','response_line_correction[')) for j in js)
  value=float(np.dot(vs,zero[js])-d['rhs'][i])
  if value>baseline[t,k]:baseline[t,k]=value;active[t,k]=f
 eligible={}
 for unit in physical['units']:
  eligible[unit['mess']]={t:tuple(s for s in physical['sites'] if f"Pch[{unit['mess']},{s},{t}]" in lookup) for t in range(96)}
 p=F(physical['battery']['p_limit']);q=F(physical['battery']['pcs_kva'])
 def expression(t,k,f):
  i=int(faces[t,k,f]);w=terms(a,d,i);assert w.pop('rho_max')==-1 and d['sense'][i]=='<'
  constant=-F(float(d['rhs'][i]));injection=defaultdict(F);definition_rows=[]
  for name,weight in w.items():
   kind=re.fullmatch(r'response_line_(P|Q|correction)\[\d+,\d+\]',name)[1]
   bi=bind[kind,t,k];bterms=terms(a,d,bi);assert bterms.pop(name)==1
   constant+=weight*F(float(d['rhs'][bi]));definition_rows.append(int(bi))
   for child,stored in bterms.items():
    assert child.startswith(('injection_P[','injection_Q['));injection[child]-=weight*stored
  return i,constant,{n:v for n,v in injection.items() if v},definition_rows
 def physical_relief(t,coefs):
  values={}
  for unit,bytime in eligible.items():
   values[unit]=max((abs(coefs.get(f'injection_P[{s},{t}]',F(0)))*p+abs(coefs.get(f'injection_Q[{s},{t}]',F(0)))*q for s in bytime[t]),default=F(0))
  return sum(values.values(),F(0)),values
 # Five lines with largest current fixed-only pressure are the static search
 # pool, not five tightening candidates. Select one 8-slot interval once.
 pool=sorted([k for k in range(len(branches)) if np.isfinite(baseline[:,k]).any()],key=lambda k:(-float(np.max(baseline[:,k])),k))[:POOL]
 profiles={};ranking=[]
 for k in pool:
  profile=[]
  for t in range(96):
   i,c,coefs,_=expression(t,k,int(active[t,k]));relief,per=physical_relief(t,coefs)
   profile.append(dict(slot=t,face=int(active[t,k]),row=i,fixed_only_pressure=exact(c),
    four_vehicle_rectangle_relief_upper=exact(relief),necessary_row_lower_pressure=exact(c-relief),
    relief_upper_per_MESS={u:exact(v) for u,v in per.items()}))
  starts=range(97-WINDOW);best=max(starts,key=lambda s:(sum(F(x['necessary_row_lower_pressure']['exact']) for x in profile[s:s+WINDOW]),-s))
  score=sum(F(x['necessary_row_lower_pressure']['exact']) for x in profile[best:best+WINDOW])/WINDOW
  ranking.append(dict(branch_index=k,branch_name=branches[k],window_start=best,window_end_exclusive=best+WINDOW,
   mean_necessary_row_lower_pressure=exact(score),fixed_only_peak=exact(max(F(x['fixed_only_pressure']['exact']) for x in profile))))
  profiles[k]=profile
 selected=max(ranking,key=lambda x:(F(x['mean_necessary_row_lower_pressure']['exact']),-x['branch_index']))
 k=selected['branch_index'];start=selected['window_start'];stop=selected['window_end_exclusive'];traces=[]
 print(json.dumps(dict(phase='SELECTED_LINE_WINDOW',selection=selected)),flush=True)
 inj_bind={}
 for i,n in enumerate(d['row_names']):
  if str(n).startswith(('injection_P_binding','injection_Q_binding')):
   for name in terms(a,d,i):
    if name.startswith(('injection_P[','injection_Q[')):inj_bind[name]=i
 for t in range(start,stop):
  i,c,coefs,bis=expression(t,k,int(active[t,k]));raw=defaultdict(F);used=[]
  for name,weight in coefs.items():
   bi=inj_bind[name];it=terms(a,d,bi);assert it.pop(name)==1 and d['rhs'][bi]==0;used.append(bi)
   for child,v in it.items():assert child.startswith(('Pch[','Pdis[','Q['));raw[child]-=weight*v
  raw={n:v for n,v in raw.items() if v}
  traces.append(dict(slot=t,face=int(active[t,k]),actual_thermal_row=row(a,d,i),response_bindings=[row(a,d,bi) for bi in bis],
   fixed_only_affine_constant=exact(c),exact_injection_coefficients={n:exact(v) for n,v in sorted(coefs.items())},
   exact_raw_Pch_Pdis_Q_coefficients={n:exact(v) for n,v in sorted(raw.items())},
   injection_binding_rows=used,projected_raw_NNZ=len(raw),projected_expression_uses_only_current_slot=True))
 selected_thermal=[int(faces[t,k,f]) for t in range(start,stop) for f in range(16)]
 energy=[];endpoints=[];all_travel_terms=0;pcs=[]
 first_unit=next(iter(eligible));first_site=eligible[first_unit][start][0]
 pcs_target=lookup[f'Pdis[{first_unit},{first_site},{start}]']
 pcs_q_target=lookup[f'Q[{first_unit},{first_site},{start}]']
 for i,n in enumerate(d['row_names']):
  fam=family(n)
  if fam=='energy_balance':
   ts=terms(a,d,i);soc=[name for name in ts if name.startswith('SOC[')]
   assert len(soc)==2
   label=re.fullmatch(r'SOC\[([^,]+),(\d+)\]',max(soc,key=lambda n:int(n.rsplit(',',1)[1][:-1])))
   unit,t=label[1],int(label[2])-1
   all_travel_terms+=sum(name.startswith('arc[') for name in ts)
   if start<=t<stop:
    counts=Counter(family(name) for name in ts)
    energy.append(dict(mess=unit,slot=t,row=int(i),NNZ=len(ts),family_support=dict(counts),
     distinct_stored_Pch_coefficients=[scalar(float(x)) for x in sorted(set(v for n,v in ts.items() if n.startswith('Pch[')))],
     distinct_stored_Pdis_coefficients=[scalar(float(x)) for x in sorted(set(v for n,v in ts.items() if n.startswith('Pdis[')))],
     travel_terms=count if (count:=counts.get('arc',0)) else 0))
  elif fam in ('initial_SOC','terminal_SOC'):endpoints.append(row(a,d,i))
  elif fam=='PCS16':
   l,r=a['indptr'][i:i+2]
   if pcs_target in a['indices'][l:r] or pcs_q_target in a['indices'][l:r]:pcs.append(row(a,d,i))
 assert len(pcs)==16
 soc_boxes={}
 for unit in eligible:
  soc_boxes[unit]={t:dict(lower=scalar(d['lower'][lookup[f'SOC[{unit},{t}]']]),upper=scalar(d['upper'][lookup[f'SOC[{unit},{t}]']])) for t in (start,stop,96)}
 original_selected={str(d['row_names'][i]):row(a,d,i) for i in selected_thermal}
 total=validation['sizes']['Dense']['nnz'];max_nnz=math.floor(total*.005)
 selected_support=dict(thermal_rows=len(selected_thermal),thermal_NNZ=sum(x['NNZ'] for x in original_selected.values()),
  active_face_rows=len(traces),active_face_auxiliary_terms=sum(x['actual_thermal_row']['NNZ']-1 for x in traces),
  exact_raw_projected_NNZ=sum(x['projected_raw_NNZ'] for x in traces),
  selected_window_energy_balance_rows=len(energy),selected_window_energy_balance_NNZ=sum(x['NNZ'] for x in energy),
  selected_window_travel_coefficient_occurrences=sum(x['travel_terms'] for x in energy),
  max_additional_rows=256,max_additional_NNZ=max_nnz,current_Dense_NNZ=total,
  one_projected_8slot_raw_relief_row_NNZ_upper=sum(x['projected_raw_NNZ'] for x in traces),
  whole_horizon_travel_energy_coefficient_occurrences=all_travel_terms,
  whole_horizon_travel_terms_exceed_budget=all_travel_terms>max_nnz)
 print(json.dumps(dict(phase='SELECTED',selection=selected,support=selected_support)),flush=True)
 del a,d,lookup,bind,faces,zero,inj_bind;gc.collect()
 stages={}
 for prefix,msha,dsha in [('C3A',identity['C3A_matrix_sha'],identity['C3A_domain_sha']),('DENSE_RESPONSE',identity['selected_matrix_sha'],identity['selected_domain_sha'])]:
  a,d=load_stage(prefix);assert matrix_sha(a)==msha and domain_sha(d)==dsha;kept={}
  for i,n in enumerate(d['row_names']):
   n=str(n)
   if n in original_selected:
    r=row(a,d,i);old=original_selected[n]
    assert (r['sense'],r['rhs'],r['terms'])==(old['sense'],old['rhs'],old['terms'])
    kept[n]=r
  stages[prefix]=dict(selected_line_window_retained_rows=len(kept),selected_line_window_retained_NNZ=sum(x['NNZ'] for x in kept.values()),
   exact_original_thermal_rows_retained_unchanged=True,selected_names=sorted(kept),missing_names=sorted(set(original_selected)-set(kept)))
  del a,d;gc.collect()
 result=dict(PASS=True,schema='CURRENT_STATIC_ONE_THERMAL_LINE_WINDOW_SELECTION_V1',
  current_validation_source_SHA=validation['source_SHA'],current_case_SHA=validation['case_SHA'],
  source19_base_commit='497609',selection=selected,window_slots=list(range(start,stop)),window_hours=WINDOW*.25,
  static_selection_policy='Top five current fixed-only peak line faces; one 8-slot window maximizing mean necessary pressure after generous four-vehicle reachable-site P/Q rectangles; exact stored rows select and define final result',
  static_selection_is_not_proven_actual_optimum_critical_line=True,
  selection_search_pool=ranking,selected_line_all96_slot_profile=profiles[k],exact_selected_traces=traces,
  current_control_schema=dict(controls=60,AIDC_fixed_kW=12,MESS_site_net_P_kW=24,MESS_site_Q_kvar=24,
   MESS_units=4,slots=96,connect_sites=physical['sites'],control_names=controls,
   net_P_definition='injection_P=sum(Pdis-Pch)',net_Q_definition='injection_Q=sum(Q)',
   fixed_zero_MESS_axes_are_not_an_optimization_point=True),
  battery=physical['battery'],initial_sites=physical['initial'],SOC_endpoint_boxes=soc_boxes,
  original_DAG_contract=dict(stay='(site,t)->(site,t+1)',travel='(source,depart)->(destination,connect)',
   travel_energy_debit='Departure slot only; exact stored coefficient',unit_source='Initial site at slot0',
   terminal_sink='Any site at slot96; unit terminal_location sum=1',return_to_initial_site_required=False,
   terminal_SOC_equals_initial=True),
  actual_SOC_energy_row_support=energy,actual_initial_and_terminal_SOC_rows=endpoints,
  exact_stored_PCS16_fixture=dict(mess=first_unit,site=first_site,slot=start,rows=pcs,
   all_16_faces_and_tiny_nonzero_stored_coefficients_preserved=True),
  rebound_and_terminal_policy='Charging at any reachable site and travel/return are preserved. Q relief carries no direct SOC debit. Window energy sum must retain charging, nonnegative actual travel debits, actual stored efficiency coefficients and start/end SOC; such a plain equality sum is already LP-valid and not a new tightening.',
  exact_fraction_arithmetic_used=True,coefficients_pruned_by_threshold=False,
  additional_rows=0,additional_columns=0,additional_binary=0,additional_NNZ=0,
  sparse_support_and_budget=selected_support,selected_C3A_and_Dense_stage_presence=stages,
  current_verified_LP_point_available=False,current_LP_violation_witness=None,LB_improvement_proven=False,
  current_root_status='ROOT_INCOMPLETE',older_Source_LP_points_bounds_or_starts_read=0,
  Native_optimize_calls=0,Gurobi_presolve_calls=0,model_builds=0,
  candidate_generation_or_adoption=False,history_audit_completion_required_before_candidates=True,
  receipts=[rec(CASE/'FULL_A.npz'),rec(CASE/'FULL_DATA.npz'),rec(CASE/'C3A_A.npz'),rec(CASE/'C3A_DATA.npz'),
   rec(CASE/'DENSE_RESPONSE_A.npz'),rec(CASE/'DENSE_RESPONSE_DATA.npz'),rec(CASE/'FIXED_AIDC_ANCHOR.json'),
   rec(CASE/'EXACT_GRID_OUTER_PRESCREEN.json'),rec(CASE/'EXACT_PHYSICAL_PRESCREEN.json'),rec(CERT),rec(COEFF),
   rec(DEV/'NATIVE0_VALIDATION.json'),*validation['fresh_input_sources']],wall_seconds=time.perf_counter()-began)
 target=OUT/'CURRENT_THERMAL_LINE_WINDOW_STATIC_AUDIT.json';target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(PASS=True,path=str(target),selection=selected,support=selected_support,stages={k:{x:v[x] for x in ['selected_line_window_retained_rows','selected_line_window_retained_NNZ']} for k,v in stages.items()},wall_seconds=result['wall_seconds'])),flush=True)
if __name__=='__main__':main()
