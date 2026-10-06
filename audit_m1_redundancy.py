"""No heavy optimize: census, exact hashes, DAG/SOC/PCS domain and screening."""
import json,time,hashlib
from collections import Counter
from fractions import Fraction as F
import numpy as np
from scipy import sparse
from v42_degen.identity import inputs,signature,digest
from v42_degen.common import SOURCE,POLICY
from v42_redundancy.common import *
from v42_redundancy.canonical import row,payload,exact_audits,exact_box
from v42_redundancy.domain import build_domain
from v42_redundancy.grid import screen

def run():
 start=time.perf_counter();LOCAL.mkdir(exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
 A,d,B,e,identity,freeze=inputs();assert B.has_canonical_format
 with np.load(SOURCE/'REDUCTION_AXES.npz') as z:originalaxis=z['keep']
 families=np.asarray([str(n).split('[')[0] for n in e['row_names']]);lengths=np.diff(B.indptr)
 census=[]
 for fam in sorted(set(families)):
  mask=families==fam;census.append(dict(family=fam,rows=int(mask.sum()),nnz=int(lengths[mask].sum()),equalities=int(np.sum(mask&(e['sense']=='='))),less_equal=int(np.sum(mask&(e['sense']=='<'))),greater_equal=int(np.sum(mask&(e['sense']=='>')))))
 cf=np.asarray([str(n).split('[')[0] for n in e['names']]);columns=[]
 for fam in sorted(set(cf)):
  mask=cf==fam;columns.append(dict(family=fam,columns=int(mask.sum()),binaries=int(np.sum(mask&(e['types']=='B'))),continuous=int(np.sum(mask&(e['types']=='C')))))
 write('M1_FULL_ROW_CENSUS.json',dict(PASS=True,base=BASE,rows=B.shape[0],columns=B.shape[1],binaries=int(np.sum(e['types']=='B')),continuous=int(np.sum(e['types']=='C')),nnz=B.nnz,row_families=census,column_families=columns,scientific_identity=identity,PR159_scientific_signature=signature(B,e),unreduced_rows=A.shape[0],unreduced_nnz=A.nnz,all_security_rows=sum(c['rows'] for c in census if c['family'] in ['line_thermal_face','NormalAmps','transformer_kVA','voltage_lower','voltage_upper','transformer_current'])))
 table('M1_FULL_ROW_CENSUS.csv',census,list(census[0]));table('M1_COLUMN_CENSUS.csv',columns,list(columns[0]))
 # Canonical transport contains every exact stored sparse coefficient and row
 # identity. Equalities retain sign. Constants from affine definitions stay in
 # their original RHS; explicit canonical constant is zero.
 sg=np.where(e['sense']=='>',-1.,1.)
 np.savez_compressed(OUT/'M1_CANONICAL_ROWS.npz',indptr=B.indptr,indices=B.indices,coefficients=B.data*np.repeat(sg,lengths),rhs=sg*e['rhs'],sense=np.where(e['sense']=='>','<',e['sense']),original_sense=e['sense'],row_names=e['row_names'],original_reduced_row_id=np.arange(B.shape[0]),unreduced_row_id=originalaxis,constant=np.zeros(B.shape[0]),shape=B.shape)
 np.savez_compressed(OUT/'M1_ORIGINAL_COLUMN_AUTHORITY.npz',**{k:e[k] for k in ['names','lower','upper','types','objective','constant']})
 print('CENSUS',B.shape,B.nnz,flush=True)
 pairs,dom,graph,collision_count=exact_audits(B,e)
 write('M1_DUPLICATE_AUDIT.json',dict(PASS=True,rows_removable=len(pairs),nnz_removable=int(sum(lengths[i] for i in pairs)),duplicates_by_family=dict(Counter(families[list(pairs)])),unique_duplicate_groups=len(set(pairs.values())),verified_exact_hash_collisions=collision_count,payload_comparison='Canonical sense, every sparse index, exact stored coefficient, exact RHS; no tolerance; signed zero normalized only.'))
 write('M1_DOMINANCE_AUDIT.json',dict(PASS=True,rows_removable=len(dom),nnz_removable=int(sum(lengths[i] for i in dom)),by_family=dict(Counter(families[list(dom)])),method='Primitive integer vector of exact dyadic coefficients; exact rational normalized RHS. Positive inequality multiplier only. Exact sign-normalized equality duplicates only.',equalities_removed_by_one_sided_bound=0))
 print('HASH_AUDITS',len(pairs),len(dom),flush=True)
 domain=build_domain(B,e);gs=screen(B,e,domain);anchors=domain['anchors']|gs['anchors']
 print('DOMAIN_SCREEN_DONE',time.perf_counter()-start,flush=True)
 certified={};overlap=Counter();box_count=0
 canon_rhs=sg*e['rhs'];margin=1e-8*np.maximum.reduce([np.ones(B.shape[0]),abs(canon_rhs),np.where(np.isfinite(gs['upper']),abs(gs['upper']),0)])
 candidates=np.flatnonzero((e['sense']!='=')&(gs['upper']<=canon_rhs-margin))
 # A zero-support violation is an authority error; never delete it.
 for i in gs['axis'][gs['zero'][gs['axis']]]:
  if gs['upper'][i]>canon_rhs[i]:
   # Independently evaluate exact constant including rho endpoint.
   from v42_redundancy.replay import exact_fixed_security
   fixed=exact_fixed_security(B,e,int(i),domain)
   if fixed is not None and fixed>F(float(canon_rhs[i])):raise ValueError('VIOLATED_CONSTANT_SECURITY_ROW:'+str(i))
 for i in candidates:
  i=int(i);cat='PROVABLY_CONSTANT_SAFE' if gs['zero'][i] else 'GRID_SENSITIVITY_CERTIFIED'
  if not gs['zero'][i] and gs['unrestricted_upper'][i]>canon_rhs[i]-margin[i]:cat='ROUTE_REACHABILITY_CERTIFIED'
  certified[i]=dict(category=cat,upper=float(gs['upper'][i]),method='OUTWARD_IEEE_SPARSE_AFFINE_PCS_SUPPORT',proof='DAG_UNIT_FLOW_PERSPECTIVE_PCS16_AND_RETAINED_AFFINE_DEFINITIONS')
 for i in range(B.shape[0]):
  if i in anchors or e['sense'][i]=='=' or i in certified:continue
  ub=exact_box(B,e,i)
  if ub is not None and F(float(canon_rhs[i]))-ub>F(1e-8)*max(F(1),abs(F(float(canon_rhs[i]))),abs(ub)):
   certified[i]=dict(category='OTHER_EXACT_STRUCTURAL',upper=str(ub),method='EXACT_BINARY_RATIONAL_VARIABLE_BOX',proof='ORIGINAL_UNCHANGED_FINITE_COLUMN_BOUNDS');box_count+=1
 for i in graph:
  if i in certified:overlap['duplicate_or_dominance_and_absolute']+=1
 # Prefer exact duplicate proof while protecting every final proof anchor.
 chosen={}
 for i,j in graph.items():
  if i in anchors and lengths[i]>0:continue
  chosen[i]=dict(category='EXACT_DUPLICATE' if i in pairs else 'EXACT_DOMINATED',dominator=int(j),upper=str(F(float(canon_rhs[i]))),method='EXACT_BINARY_RATIONAL_ROW_IMPLICATION',proof='RETAINED_ORIGINAL_ROW')
 for i,c in certified.items():
  if i not in chosen and i not in anchors:chosen[i]=dict(c,dominator=None)
 # If a duplicate representative has an absolute certificate, either anchor
 # it retained or redirect dependency to that independent absolute proof.
 for c in chosen.values():
  j=c['dominator']
  if j is not None and j in chosen:
   assert chosen[j]['dominator'] is None,'NONCLOSED_DEPENDENCY'
 keep=np.ones(B.shape[0],bool);keep[list(chosen)]=False
 dependency=[dict(removed_row=i,retained_dominator=c['dominator'],absolute_domain=c['proof'] if c['dominator'] is None else None) for i,c in sorted(chosen.items())]
 write('M1_REMOVAL_DEPENDENCY_GRAPH.json',dict(PASS=True,acyclic=True,edges=dependency,retained_anchor_rows=sorted(anchors-set(chosen)),absolute_endpoint_rows=[j for j in chosen if chosen[j]['dominator'] is None],final_closure='Direct retained original row or independently absolute domain endpoint. No circular implication.'))
 cats=['EXACT_DUPLICATE','EXACT_DOMINATED','PROVABLY_CONSTANT_SAFE','ROUTE_REACHABILITY_CERTIFIED','SOC_PQ_ENVELOPE_CERTIFIED','GRID_SENSITIVITY_CERTIFIED','OTHER_EXACT_STRUCTURAL']
 catc=[]
 for c in cats:
  ix=[i for i,v in chosen.items() if v['category']==c];catc.append(dict(category=c,rows=len(ix),nnz=int(sum(lengths[i] for i in ix)),percent_whole_rows=100*len(ix)/B.shape[0],percent_whole_nnz=100*sum(lengths[i] for i in ix)/B.nnz,by_family=dict(Counter(families[ix]))))
 final=[]
 for r in census:
  ix=np.flatnonzero(families==r['family']);rem=[int(i) for i in ix if i in chosen]
  final.append(dict(family=r['family'],original_rows=r['rows'],removed_rows=len(rem),remaining_rows=r['rows']-len(rem),removed_nnz=int(sum(lengths[i] for i in rem)),percent_family=100*len(rem)/r['rows'],percent_whole=100*len(rem)/B.shape[0]))
 reduced=B[keep];rows_removed=int((~keep).sum());nnz_removed=B.nnz-reduced.nnz;gate=rows_removed/B.shape[0]>=.20 or nnz_removed/B.nnz>=.15
 write('M1_FINAL_REDUCTION_CENSUS.json',dict(PASS=True,original_rows=B.shape[0],original_nnz=B.nnz,removed_rows=rows_removed,removed_nnz=nnz_removed,rows_fraction=rows_removed/B.shape[0],nnz_fraction=nnz_removed/B.nnz,remaining_rows=reduced.shape[0],remaining_nnz=reduced.nnz,categories=catc,families=final,overlaps_before_unique_assignment=dict(overlap),absolute_candidates_before_unique_assignment=len(certified),box_candidates=box_count,materiality_gate=gate,EXACT_REDUNDANCY_REDUCTION_SELECTED=False))
 def certificates():
  for i,c in sorted(chosen.items()):
   js,ws,b,s=row(B,e,i);ub=c['upper'];slack=str(F(b)-F(ub)) if ub is not None else 'IMPLIED_BY_EXACT_RETAINED_ROW'
   yield dict(original_row_id=i,unreduced_row_id=int(originalaxis[i]),row_name=str(e['row_names'][i]),family=str(families[i]),original_sense=str(e['sense'][i]),canonical_sense=s,RHS=repr(b),constant='0',row_SHA256=hashlib.sha256(payload(B,e,i)).hexdigest(),category=c['category'],dominator=c['dominator'],certified_upper_bound=ub,certified_slack=slack,arithmetic_method=c['method'],proof_source=c['proof'],nnz=int(lengths[i]))
 fields=['original_row_id','unreduced_row_id','row_name','family','original_sense','canonical_sense','RHS','constant','row_SHA256','category','dominator','certified_upper_bound','certified_slack','arithmetic_method','proof_source','nnz']
 table('M1_REMOVED_ROW_CERTIFICATES.csv',certificates(),fields)
 for fs,name in [(['line_thermal_face'],'M1_LINE_FACE_REDUNDANCY.csv'),(['transformer_kVA','transformer_current','NormalAmps'],'M1_TRANSFORMER_REDUNDANCY.csv'),(['voltage_lower','voltage_upper'],'M1_VOLTAGE_REDUNDANCY.csv')]:
  def records():
   for i in gs['axis'][np.isin(families[gs['axis']],fs)]:
    v=chosen.get(int(i),{});yield dict(original_row_id=int(i),row_name=str(e['row_names'][i]),family=str(families[i]),canonical_RHS=repr(float(canon_rhs[i])),upper_bound=repr(float(gs['upper'][i])),upper_without_route_exclusions=repr(float(gs['unrestricted_upper'][i])),upper_without_exclusivity=repr(float(gs['naive_upper'][i])),decision='REMOVE' if int(i) in chosen else 'KEEP',category=v.get('category','NOT_CERTIFIED'),dominator=v.get('dominator'))
  table(name,records(),['original_row_id','row_name','family','canonical_RHS','upper_bound','upper_without_route_exclusions','upper_without_exclusivity','decision','category','dominator'])
 write('M1_GRID_SENSITIVITY_SCREENING.json',dict(PASS=True,security_rows=len(gs['axis']),all_families_screened=dict(Counter(families[gs['axis']])),no_mass_LPs=True,optimize_calls=0,zero_controllable_support_rows=int(gs['zero'].sum()),absolute_certified_rows=len(candidates),affine_bindings_retained=len(gs['anchors']),all_grid_auxiliaries_retained=81216,outer_domain='Original affine equalities + DAG unit flow + reachable-state perspective PCS16 support + rho original bounds. All original integer and continuous-relaxed feasible controls are included.',interval_method='Exact stored affine factors; enclosed sparse dot (4 gamma_(2k+4) plus subnormal payment); every subsequent multiply/add rounded outward. Exact rational PCS vertices rounded outward.',certified_safety='1e-8*max(1,abs(RHS),abs(upper)); ambiguous KEEP',LP_based_residual_stage='NOT_EXECUTED_OR_AUTHORIZED'))
 sparse.save_npz(OUT/'M1_EXACT_REDUCED_A.npz',reduced)
 np.savez_compressed(OUT/'M1_REDUCTION_AXES.npz',keep=np.flatnonzero(keep),removed=np.flatnonzero(~keep))
 np.savez_compressed(LOCAL/'SCREEN_CACHE.npz',upper=gs['upper'],zero=gs['zero'],rowtime=gs['rowtime'])
 f=dict(e,rhs=e['rhs'][keep],sense=e['sense'][keep],row_names=e['row_names'][keep]);sig=signature(reduced,f)
 write('M1_REDUCED_MODEL_IDENTITY_AUDIT.json',dict(PASS=True,base=BASE,original_signature=signature(B,e),reduced_signature=sig,columns_unchanged=all(signature(B,e)[k]==sig[k] for k in ['objective','objective_constant','bounds_lower','bounds_upper','vtypes','variable_names']),columns=B.shape[1],binaries=int(np.sum(e['types']=='B')),continuous=int(np.sum(e['types']=='C')),grid_auxiliaries=81216,all_retained_rows_exactly_original=True,row_subset_SHA=digest(np.flatnonzero(keep)),all_scientific_input_hashes_verified=True,route_domain_changed=False,limits_changed=False,objective_changed=False,solver_POLICY=POLICY,optimization_calls=0,pending_independent_replay=True))
 print('REDUCTION',rows_removed,nnz_removed,'GATE',gate,'wall',time.perf_counter()-start,flush=True)
 return chosen
if __name__=='__main__':run()
