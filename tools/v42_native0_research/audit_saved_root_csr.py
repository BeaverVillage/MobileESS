"""Read one saved current CSR at a time; no Gurobi, models, presolve or A*A'."""
from collections import Counter
from pathlib import Path
import csv,gc,json,math,re,time
import numpy as np
from select_current_thermal_window import CASE,DEV,read,rec,load_stage,matrix_sha,domain_sha
OUT=Path(__file__).resolve().parent/'root_barrier'

def distribution(x):
 x=np.asarray(x)
 return dict(count=len(x),minimum=float(np.min(x)) if len(x) else None,maximum=float(np.max(x)) if len(x) else None,
  mean=float(np.mean(x)) if len(x) else None,percentile50=float(np.percentile(x,50)) if len(x) else None,
  percentile90=float(np.percentile(x,90)) if len(x) else None,percentile99=float(np.percentile(x,99)) if len(x) else None)
def fam(n):return str(n).split('[',1)[0]
def choose2(n):return int(n)*(int(n)-1)//2
def write(name,x):(OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def rho_certificate(a,d,v):
 j=list(d['names']).index('rho_max');p=np.flatnonzero(a['indices']==j)
 rows=np.searchsorted(a['indptr'],p,side='right')-1;counts=Counter();families=Counter();senses=Counter();records=[]
 for i in rows:
  name=str(d['row_names'][i]);m=re.fullmatch(r'line_thermal_face\[(\d+),(\d+),(\d+)\]',name)
  assert m is not None
  counts[int(m[1])]+=1;families[fam(name)]+=1;senses[str(d['sense'][i])]+=1
 assert set(counts)==set(range(96)) and len(rows)==333689 and all(a['data'][p]==-1)
 assert d['types'][j]=='C' and d['objective'][j]==1 and d['lower'][j]==0 and d['upper'][j]==1
 assert senses=={'<':333689}
 before=choose2(len(rows));within=sum(choose2(n) for n in counts.values());after=sum(choose2(n+1) for n in counts.values())+choose2(96)
 certificate=dict(PASS=True,schema='ACTUAL_CURRENT_DENSE_RHO_INCIDENCE_CERTIFICATE_V1',source_SHA=v['source_SHA'],case_SHA=v['case_SHA'],
  selected_matrix_SHA=v['selected_matrix_SHA'],selected_domain_SHA=v['selected_domain_SHA'],
  rho_column=dict(index=j,name='rho_max',type='C',objective_exact='1',lower_exact='0',upper_exact='1'),
  actual_incident_rows=len(rows),incident_families=dict(families),incident_senses=dict(senses),exact_stored_rho_coefficients=['-1'],
  all_incident_rows_replaced_only_current_time_line_thermal_faces=True,other_rho_equalities_modes_or_incidents=0,
  per_slot_row_counts={str(t):counts[t] for t in range(96)},all96slots_nonempty=True,
  proposed_static_split=dict(new_continuous_columns=96,new_rows=96,new_binary=0,new_NNZ=192,
   original_global_rho_degree=333689,new_global_rho_degree=96,new_local_rho_degrees={str(t):counts[t]+1 for t in range(96)},
   new_local_bounds=[0,1],new_local_objective=0,new_link_coefficients=['1','-1'],new_link_sense='<',new_link_rhs_exact='0',
   rows=715692,columns=354373,binary=9322,NNZ=7911561,actual_matrix_constructed=False),
  purely_structural_uncoalesced_rho_column_row_pair_proxy=dict(before=before,original_within_slot=within,
   original_cross_slot=before-within,after=after,reduction=before-after,
   ignores_duplicate_row_pairs_dense_column_treatment_ordering_and_presolve=True,
   actual_factor_NZ_Ops_memory_or_root_runtime_gain_measured=False),
  Native_calls=0,Gurobi_presolve_calls=0,model_builds=0,source_edits=0,
  receipts=[rec(CASE/'DENSE_RESPONSE_A.npz'),rec(CASE/'DENSE_RESPONSE_DATA.npz'),rec(DEV/'NATIVE0_VALIDATION.json')])
 write('CURRENT_DENSE_RHO_COLUMN_CERTIFICATE.json',certificate)
 with (OUT/'CURRENT_DENSE_RHO_PER_SLOT.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.writer(f);w.writerow(['slot','actual_old_rho_rows','proposed_local_rho_degree']);w.writerows((t,counts[t],counts[t]+1) for t in range(96))
 print(json.dumps(dict(phase='RHO_CERTIFICATE_SAVED',path=str(OUT/'CURRENT_DENSE_RHO_COLUMN_CERTIFICATE.json'),index=j,rows=len(rows),slots=96)),flush=True)
 return certificate

def roundtrip_scaling(a,d,shift,kind):
 smallest=math.inf;largest=0.;checked=0
 for lo in range(0,len(d['row_names']),4096):
  hi=min(lo+4096,len(d['row_names']));start,stop=map(int,(a['indptr'][lo],a['indptr'][hi]))
  ss=np.repeat(shift[lo:hi],np.diff(a['indptr'][lo:hi+1])) if kind=='row' else shift[a['indices'][start:stop]]
  old=a['data'][start:stop];new=np.ldexp(old,ss);back=np.ldexp(new,-ss)
  assert np.isfinite(new).all() and np.all(new!=0) and np.array_equal(old.view(np.uint64),back.view(np.uint64))
  if len(new):smallest=min(smallest,float(np.min(np.abs(new))));largest=max(largest,float(np.max(np.abs(new))))
  checked+=len(new)
 extra={}
 if kind=='row':
  old=d['rhs'];new=np.ldexp(old,shift);assert np.isfinite(new).all() and np.array_equal(old.view(np.uint64),np.ldexp(new,-shift).view(np.uint64))
  extra=dict(RHS_bit_exact_roundtrip=True,positive_shift_rows=int(np.count_nonzero(shift>0)),negative_shift_rows=int(np.count_nonzero(shift<0)))
 else:
  for key in ('lower','upper'):
   old=d[key];finite=np.isfinite(old);new=np.ldexp(old[finite],-shift[finite]);assert np.isfinite(new).all() and np.array_equal(old[finite].view(np.uint64),np.ldexp(new,shift[finite]).view(np.uint64))
  old=d['objective'];new=np.ldexp(old,shift);assert np.isfinite(new).all() and np.array_equal(old.view(np.uint64),np.ldexp(new,-shift).view(np.uint64))
  assert all(shift[np.asarray(d['types'])!='C']==0)
  extra=dict(finite_bounds_and_objective_bit_exact_roundtrip=True,integer_binary_columns_unchanged=True,
   positive_shift_columns=int(np.count_nonzero(shift>0)),negative_shift_columns=int(np.count_nonzero(shift<0)))
 return dict(exact_finite_nonzero_coefficient_roundtrip=True,NNZ_checked=checked,coefficient_abs_minimum=smallest,coefficient_abs_maximum=largest,
  coefficient_abs_dynamic_range=largest/smallest,shift_distribution=dict(Counter(map(int,shift))),**extra)

def measure(prefix,msha,dsha,v):
 started=time.perf_counter();a,d=load_stage(prefix);assert matrix_sha(a)==msha and domain_sha(d)==dsha
 rho=rho_certificate(a,d,v) if prefix=='DENSE_RESPONSE' else None
 row_degree=np.diff(a['indptr']);col_degree=np.bincount(a['indices'],minlength=len(d['names']))
 rf=np.asarray([fam(n) for n in d['row_names']]);cf=np.asarray([fam(n) for n in d['names']])
 col_stats={};row_stats={};absdata=np.abs(a['data']);nonempty=row_degree>0
 row_min=np.full(len(row_degree),np.inf);row_max=np.zeros(len(row_degree))
 row_min[nonempty]=np.minimum.reduceat(absdata,a['indptr'][:-1][nonempty]);row_max[nonempty]=np.maximum.reduceat(absdata,a['indptr'][:-1][nonempty])
 col_min=np.full(len(col_degree),np.inf);col_max=np.zeros(len(col_degree));np.minimum.at(col_min,a['indices'],absdata);np.maximum.at(col_max,a['indices'],absdata)
 for f in np.unique(rf):
  ids=np.flatnonzero(rf==f);ok=ids[nonempty[ids]];row_stats[str(f)]=dict(rows=len(ids),NNZ=int(np.sum(row_degree[ids])),degree=distribution(row_degree[ids]),
   min_abs_coefficient=float(np.min(row_min[ok])) if len(ok) else None,max_abs_coefficient=float(np.max(row_max[ids])),
   within_row_coefficient_dynamic_range=distribution(row_max[ok]/row_min[ok]))
 for f in np.unique(cf):
  ids=np.flatnonzero(cf==f);ok=ids[col_degree[ids]>0];top=ids[np.argsort(col_degree[ids])[-5:][::-1]]
  col_stats[str(f)]=dict(columns=len(ids),NNZ=int(np.sum(col_degree[ids])),degree=distribution(col_degree[ids]),
   within_column_coefficient_dynamic_range=distribution(col_max[ok]/col_min[ok]),
   largest_columns=[dict(index=int(j),name=str(d['names'][j]),degree=int(col_degree[j]),min_abs_coefficient=float(col_min[j]),max_abs_coefficient=float(col_max[j])) for j in top])
 helpers=cf=='response_voltage_shared';hp=np.flatnonzero(helpers[a['indices']]);hr=np.searchsorted(a['indptr'],hp,side='right')-1
 helper=dict(columns=int(np.sum(helpers)),degree_one_columns=int(np.count_nonzero(col_degree[helpers]==1)),
  all_incident_stored_coefficients_exact_one=bool(np.all(a['data'][hp]==1)),
  all_incident_rows_definition_equalities=bool(all(d['sense'][i]=='=' and str(d['row_names'][i]).startswith('response_voltage_shared_binding[') for i in hr)),
  all_finite_bounds=bool(np.isfinite(d['lower'][helpers]).all() and np.isfinite(d['upper'][helpers]).all()),
  all_zero_objective=bool(np.all(d['objective'][helpers]==0)),consumer_inequality_incidents=0,
  actual_native_presolved_helper_elimination_unknown=True)
 shift=np.zeros(len(row_degree),dtype=np.int32);shift[nonempty]=1-np.frexp(row_max[nonempty])[1]
 row_scaling=roundtrip_scaling(a,d,shift,'row');upscaling=roundtrip_scaling(a,d,np.maximum(shift,0),'row')
 mag=np.maximum(np.abs(d['lower']),np.abs(d['upper']));finite=(d['types']=='C')&np.isfinite(mag)&(mag>0)
 cshift=np.zeros(len(col_degree),dtype=np.int32);cshift[finite]=np.frexp(mag[finite])[1]-1
 column_scaling=roundtrip_scaling(a,d,cshift,'column')
 result=dict(rows=len(row_degree),columns=len(col_degree),binary=int(np.count_nonzero(d['types']=='B')),NNZ=len(a['data']),
  logical_matrix_SHA=msha,logical_domain_SHA=dsha,row_families=row_stats,column_families=col_stats,
  overall_row_degree=distribution(row_degree),overall_column_degree=distribution(col_degree),
  exact_row_degree_squared_sum=int(np.dot(row_degree.astype(np.int64),row_degree.astype(np.int64))),
  exact_column_degree_squared_sum=int(np.dot(col_degree.astype(np.int64),col_degree.astype(np.int64))),
  uncoalesced_column_row_pair_proxy=sum(choose2(n) for n in col_degree),
  coefficient_abs_minimum=float(np.min(absdata)),coefficient_abs_maximum=float(np.max(absdata)),
  coefficient_abs_dynamic_range=float(np.max(absdata)/np.min(absdata)),
  coefficient_bins={f'({lo:g},{hi:g}]':int(np.count_nonzero((absdata>lo)&(absdata<=hi))) for lo,hi in zip((0,1e-12,1e-10,1e-8,1e-6,1e-4,1e-2,1,100),(1e-12,1e-10,1e-8,1e-6,1e-4,1e-2,1,100,np.inf))},
  voltage_shared_helper_analysis=helper,scalar_power_of_two_scaling_checks=dict(row_max_normalization=row_scaling,
   row_upscaling_only_no_original_unit_absolute_row_tolerance_loosening=upscaling,continuous_finite_bound_column_normalization=column_scaling,
   actual_scaled_CSR_or_native_model_constructed=False,tolerances_changed=False,coefficients_zeroed=False,
   solver_conditioning_fill_runtime_and_memory_effect_unknown=True,
   numeric_domain_caveat='Exact feasible-set projection does not imply identical absolute feasibility allowances in original units; downscaled rows or enlarged variables require unchanged original FULL replay gates. No scaling is adopted.'),
  wall_seconds=time.perf_counter()-started)
 del a,d,absdata,row_degree,col_degree,rf,cf,row_min,row_max,col_min,col_max,shift,cshift;gc.collect()
 print(json.dumps(dict(phase='STAGE_DONE',stage=prefix,rows=result['rows'],columns=result['columns'],NNZ=result['NNZ'],wall_seconds=result['wall_seconds'])),flush=True)
 return result

def main():
 OUT.mkdir(parents=True,exist_ok=True);v=read(DEV/'NATIVE0_VALIDATION.json');s=read(CASE/'SCIENTIFIC_CASE_IDENTITY.json')
 dense=measure('DENSE_RESPONSE',s['selected_matrix_sha'],s['selected_domain_sha'],v)
 c3a=measure('C3A',s['C3A_matrix_sha'],s['C3A_domain_sha'],v)
 rho=read(OUT/'CURRENT_DENSE_RHO_COLUMN_CERTIFICATE.json');n=rho['actual_incident_rows'];slots=rho['per_slot_row_counts']
 comparison=dict(Dense_minus_C3A_rows=dense['rows']-c3a['rows'],Dense_minus_C3A_columns=dense['columns']-c3a['columns'],
  Dense_minus_C3A_NNZ=dense['NNZ']-c3a['NNZ'],Dense_minus_C3A_row_square_proxy=dense['exact_row_degree_squared_sum']-c3a['exact_row_degree_squared_sum'],
  Dense_minus_C3A_column_square_proxy=dense['exact_column_degree_squared_sum']-c3a['exact_column_degree_squared_sum'],
  proposed_rho_split_row_square_delta=384,
  proposed_rho_split_column_square_delta=96**2+sum((v+1)**2 for v in slots.values())-n**2,
  actual_native_presolved_family_axes_or_factor_gain_measured=False)
 report=dict(PASS=True,schema='CURRENT_C3A_DENSE_ROOT_FANOUT_SCALING_NATIVE0_V1',source_SHA=v['source_SHA'],case_SHA=v['case_SHA'],
  stages=dict(C3A=c3a,Dense=dense),comparison=comparison,rho_certificate=rec(OUT/'CURRENT_DENSE_RHO_COLUMN_CERTIFICATE.json'),
  no_AA_prime_or_factor_matrix_formed=True,matrices_loaded_and_released_one_at_a_time=True,
  Native_calls=0,Gurobi_presolve_calls=0,model_builds=0,source_edits=0,Threads=1,
  worker_or_thread_increases_requested=False,virtual_memory_or_paging_changes=False,
  receipts=[rec(CASE/(p+'_'+f+'.npz')) for p in ('C3A','DENSE_RESPONSE') for f in ('A','DATA')])
 write('CURRENT_C3A_DENSE_ROOT_FANOUT_SCALING_AUDIT.json',report)
 print(json.dumps(dict(PASS=True,path=str(OUT/'CURRENT_C3A_DENSE_ROOT_FANOUT_SCALING_AUDIT.json'),comparison=comparison)))
if __name__=='__main__':main()
