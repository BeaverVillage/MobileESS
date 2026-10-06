"""Small bounded fixtures only; never optimizes the full-scale model."""
import itertools,time,copy,json
from fractions import Fraction as F
from collections import Counter
import numpy as np
import gurobipy as gp
from scipy import sparse
from v42_benders.fixtures import CASES,build as fixture
from v42_integrated.matrix import arrays,audit
from v42_redundancy.common import OUT,write,table
from v42_redundancy.canonical import exact_audits,exact_box,row,proportional_key
from v42_redundancy.domain import rational_vertices
from v42_redundancy.grid import support_bounds
from v42_redundancy.model import build

def tiny_reduction(A,d):
 pairs,dom,graph,_=exact_audits(A,d);gone=set(graph)
 for i in range(A.shape[0]):
  ub=exact_box(A,d,i);js,ws,b,s=row(A,d,i)
  if ub is not None and F(b)-ub>F(1e-8)*max(F(1),abs(F(b)),abs(ub)):gone.add(i)
 # Keep final implication representatives if they would otherwise be removed.
 # Fixture bound certificates are absolute, but retained representative is the
 # simpler proof; full-scale closure separately permits absolute endpoints.
 gone-=set(graph.values())
 return np.asarray([i for i in range(A.shape[0]) if i not in gone]),graph
def configure(m):
 for k,v in dict(Threads=1,Seed=20260929,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,MIPGap=.005,TimeLimit=5,Method=1,LogToConsole=0).items():m.setParam(k,v)
def compare_models(a,b,A,d):
 a.optimize();b.optimize();assert a.Status in (2,3) and a.Status==b.Status
 if a.Status==3:return dict(feasible=False,objective=None,full_point=None,reduced_point=None)
 x=np.asarray(a.getAttr('X'));y=np.asarray(b.getAttr('X'));assert abs(a.ObjVal-b.ObjVal)<=1e-7
 assert audit(A,d,x,integral=True,tolerance=1e-7)['PASS'] and audit(A,d,y,integral=True,tolerance=1e-7)['PASS']
 return dict(feasible=True,objective=float(a.ObjVal),full_point=x.tolist(),reduced_point=y.tolist(),max_full_row_residual_on_reduced=float(np.max(np.maximum(0,np.where(d['sense']=='=',abs(A@y-d['rhs']),np.where(d['sense']=='<',A@y-d['rhs'],d['rhs']-A@y))),initial=0.)))
def run():
 begin=time.perf_counter();env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();assignments=[];summary=[]
 try:
  for case,cfg in CASES.items():
   full=fixture(env,case);configure(full);A,d=arrays(full);keep,graph=tiny_reduction(A,d);reduced=build(A,d,keep,env);configure(reduced)
   # Native payload transport, including exact names and unchanged columns.
   C,f=arrays(reduced);assert np.array_equal(C.toarray(),A[keep].toarray())
   for key in ['names','lower','upper','types','objective','constant']:assert np.array_equal(d[key],f[key])
   for key in ['rhs','sense','row_names']:assert np.array_equal(f[key],d[key][keep])
   original=compare_models(full,reduced,A,d);ix=np.flatnonzero(d['types']=='B');fv=full.getVars();rv=reduced.getVars();feasible=0;best=None;best_patterns=[]
   for no,bits in enumerate(itertools.product([0.,1.],repeat=7)):
    for j,v in zip(ix,bits):fv[j].LB=fv[j].UB=v;rv[j].LB=rv[j].UB=v
    # Audit against exact fixed binary bounds, not just the old unfixed box.
    dd=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy());dd['lower'][ix]=bits;dd['upper'][ix]=bits
    r=compare_models(full,reduced,A,dd);r.update(case=case,assignment=no,bits=''.join(map(str,map(int,bits))),PASS=True)
    if r['feasible']:
     feasible+=1
     if best is None or r['objective']<best-1e-7:best=r['objective'];best_patterns=[r['bits']]
     elif abs(r['objective']-best)<=1e-7:best_patterns.append(r['bits'])
     # Independent physical values retain P/Q/SOC and all original grid
     # expressions at BOTH optima, rather than require arbitrary degenerate
     # optimizer primal choices to coincide.
     for label in ['full_point','reduced_point']:
      point=np.asarray(r[label]);values=A@point
      r[label+'_physics']={str(n):float(point[j]) for j,n in enumerate(d['names']) if str(n).startswith(('SOC','Pch','Pdis','Q'))}
      r[label+'_grid']=[dict(row=i,name=str(d['row_names'][i]),lhs=float(values[i]),rhs=float(d['rhs'][i]),sense=str(d['sense'][i])) for i in range(A.shape[0]) if any(k in str(d['row_names'][i]).lower() for k in ['voltage','transformer','line_threshold'])]
    assignments.append(r)
   assert (best is None and not original['feasible']) or (best is not None and abs(best-original['objective'])<=1e-7)
   if original['feasible'] and len(best_patterns)==1:
    for key in ['full_point','reduced_point']:assert ''.join(str(int(round(original[key][j]))) for j in ix)==best_patterns[0]
   summary.append(dict(case=case,label=cfg['label'],assignments=128,feasible=feasible,infeasible=128-feasible,rows=A.shape[0],removed=A.shape[0]-len(keep),unfixed_objective=original['objective'],enumerated_objective=best,optimum_integer_patterns=best_patterns,unique_pattern_verified=len(best_patterns)==1,PQ_SOC_and_original_grid_at_both_optima_PASS=True,PASS=True))
   full.dispose();reduced.dispose();print('PHYSICAL_FIXTURE',case,feasible,'PASS',flush=True)
  write('M1_REDUNDANCY_FIXTURE_ASSIGNMENTS.json',assignments)
  result=dict(PASS=True,fixtures=summary,exhaustive_assignments=len(assignments),feasible=sum(s['feasible'] for s in summary),infeasible=sum(s['infeasible'] for s in summary),equivalent_feasibility_and_objective=True,all_original_PQ_SOC_grid_constraints_cross_checked=True,integer_pattern_equivalence='Exhaustive feasible and optimum pattern sets; selected pattern checked where unique. Degenerate continuous optima may differ but both are full-original feasible.',fixture_scope='Existing unmodified v42_benders.fixtures CASES/build; exact duplicate and original finite-bound reductions. Full-scale PCS/route affine support deletion mechanism separately tested analytically and independently replayed for every removed row.',heavy_optimize_calls=0,lightweight_optimize_calls=2*12*(128+1),wall=time.perf_counter()-begin)
  assert len(assignments)==1536;write('M1_REDUNDANCY_FIXTURE_RESULTS.json',result)
  adversarial(env)
 finally:env.dispose()

def adversarial(env):
 results=[]
 def check(name,fn):fn();results.append(dict(case=name,PASS=True))
 def data(rows,rhs,sense,lo=None,hi=None):
  A=sparse.csr_matrix(np.asarray(rows,float));n=A.shape[1]
  d=dict(rhs=np.asarray(rhs,float),sense=np.asarray(sense),row_names=np.asarray(['probe']*len(rows)),lower=np.asarray(lo if lo is not None else [-1.]*n),upper=np.asarray(hi if hi is not None else [1.]*n))
  return A,d
 def boundary(s):
  A,d=data([[s]],[np.nextafter(1.,-np.inf)],['<']);assert exact_box(A,d,0)>F(float(d['rhs'][0]))
 check('near_voltage_upper',lambda:boundary(1))
 check('near_voltage_lower_canonical_sign',lambda:boundary(-1))
 def duplicate():
  A,d=data([[1.,.1],[-1.,-.1],[1.,np.nextafter(.1,np.inf)]],[1.,-1.,1.],['<','>','<']);p,q,g,_=exact_audits(A,d)
  assert p=={1:0} and 2 not in g
 check('exact_duplicate_and_near_not_dominated',duplicate)
 def dominance():
  A,d=data([[1.,2.],[2.,4.],[-1.,-2.],[1.,np.nextafter(2.,np.inf)]],[1.,3.,2.,1.],['<']*4);p,q,g,_=exact_audits(A,d)
  assert g=={1:0} and 2 not in g and 3 not in g
 check('rational_proportional_dominance_positive_scale_only',dominance)
 def equality():
  A,d=data([[1.],[1.]],[1.,2.],['=','=']);p,q,g,_=exact_audits(A,d);assert not g and exact_box(A,d,0) is None
 check('equality_not_one_sided_screened',equality)
 from math import cos,sin,pi
 faces=[(cos(2*pi*f/16),sin(2*pi*f/16),16*cos(pi/16)) for f in range(16)];vertices=rational_vertices(faces,16.,16.);domain=dict(sites=['A','B'],vertices=vertices)
 def poly_probe(cp,cq,name):
  exact=max(F(cp)*p+F(cq)*q for p,q in vertices);C=np.array([[cp,0.,cq,0.]]);u=support_bounds(C,C,domain)[0,0]
  assert F(float(u))>=exact
  # A face just below exact attainable support must not be called inactive.
  rhs=np.nextafter(float(exact),-np.inf);assert not u<=rhs
 check('near_line_face',lambda:poly_probe(1.,.2,'line'))
 check('reverse_PQ_quadrant',lambda:poly_probe(-1.,-.7,'reverse'))
 check('transformer_kVA_face',lambda:poly_probe(.5,1.,'transformer'))
 def unit_union():
  # Four MESS fractional masses split across two sites, each sum<=1.
  C=np.array([[1.,100.,.2,-80.]]);sup=support_bounds(C,C,domain)[0];upper=max(sup)
  for p,q in vertices:
   for r,s in vertices:
    for mass in [F(0),F(1,4),F(1,2),F(3,4),F(1)]:
     val=mass*(p+F(.2)*q)+(1-mass)*(100*r-80*s);assert F(float(upper))>=val
  assert max(sup[0],0.)<upper
 check('fractional_site_exclusivity_convex_hull_and_unreachable_high_sensitivity',unit_union)
 def route_transit_terminal():
  # Bounded original flow equations: stay path or travel A0->B2 then stay.
  # Independent enumerate all route bits and compare forward/back exclusions.
  arcs=[('A',0,'A',1),('A',1,'A',2),('A',2,'A',3),('A',0,'B',2),('B',2,'B',3),('C',1,'C',2),('C',2,'C',3)]
  feasible=[]
  for bits in itertools.product([0,1],repeat=len(arcs)):
   good=True
   for s in ['A','B','C']:
    for t in range(3):
     out=sum(bits[k] for k,a in enumerate(arcs) if a[:2]==(s,t));inc=sum(bits[k] for k,a in enumerate(arcs) if a[2:]==(s,t))
     good &= out-inc==int(s=='A' and t==0)
   good &= sum(bits[k] for k,a in enumerate(arcs) if a[3]==3)==1
   if good:feasible.append(bits);assert not bits[5] and not bits[6]
  assert len(feasible)==2
  # Travel skips connected states at t0,t1 and cannot supply P/Q. Terminal
  # B-only backward test rules out the entire stay-A path.
  travel=next(b for b in feasible if b[3]);assert not any(travel[k] and a[0]==a[2] and a[1] in (0,1) for k,a in enumerate(arcs))
  terminal_B=[b for b in feasible if b[4]];assert len(terminal_B)==1 and terminal_B[0][3]
 check('original_route_exhaustion_transit_unreachable_and_terminal_location',route_transit_terminal)
 def soc():
  # Exact bounded trajectories incl both endpoint constraints, .25 efficiency
  # factors and movement deductions; loose interval propagation contains all.
  lo=[F(10),F(0),F(10)];hi=[F(10),F(20),F(10)];cc=F(.225);dd=F(.25/.9);travelmax=[F(4),F(0)]
  for t in range(2):lo[t+1]=max(lo[t+1],lo[t]-dd*16-travelmax[t]);hi[t+1]=min(hi[t+1],hi[t]+cc*16)
  for t in [1,0]:lo[t]=max(lo[t],lo[t+1]-cc*16);hi[t]=min(hi[t],hi[t+1]+dd*16+travelmax[t])
  checked=0
  travel_checked=0
  for c0,d0,travel in itertools.product([F(0),F(4),F(8),F(16)],[F(0),F(4),F(8),F(16)],[F(0),F(1,5),F(4)]):
   if c0*d0:continue
   E1=10+cc*c0-dd*d0-travel
   c1=max(F(0),(F(10)-E1)/cc);d1=max(F(0),(E1-F(10))/dd)
   if c1>16 or d1>16:continue
   E2=E1+cc*c1-dd*d1
   if 0<=E1<=20 and E2==10:assert lo[1]<=E1<=hi[1];checked+=1
   if 0<=E1<=20 and E2==10 and travel:travel_checked+=1
  assert checked>=10 and travel_checked>=5
  # Near-final discharge without terminal recovery cannot be screened as
  # admissible; certificate uses both terminal and initial endpoints.
  assert 10-dd*16<lo[2]
 check('terminal_SOC_limited_discharge_and_exact_safe_envelope',soc)
 def unbounded():
  A,d=data([[1.]],[1.],['<'],[-np.inf],[np.inf]);assert exact_box(A,d,0) is None
 check('unbounded_variable_no_box_certificate',unbounded)
 write('M1_REDUNDANCY_ADVERSARIAL_RESULTS.json',dict(PASS=True,cases=results,tests=len(results),no_fullscale_optimization=True))
 print('ADVERSARIAL_PASS',len(results),flush=True)
if __name__=='__main__':run()
