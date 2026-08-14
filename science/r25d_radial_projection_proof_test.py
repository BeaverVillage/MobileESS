#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,math,random,tarfile,tempfile,shutil
from collections import defaultdict
import numpy as np
import pandas as pd
from r25d_radial_projection import (
 build_projection_topology,condense_static_subtree_flows,skeleton_balance_child_terms,
 build_voltage_affine_map,propagate_projected_voltage_bounds,static_line_thermal_checks,
 structural_reduction_counts,LINE,TX)

R=Path(__file__).resolve().parent
ARC=R/'embedded/BUILD7AR2_PASS.tar.gz'

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()

def full_flows(nodes,root,parent,depth,ownp,ownq):
 fp={n:float(ownp.get(n,0.0)) for n in nodes};fq={n:float(ownq.get(n,0.0)) for n in nodes}
 for n in sorted((u for u in nodes if u!=root),key=lambda u:depth[u],reverse=True):
  p=parent[n];fp[p]+=fp[n];fq[p]+=fq[n]
 return fp,fq

def full_voltage(nodes,root,parent,depth,kind,r,x,ratio,fp,fq,rfp,rfq):
 du={root:0.0}
 for n in sorted((u for u in nodes if u!=root),key=lambda u:depth[u]):
  p=parent[n]
  if kind[n]==LINE:
   du[n]=du[p]-0.002*(r[n]*(fp[n]-rfp[n])+x[n]*(fq[n]-rfq[n]))
  elif kind[n]==TX:
   du[n]=ratio[n]*du[p]
  else:raise AssertionError(kind[n])
 return du

def main():
 td=Path(tempfile.mkdtemp(prefix='r25d_gridproof_'))
 try:
  with tarfile.open(ARC,'r:gz') as tf:
   members=[m for m in tf.getmembers() if m.name.endswith(('BUILD7_GRID_LINEAR_COEFFICIENTS.npz','BUILD7_TRAFFIC_ELECTRICAL_SERVICE_NODE_AXIS_24.csv','BUILD7_IDC_LOAD_PCC_MAP_12.csv'))]
   tf.extractall(td,members=members,filter='data')
  coeff=next(td.rglob('BUILD7_GRID_LINEAR_COEFFICIENTS.npz'))
  service=next(td.rglob('BUILD7_TRAFFIC_ELECTRICAL_SERVICE_NODE_AXIS_24.csv'))
  idc=next(td.rglob('BUILD7_IDC_LOAD_PCC_MAP_12.csv'))
  z=np.load(coeff,allow_pickle=False)
  nodes=tuple(str(q).lower() for q in z['node_axis'].tolist())
  root=str(z['root'].item()).lower()
  parent={str(c).lower():str(p).lower() for p,c in zip(z['edge_parent'],z['edge_child'])}
  kind={str(c).lower():str(k) for c,k in zip(z['edge_child'],z['edge_kind'])}
  rr={str(c).lower():float(v) for c,v in zip(z['edge_child'],z['r_ohm'])}
  xx={str(c).lower():float(v) for c,v in zip(z['edge_child'],z['x_ohm'])}
  ratio={str(c).lower():float(v) for c,v in zip(z['edge_child'],z['ratio2'])}
  limits={(str(p).lower(),str(c).lower()):float(v) for p,c,k,v in zip(z['edge_parent'],z['edge_child'],z['edge_kind'],z['line_apparent_limit_kVA']) if str(k)==LINE and np.isfinite(float(v))}
  sv=pd.read_csv(service);iv=pd.read_csv(idc)
  decision=set(sv['pcc_bus'].astype(str).str.lower())|set(iv['pcc_bus'].astype(str).str.lower())
  topo=build_projection_topology(nodes,root,parent,kind,decision)
  aud=topo.audit();red=structural_reduction_counts(topo,54)
  expected={
   'node_count':168,'edge_count':167,'decision_injection_node_count':36,
   'decision_skeleton_node_count':100,'static_node_count':68,'static_root_count':31,
   'skeleton_line_node_count':61,'skeleton_transformer_node_count':38,
   'static_line_node_count':65,'static_transformer_node_count':3,
   'retained_voltage_variable_nodes_per_h':61,
  }
  topology_exact=all(aud[k]==v for k,v in expected.items())
  expected_red={
   'FP_FQ_continuous_variables_removed':7344,
   'P_Q_balance_equalities_removed':7344,
   'dU_continuous_variables_removed':5778,
   'voltage_recursion_equalities_removed':5724,
   'line_circle_QCP_constraints_removed_by_constant_precheck':3510,
   'total_continuous_variables_removed_structural':13122,
   'total_linear_equalities_removed_structural':13068,
  }
  reduction_exact=all(red[k]==v for k,v in expected_red.items())

  rng=random.Random(20260813)
  max_balance_err=max_static_flow_err=max_voltage_err=0.0
  bound_equivalence=True;thermal_equivalence=True
  trials=300
  for trial in range(trials):
   # Small random injections keep actual line limits comfortably feasible while
   # still exercising every tree branch and both P/Q dimensions.
   ownp={n:rng.uniform(-0.25,0.75) for n in nodes}
   ownq={n:rng.uniform(-0.20,0.30) for n in nodes}
   refownp={n:rng.uniform(-0.20,0.60) for n in nodes}
   refownq={n:rng.uniform(-0.15,0.25) for n in nodes}
   fp,fq=full_flows(nodes,root,parent,topo.depth,ownp,ownq)
   rfp,rfq=full_flows(nodes,root,parent,topo.depth,refownp,refownq)
   sfp,sfq=condense_static_subtree_flows(topo,ownp,ownq)
   for n in topo.static_nodes:
    max_static_flow_err=max(max_static_flow_err,abs(fp[n]-sfp[n]),abs(fq[n]-sfq[n]))
   for n in topo.skeleton:
    if n==root:continue
    dyn,cp,cq=skeleton_balance_child_terms(topo,n,sfp,sfq)
    rp=float(ownp[n])+cp+sum(fp[c] for c in dyn)
    rq=float(ownq[n])+cq+sum(fq[c] for c in dyn)
    max_balance_err=max(max_balance_err,abs(fp[n]-rp),abs(fq[n]-rq))
   # Static QCP replacement is exact because the eliminated branch flow equals
   # the constant subtree flow.  Actual planning limits are used here.
   checks=static_line_thermal_checks(topo,sfp,sfq,limits)
   thermal_equivalence &= len(checks)==len(topo.static_line_nodes)
   thermal_equivalence &= all(abs(math.hypot(fp[q['child']],fq[q['child']])/q['limit_kVA']-q['loading_ratio'])<1e-12 for q in checks)

   du=full_voltage(nodes,root,parent,topo.depth,kind,rr,xx,ratio,fp,fq,rfp,rfq)
   amap=build_voltage_affine_map(topo,rr,xx,ratio,sfp,sfq,rfp,rfq)
   for n,(a,s,b) in amap.items():
    pred=b if a is None else s*du[a]+b
    max_voltage_err=max(max_voltage_err,abs(pred-du[n]))

   # Construct heterogeneous hard intervals around this feasible voltage point,
   # propagate them, then independently sample the one-dimensional anchor domain.
   vb={n:(du[n]-rng.uniform(0.2,1.5),du[n]+rng.uniform(0.2,1.5)) for n in nodes}
   ab,_=propagate_projected_voltage_bounds(topo,amap,vb)
   by_anchor=defaultdict(list)
   for n,(a,s,b) in amap.items():
    if a is not None:by_anchor[a].append(n)
   for a,group in by_anchor.items():
    lb,ub=ab[a]
    span=max(1.0,ub-lb)
    for j in range(25):
     xval=(lb-span)+(2*span+(ub-lb))*j/24.0
     direct=all(vb[n][0]-1e-10 <= amap[n][1]*xval+amap[n][2] <= vb[n][1]+1e-10 for n in group)
     compressed=(lb-1e-10 <= xval <= ub+1e-10)
     if direct!=compressed:bound_equivalence=False

  result={
   'stage':'A4/6','PASS':bool(topology_exact and reduction_exact and max_balance_err<1e-10 and max_static_flow_err<1e-10 and max_voltage_err<1e-10 and bound_equivalence and thermal_equivalence),
   'actual_BUILD7AR2_topology':aud,'expected_topology_match':topology_exact,
   'H54_structural_reduction':red,'expected_reduction_match':reduction_exact,
   'random_equivalence_trials':trials,
   'max_skeleton_balance_error':max_balance_err,'max_static_branch_flow_error':max_static_flow_err,
   'max_projected_voltage_error':max_voltage_err,'projected_voltage_bound_interval_equivalence':bool(bound_equivalence),
   'static_line_QCP_constant_replacement_equivalence':bool(thermal_equivalence),
   'scientific_claim':'Static-subtree branch flows are decision-independent because all 36 possible IDC/MESS decision injections are included in the retained ancestor skeleton. Eliminated voltage states are exact affine functions of one retained LINE-node dU or the anchored root constant.',
   'long_solver_run_executed':False,
   'source_sha256':{'BUILD7AR2_PASS.tar.gz':sha(ARC),'BUILD7_GRID_LINEAR_COEFFICIENTS.npz':sha(coeff),'service24_csv':sha(service),'idc12_csv':sha(idc)}
  }
  print(json.dumps(result,indent=2,sort_keys=True))
  if not result['PASS']:raise SystemExit(2)
 finally:
  shutil.rmtree(td,ignore_errors=True)
if __name__=='__main__':main()
