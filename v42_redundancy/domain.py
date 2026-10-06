"""Original DAG-flow and homogeneous PCS proof, including fractional flows."""
from collections import defaultdict
from fractions import Fraction as F
from dataclasses import asdict
import itertools
import numpy as np
from v42_strengthening.analysis import graph_inputs
from .common import write

def suffix(name):return str(name).split('[',1)[1][:-1].split(',')
def rational_vertices(faces,pmax,qmax):
 constraints=[(F(a),F(b),F(c)) for a,b,c in faces]
 constraints += [(F(1),F(0),F(pmax)),(F(-1),F(0),F(pmax)),(F(0),F(1),F(qmax)),(F(0),F(-1),F(qmax))]
 verts=set()
 for (a,b,c),(d,e,f) in itertools.combinations(constraints,2):
  det=a*e-b*d
  if not det:continue
  x=(c*e-b*f)/det;y=(a*f-c*d)/det
  if all(u*x+v*y<=w for u,v,w in constraints):verts.add((x,y))
 assert verts
 return sorted(verts)

def build_domain(A,d):
 sites,initial,arcs,battery,receipt=graph_inputs();units=sorted(initial);H=96
 names={str(n):i for i,n in enumerate(d['names'])};rf=np.asarray([str(n).split('[')[0] for n in d['row_names']])
 cols={u:{k:names[f'arc[{u},{k}]'] for k in range(len(arcs)) if f'arc[{u},{k}]' in names} for u in units}
 incoming=defaultdict(list);outgoing=defaultdict(list)
 for k,(s,t,z,v,r) in enumerate(arcs):outgoing[s,t].append(k);incoming[z,v].append(k)
 forward={};backward={};reach=np.zeros((4,H,len(sites)),bool);transit=np.zeros((4,H),bool);eligible={}
 flows=np.flatnonzero(rf=='flow');terminal=np.flatnonzero(rf=='terminal_location')
 assert len(flows)==4*len(sites)*H and len(terminal)==4
 flow_checks=0
 for uidx,u in enumerate(units):
  f={(initial[u],0)}
  for t in range(H):
   for s in sites:
    if (s,t) in f:
     for k in outgoing[s,t]:f.add((arcs[k][2],arcs[k][3]))
  # Exact native terminal-location equation admits ANY site at H.
  i=int(terminal[uidx]);a,b=A.indptr[i:i+2]
  expected={j:1. for k,j in cols[u].items() if arcs[k][3]==H}
  assert dict(zip(map(int,A.indices[a:b]),map(float,A.data[a:b])))==expected and d['sense'][i]=='=' and d['rhs'][i]==1
  end={ (arcs[k][2],H) for k in cols[u] if arcs[k][3]==H }
  back=set(end)
  for t in reversed(range(H)):
   for s in sites:
    if any((arcs[k][2],arcs[k][3]) in back for k in outgoing[s,t]):back.add((s,t))
  active=[]
  for k,j in cols[u].items():
   assert (arcs[k][0],arcs[k][1]) in f and d['lower'][j]==0 and d['upper'][j]==1
   if (arcs[k][2],arcs[k][3]) in back:
    active.append(k)
    s,t,z,v,r=arcs[k]
    if r is None:reach[uidx,t,sites.index(s)]=True
    else:transit[uidx,t:v]=True
  for si,s in enumerate(sites):
   for t in range(H):
    i=int(flows[uidx*len(sites)*H+si*H+t]);a,b=A.indptr[i:i+2]
    expected={}
    for k in outgoing[s,t]:
     if k in cols[u]:expected[cols[u][k]]=expected.get(cols[u][k],0.)+1.
    for k in incoming[s,t]:
     if k in cols[u]:expected[cols[u][k]]=expected.get(cols[u][k],0.)-1.
    expected={j:v for j,v in expected.items() if v}
    assert dict(zip(map(int,A.indices[a:b]),map(float,A.data[a:b])))==expected
    assert d['sense'][i]=='=' and d['rhs'][i]==int(t==0 and s==initial[u]);flow_checks+=1
  forward[u]=sorted(f);backward[u]=sorted(back);eligible[u]=set(active)
 route=dict(PASS=True,units=units,sites=sites,horizon=H,initial=initial,graph_receipt=receipt,
  forward={u:[list(n) for n in ns] for u,ns in forward.items()},backward={u:[list(n) for n in ns] for u,ns in backward.items()},
  reachable_connected_sites={u:[list(np.asarray(sites)[reach[z,t]]) for t in range(H)] for z,u in enumerate(units)},
  transit_possible={u:transit[z].tolist() for z,u in enumerate(units)},original_flow_rows_exactly_checked=flow_checks,
  terminal_location='Original terminal row is sum of arcs ending at H=1; no prescribed terminal site is present. All original allowed terminal sites retained.',
  continuous_proof='Nonnegative unit flow on an acyclic time DAG decomposes into nonnegative source-to-allowed-sink paths of total mass one. Every time cut has mass one; connected stays have mass <=1. Unreachable arcs have zero mass even in the continuous relaxation.',
  graph_changed=False,removed_route_variables=0)
 write('M1_ROUTE_REACHABILITY_CERTIFICATE.json',route)
 # Extract every original homogeneous PCS16 and connection row, rather than
 # regenerate trigonometry (stored binary coefficients are authoritative).
 pcs=defaultdict(list);anchors=set(map(int,flows))|set(map(int,terminal))
 for i in np.flatnonzero(np.isin(rf,['PCS16','connected_Pch','connected_Pdis','connected_Qmax','connected_Qmin'])):
  a,b=A.indptr[i:i+2];terms={str(d['names'][j]):F(float(w)) for j,w in zip(A.indices[a:b],A.data[a:b]) if w}
  ctrl=next(n for n in terms if n.startswith(('Pch[','Pdis[','Q[')));u,s,tt=suffix(ctrl);t=int(tt)
  arc=f'arc[{u},{sites.index(s)*H+t}]';assert arc in terms
  if rf[i]=='PCS16':
   p=terms.get(f'Pdis[{u},{s},{t}]',F(0));assert terms.get(f'Pch[{u},{s},{t}]',F(0))==-p
   q=terms.get(f'Q[{u},{s},{t}]',F(0));c=-terms[arc]
   assert d['sense'][i]=='<' and d['rhs'][i]==0 and len(terms)==1+int(p!=0)*2+int(q!=0)
   pcs[u,s,t].append((p,q,c))
  else:
   v=next(j for j in A.indices[a:b] if str(d['names'][j])==ctrl)
   if rf[i].startswith('connected_P'):
    assert terms=={arc:-F(battery.p_limit),ctrl:F(1)} and d['sense'][i]=='<'
    assert d['lower'][v]==0 and d['upper'][v]==battery.p_limit
   else:
    expected={arc:F(battery.pcs_kva)*(-1 if rf[i]=='connected_Qmax' else 1),ctrl:F(1)}
    assert terms==expected and d['sense'][i]==('<' if rf[i]=='connected_Qmax' else '>')
    assert d['lower'][v]==-battery.pcs_kva and d['upper'][v]==battery.pcs_kva
   assert d['rhs'][i]==0
  anchors.add(int(i))
 faces=next(iter(pcs.values()));assert len(faces)==16 and all(v==faces for v in pcs.values())
 vertices=rational_vertices(faces,battery.p_limit,battery.pcs_kva)
 # Use exact coefficients from original energy equations, not rounded eta math.
 balances=np.flatnonzero(rf=='energy_balance');chcoef=discoef=None;cost=np.zeros((4,H),float)
 for z,u in enumerate(units):
  for t in range(H+1):
   j=names[f'SOC[{u},{t}]'];assert d['lower'][j]==battery.minimum and d['upper'][j]==battery.maximum and d['types'][j]=='C'
  for fam,t,level in [('initial_SOC',0,battery.initial),('terminal_SOC',H,battery.terminal)]:
   i=int(np.flatnonzero(rf==fam)[z]);a,b=A.indptr[i:i+2]
   assert list(A.indices[a:b])==[names[f'SOC[{u},{t}]']] and list(A.data[a:b])==[1.] and d['sense'][i]=='=' and d['rhs'][i]==level
  for t in range(H):
   i=int(balances[z*H+t]);a,b=A.indptr[i:i+2];terms={str(d['names'][j]):F(float(w)) for j,w in zip(A.indices[a:b],A.data[a:b])}
   assert terms.pop(f'SOC[{u},{t}]')==-1 and terms.pop(f'SOC[{u},{t+1}]')==1 and d['sense'][i]=='=' and d['rhs'][i]==0
   for n,w in terms.items():
    if n.startswith('Pch'):
     uu,ss,tt=suffix(n);assert uu==u and int(tt)==t and (u,ss,t) in pcs
     if chcoef is None:chcoef=-w
     assert w==-chcoef
    elif n.startswith('Pdis'):
     uu,ss,tt=suffix(n);assert uu==u and int(tt)==t and (u,ss,t) in pcs
     if discoef is None:discoef=w
     assert w==discoef
    else:
     uu,kk=suffix(n);k=int(kk);assert uu==u and arcs[k][1]==t and arcs[k][-1] is not None and w==F(arcs[k][-1].energy_kwh)
     if k in eligible[u]:cost[z,t]=max(cost[z,t],float(w))
   anchors.add(i)
 assert 0<chcoef<=discoef
 envelopes={};PQ={}
 for z,u in enumerate(units):
  lo=[F(battery.minimum)]*(H+1);hi=[F(battery.maximum)]*(H+1)
  lo[0]=hi[0]=F(battery.initial);lo[H]=hi[H]=F(battery.terminal)
  for t in range(H):
   lo[t+1]=max(lo[t+1],lo[t]-discoef*F(battery.p_limit)-F(cost[z,t]));hi[t+1]=min(hi[t+1],hi[t]+chcoef*F(battery.p_limit))
  for t in reversed(range(H)):
   lo[t]=max(lo[t],lo[t+1]-chcoef*F(battery.p_limit));hi[t]=min(hi[t],hi[t+1]+discoef*F(battery.p_limit)+F(cost[z,t]))
  assert all(l<=h for l,h in zip(lo,hi))
  envelopes[u]=dict(lower=list(map(str,lo)),upper=list(map(str,hi)),travel_upper=list(map(str,map(F,cost[z]))))
  pq=[]
  for t in range(H):
   # Aggregate C,D bounds valid with fractional mode; do not distribute these
   # SOC aggregate bounds to individual state supports (would be unsafe).
   dis=min(F(battery.p_limit),(hi[t]-lo[t+1])/discoef)
   charge=min(F(battery.p_limit),(hi[t+1]-lo[t]+F(cost[z,t]))/chcoef)
   pq.append(dict(P_lower=str(-charge),P_upper=str(dis),Q_lower=str(min(v[1] for v in vertices)),Q_upper=str(max(v[1] for v in vertices))))
  PQ[u]=pq
 anchors.update(map(int,np.flatnonzero(np.isin(rf,['initial_SOC','terminal_SOC']))))
 write('M1_SOC_ENVELOPE_CERTIFICATE.json',dict(PASS=True,exact_stored_charge_coefficient=str(chcoef),exact_stored_discharge_coefficient=str(discoef),battery=asdict(battery),envelopes=envelopes,
  proof='At any slot sum C<=Pmax*sum stay<=Pmax, sum D<=Pmax. Travel departure cost is a nonnegative convex combination <=maximum reachable departure energy. Propagate both endpoint SOC constraints forward/backward by exact rational interval arithmetic.',mode_integrality_not_assumed=True))
 write('M1_PQ_ENVELOPE_CERTIFICATE.json',dict(PASS=True,envelopes=PQ,PCS16_faces=[[str(w) for w in face] for face in faces],PCS16_vertices=[[str(w) for w in v] for v in vertices],original_PCS_rows_checked=sum(map(len,pcs.values())),connection_rows_checked=5*len(pcs),
  proof='Connected controls lie in stay_mass times the exact stored PCS16 polygon intersected with |P|<=Pmax, |Q|<=S. Sum stay mass<=1; all fractional and integer controls are contained in the convex hull of the reachable-state union and zero transit contribution.',
  SOC_aggregate_bounds_used_for_site_union_deletions=False,reason='Aggregate SOC net-power bounds do not imply per-site perspective bounds for fractional mixtures; retained loose PCS domain avoids that unsafe step.',
  mode_rows_unchanged=True))
 return dict(sites=sites,units=units,reach=reach,transit=transit,vertices=vertices,anchors=anchors,battery=battery,arcs=arcs,eligible=eligible,initial=initial)
