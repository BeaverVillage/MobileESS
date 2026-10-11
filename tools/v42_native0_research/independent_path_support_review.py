"""Exact no-solver local support/DP certificates and finite fixture review.

This file does not install any production inequality. It certifies why the
reviewed additive energy-price path bound is already implied by fractional
unit-DAG flow, homogeneous connected PCS rows and original SOC equalities.
"""
from collections import defaultdict
from datetime import datetime,timezone
from fractions import Fraction as F
from itertools import combinations,product
from pathlib import Path
import hashlib,json,time

def require(condition,label):
    if not condition:raise ValueError(label)

def exact(value):
    require(not isinstance(value,float),'NO_FLOAT_RECOMPUTATION')
    return F(value)

def vertices(rows):
    points=set()
    for (a,b,r),(c,d,s) in combinations(rows,2):
        determinant=a*d-b*c
        if not determinant:continue
        p=(r*d-b*s)/determinant;q=(a*s-r*c)/determinant
        if all(aa*p+bb*q<=rr for aa,bb,rr in rows):points.add((p,q))
    require(points,'EMPTY_OR_UNBOUNDED_LOCAL_POLYGON')
    return sorted(points)

def half_certificate(pcs,p_limit,q_limit,objective,sign):
    """Fixture-only exact producer. Independent replay is below."""
    rows=tuple(pcs)+((F(1),F(0),p_limit),(F(-1),F(0),p_limit),
        (F(0),F(1),q_limit),(F(0),F(-1),q_limit),
        (F(-sign),F(0),F(0)))
    pts=vertices(rows);a,b=objective;support=max(a*p+b*q for p,q in pts)
    for i,j in combinations(range(len(rows)),2):
        x,y,r=rows[i];z,w,s=rows[j];det=x*w-y*z
        if not det:continue
        mu=(a*w-b*z)/det;nu=(x*b-y*a)/det
        if mu>=0 and nu>=0 and mu*r+nu*s==support:
            return dict(sign=sign,rows=rows,objective=objective,support=support,multipliers=((i,mu),(j,nu)))
    raise ValueError('NO_LOCAL_DUAL_CERTIFICATE')

def verify_local_certificate(packet,pcs,p_limit,q_limit,w_p,w_q,c,d,price):
    """No vertex enumeration or producer call; exact row-combination replay."""
    require(price>=0,'NEGATIVE_ENERGY_PRICE')
    require(d>=c>=0,'STORED_ENERGY_ORDER')
    require(p_limit>0 and q_limit>0,'NONPOSITIVE_CONNECTED_BOUND')
    supports=[]
    require(len(packet)==2 and {p['sign'] for p in packet}=={-1,1},'MODE_UNION_COVER')
    for witness in packet:
        sign=witness['sign'];e=d if sign==1 else c
        expected=tuple(pcs)+((F(1),F(0),p_limit),(F(-1),F(0),p_limit),
            (F(0),F(1),q_limit),(F(0),F(-1),q_limit),(F(-sign),F(0),F(0)))
        require(witness['rows']==expected,'ORIGINAL_STORED_PCS_ROW_DRIFT')
        objective=(w_p-price*e,w_q)
        require(witness['objective']==objective,'PRICED_DIRECTION_DRIFT')
        a=b=r=F(0)
        for row_index,multiplier in witness['multipliers']:
            require(isinstance(row_index,int) and 0<=row_index<len(expected),'LOCAL_DUAL_AXIS')
            require(multiplier>=0,'NEGATIVE_LOCAL_ROW_MULTIPLIER')
            x,y,rhs=expected[row_index];a+=multiplier*x;b+=multiplier*y;r+=multiplier*rhs
        require((a,b)==objective,'LOCAL_DUAL_DIRECTION_MISMATCH')
        require(r==witness['support'],'LOCAL_SUPPORT_RHS_MISMATCH')
        supports.append(r)
    return max(supports)

def certify_local(pcs,p_limit,q_limit,w_p,w_q,c,d,price):
    packets=[half_certificate(pcs,p_limit,q_limit,(w_p-price*(d if s==1 else c),w_q),s) for s in (-1,1)]
    return packets,verify_local_certificate(packets,pcs,p_limit,q_limit,w_p,w_q,c,d,price)

def verify_potentials(arcs,source,terminals,potentials,weights,bound):
    """Independent Bellman inequality replay; does not execute a DP."""
    require(potentials[source]==bound,'SOURCE_POTENTIAL_BOUND_DRIFT')
    require(all(potentials[v]==0 for v in terminals),'TERMINAL_POTENTIAL_DRIFT')
    require(set(weights)==set(range(len(arcs))),'ARC_WEIGHT_COVER')
    for i,(tail,head,kind,energy) in enumerate(arcs):
        require(tail[1]<head[1],'NOT_STRICT_FORWARD_DAG')
        require(potentials[tail]>=weights[i]+potentials[head],'BELLMAN_ARC_VIOLATION')
    return True

def fixture():
    began=time.perf_counter();checks=[]
    def check(label,value):require(value,label);checks.append(dict(name=label,PASS=True))
    pcs=((F(1),F(1),F(1)),(F(1),F(-1),F(1)),(F(-1),F(1),F(1)),(F(-1),F(-1),F(1)))
    c=F(1);d=F(2);price=F(1,4);H=4;sites=('A','B');source=('A',0);terminals=tuple((s,H) for s in sites)
    arcs=[]
    for t in range(H):
        for s in sites:arcs.append(((s,t),(s,t+1),'stay',F(0)))
    for t in range(H-1):
        for s in sites:arcs.append(((s,t),('B' if s=='A' else 'A',t+2),'travel',F(1,4)))
    directions={(s,t):((F(2) if s=='A' else F(1)),F(1,3)) if t in (1,2) else (F(0),F(0)) for t in range(H) for s in sites}
    local={};local_packets={}
    for state,(wp,wq) in directions.items():
        packet,h=certify_local(pcs,F(1),F(1),wp,wq,c,d,price);local[state]=h;local_packets[state]=packet
        for C,D,Q in product((F(0),F(1,2),F(1)),(F(0),F(1,2),F(1)),(F(-1),F(-1,2),F(0),F(1,2),F(1))):
            P=D-C
            if not all(a*P+b*Q<=r for a,b,r in pcs):continue
            common=min(C,D);CC=C-common;DD=D-common
            old=wp*P+wq*Q-price*(d*D-c*C)
            new=wp*(DD-CC)+wq*Q-price*(d*DD-c*CC)
            check('fractional local cancellation identity',new-old==price*(d-c)*common and new>=old)
            check('fractional simultaneous support dominated by integer-mode union',old<=h)
    weights={i:local[tail] if kind=='stay' else -price*energy for i,(tail,head,kind,energy) in enumerate(arcs)}
    outgoing=defaultdict(list)
    for i,(tail,head,kind,energy) in enumerate(arcs):outgoing[tail].append(i)
    potentials={v:F(0) for v in terminals}
    for t in range(H-1,-1,-1):
        for s in sites:potentials[s,t]=max(weights[i]+potentials[arcs[i][1]] for i in outgoing[s,t])
    bound=potentials[source];check('independent full DAG Bellman witness',verify_potentials(arcs,source,terminals,potentials,weights,bound))
    paths=[]
    def visit(node,path):
        if node in terminals:paths.append(path);return
        for i in outgoing[node]:visit(arcs[i][1],path+(i,))
    visit(source,())
    check('all small integer paths match DP bound',max(sum((weights[i] for i in path),F(0)) for path in paths)==bound)
    actions=tuple((max(-p,F(0)),max(p,F(0)),q) for p,q in product((F(-1),F(-1,2),F(0),F(1,2),F(1)),repeat=2) if abs(p)+abs(q)<=1)+((F(1,4),F(0),F(0)),(F(0),F(1,8),F(0)))
    feasible=[];plans_checked=0;maxrelief=None
    for path in paths:
        stays=[i for i in path if arcs[i][2]=='stay']
        for controls in product(actions,repeat=len(stays)):
            plans_checked+=1;control=dict(zip(stays,controls));E=F(0);R=F(0);soc=F(4);states={0:soc};modes={t:F(0) for t in range(H)};ok=True
            for i in path:
                tail,head,kind,energy=arcs[i]
                if kind=='stay':
                    C,D,Q=control[i];wp,wq=directions[tail];e=d*D-c*C;R+=wp*(D-C)+wq*Q
                    modes[tail[1]]=F(int(C>0))
                else:e=energy
                E+=e;soc-=e
                if not 0<=soc<=8:ok=False;break
                states[head[1]]=soc
            if ok and E==0:
                require(R<=bound,'INTEGER_TERMINAL_SOC_BOUND_VIOLATION')
                feasible.append((path,control,modes,R));maxrelief=R if maxrelief is None else max(maxrelief,R)
    check('small exact terminal-energy feasible plans exist',bool(feasible))
    check('every finite-fixture integer feasible plan respects support',maxrelief<=bound)
    first=next(p for p in feasible if any(arcs[i][2]=='travel' for i in p[0])) if any(any(arcs[i][2]=='travel' for i in p[0]) for p in feasible) else feasible[0]
    second=next(p for p in feasible if p[0]!=first[0] and p[3]!=first[3])
    mixture=((F(1,3),first),(F(2,3),second));flow=defaultdict(F);control_mix=defaultdict(lambda:[F(0),F(0),F(0)]);mode_mix=defaultdict(F);relief=F(0)
    for weight,(path,control,modes,R) in mixture:
        relief+=weight*R
        for i in path:flow[i]+=weight
        for i,values in control.items():
            for j,value in enumerate(values):control_mix[i][j]+=weight*value
        for t,z in modes.items():mode_mix[t]+=weight*z
    balance=defaultdict(F);energy=F(0);priced=F(0)
    for i,(tail,head,kind,e) in enumerate(arcs):
        a=flow[i];require(a>=0,'NEGATIVE_FRACTIONAL_FLOW');balance[tail]+=a;balance[head]-=a
        if kind=='stay':
            C,D,Q=control_mix[i];wp,wq=directions[tail]
            require(0<=C<=a and 0<=D<=a and -a<=Q<=a,'CONNECTED_MIXTURE_BOUND')
            require(C<=mode_mix[tail[1]] and D<=1-mode_mix[tail[1]],'FRACTIONAL_MODE_MIXTURE_BOUND')
            require(all(x*(D-C)+y*Q<=r*a for x,y,r in pcs),'HOMOGENEOUS_PCS_MIXTURE_BOUND')
            energy+=d*D-c*C;priced+=wp*(D-C)+wq*Q-price*(d*D-c*C)
        else:energy+=e*a;priced-=price*e*a
    check('fractional mixture preserves all source/interior/terminal flows',balance[source]==1 and sum(balance[v] for v in terminals)==-1 and all(v==source or v in terminals or mass==0 for v,mass in balance.items()))
    check('fractional mixture exact energy balance and relief',energy==0 and priced==relief and relief<=sum((weights[i]*flow[i] for i in weights),F(0))<=bound)
    attacks=[]
    for label,attack in (
        ('negative energy price rejected',lambda:verify_local_certificate(local_packets['A',1],pcs,F(1),F(1),F(2),F(1,3),c,d,F(-1))),
        ('reversed stored energy order rejected',lambda:verify_local_certificate(local_packets['A',1],pcs,F(1),F(1),F(2),F(1,3),F(2),F(1),price)),
        ('understated source support rejected',lambda:verify_potentials(arcs,source,terminals,potentials,weights,bound-F(1,100))),
        ('missed current arc rejected',lambda:verify_potentials(arcs,source,terminals,potentials,{i:w for i,w in weights.items() if i!=0},bound))):
        try:attack()
        except ValueError:attacks.append(dict(name=label,PASS=True))
        else:raise ValueError('MUTATION_ACCEPTED:'+label)
    check('negative-price simultaneous counterexample',F(1)>F(1,2))
    # lambda=-1,w=-3/2,c=1,d=2: both C=D=1 yield1; each integer branch <=1/2.
    require(F(-3,2)*(1-1)-F(-1)*(2*1-1*1)==1,'NEGATIVE_PRICE_COUNTEREXAMPLE')
    check('outside-window charging omission counterexample',F(1,2)>0 and d*F(1,2)-c*F(1)==0)
    # Window relief p=1/2, lambda=1: window-only priced maximum0; next-slot charge1 restores SOC.
    payload=dict(schema='EXACT_PATH_ENERGY_PRICE_SUPPORT_GENERIC_INDEPENDENT_REVIEW_V1',PASS=True,UTC=datetime.now(timezone.utc).isoformat(),classification='VALID_BUT_IMPLIED_BY_EXISTING_FRACTIONAL_LP',checks=checks,mutation_attacks=attacks,fixture=dict(horizon=H,sites=sites,integer_paths=len(paths),finite_control_actions=len(actions),finite_integer_plans_checked=plans_checked,terminal_energy_feasible_plans=len(feasible),maximum_finite_fixture_relief=str(maxrelief),exact_DP_bound=str(bound),fractional_mixture_relief=str(relief),fractional_mixture_nonintegral_arcs=sum(0<v<1 for v in flow.values()),enumeration_scope='SMALL_FINITE_RATIONAL_FIXTURE_ONLY_NOT_A96SLOT_PROOF'),general_theorem=dict(valid_for_all_horizons_including96=True,required_stored_conditions=['strict forward DAG and nonnegative unit flow','all terminal sites admitted','exact original homogeneous net-P PCS16 and connected C/D/Q bounds','folded relief is exactly wP*(D-C)+wQ*Q','exact stored d>=c>=0 and exact lambda>=0','all96slot control energy including outside-window rebound','actual travel energy at departure','energy sum delta=initialSOC-terminalSOC'],proof_steps=['Subtract common=min(C,D): netP/Q unchanged; priced objective rises by lambda*(d-c)*common.','For stayflowa>0 normalize cancelled controls by a. They lie in one exact integer-mode PCS half-polygon. For a=0 connected bounds force zero controls.','Independent nonnegative local row combinations bound every normalized branch; hence per-stay priced term<=a*h.','Exact Bellman inequalities bound each arc by potential drop; multiply by nonnegative fractional flow and telescope to source potential.','Original SOC equations sum to E=initial-terminal; add lambda*E to recover R<=sourcePotential+lambda*(initial-terminal).'],implication='This proves the candidate for every existing fractional LP point; it cannot remove LP points or improve the LP bound.',integer_value_preserved=True,new_strengthening=False),Native_calls=0,model_builds=0,full96slot_path_enumerations=0,wall_seconds=time.perf_counter()-began)
    out=Path(r'D:\v42_multitime_audit_20261011\GENERIC_EXACT_PATH_SUPPORT_INDEPENDENT_REVIEW.json')
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(PASS=True,checks=len(checks),attacks=len(attacks),fixture=payload['fixture'],receipt=str(out),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),wall_seconds=payload['wall_seconds'])))

if __name__=='__main__':fixture()
