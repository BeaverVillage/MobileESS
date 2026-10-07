"""Finite, purely linear deterministic WAN state formulation.

All byte states use an exact rational quantum derived from payload and
nominal bottleneck rates. No pair x transfer-start binary exists.
"""
from collections import defaultdict,Counter
from dataclasses import replace
from fractions import Fraction
from functools import reduce
from math import gcd,lcm
import gurobipy as gp
from v42_compact.formulation import add_job as compact_job,intervention,values
from v42_compact.graph import reconstruct as compact_reconstruct
from v42_job_capability import validate

def authority(j,g,r):
    pairs=tuple(sorted({(k,d) for k,d,t in g.events['w']}))
    B=Fraction(r.bytes_per_gpu)*j.gpu
    rates={(k,d,t):min(max(0,r.wan_capacities.get((l,t),0)) for l in r.paths[k,d]) for k,d in pairs for t in range(r.control_end)}
    # Rates larger than payload may be capped at payload INSIDE min only:
    # min(remaining,rate) == min(remaining,min(payload,rate)).
    fractions=[B]+[Fraction(min(float(B),x)) for x in rates.values()]
    den=reduce(lcm,(x.denominator for x in fractions),1)
    num=reduce(gcd,(x.numerator*(den//x.denominator) for x in fractions))
    quantum=Fraction(num,den)
    units=int(B/quantum)
    if units>1e8:raise ValueError('EXACT_BYTE_QUANTUM_NUMERIC_RANGE_UNSUPPORTED')
    return pairs,float(quantum),units,{key:float(min(B,Fraction(x))/quantum) for key,x in rates.items()}

def add_job(m,j,g,r,*,compress=False,optional=False,eliminate_depart=None,eliminate_arrive=None,share_links=None,eliminate_f0=None,eliminate_state=None,byte_scale=1.,preserve_stay_flow=False):
    depart=compress if eliminate_depart is None else eliminate_depart
    arrive=compress if eliminate_arrive is None else eliminate_arrive
    link=compress if share_links is None else share_links
    f0_removed=compress if eliminate_f0 is None else eliminate_f0
    state_removed=compress if eliminate_state is None else eliminate_state
    if preserve_stay_flow and not g.events['w']:
        if optional:raise ValueError('OPTIONAL_TRACK_REQUIRES_MIGRATION_DOMAIN')
        # Activation may identify a currently unique STAY. Its engineering
        # fixed marker must not discard the retained source-flow authority.
        return compact_job(m,j,replace(g,fixed=None))
    if g.fixed:return compact_job(m,j,g)
    if not g.events['w']:
        if optional:raise ValueError('OPTIONAL_TRACK_REQUIRES_MIGRATION_DOMAIN')
        if f0_removed or state_removed:
            starts=tuple((k,s) for k,s in g.events['y'] if (k,s+j.service_slots) in g.events['f0'])
            v=stay(m,j,g,1,starts=starts,eliminate_f0=f0_removed,eliminate_state=state_removed);m.addConstr(gp.quicksum(v['y'].values())==1);return v
        return compact_job(m,j,g)
    pairs,quantum,B,rates=authority(j,g,r);H=r.control_end
    v={n:{key:m.addVar(vtype=gp.GRB.BINARY,name=f'{n}[{j.uid},{i}]') for i,key in enumerate(keys)} for n,keys in g.events.items() if n!='w' and not (optional and f0_removed and n=='f0')}
    v.setdefault('f0',{})
    v.update({n:{key:m.addVar(lb=0,ub=1,name=f'{n}[{j.uid},{i}]') for i,key in enumerate(keys)} for n,keys in g.states.items()})
    v['w']={}
    v['pair']={p:m.addVar(vtype=gp.GRB.BINARY,name=f'pair[{j.uid},{i}]') for i,p in enumerate(pairs)}
    starts=sorted({t for k,d,t in g.events['w']})
    v['wan_start']={t:m.addVar(vtype=gp.GRB.BINARY,name=f'wan_start[{j.uid},{t}]') for t in starts}
    active_slots=sorted({t for key,tr in g.transfers.items() for t in range(key[2],tr.end)})
    final_slots=sorted({tr.end-1 for tr in g.transfers.values() if tr.feasible and tr.restart<H})
    # In a standalone infeasible-template oracle, include its timing envelope
    # but never permit a restart-invalid final event. Production transfers are
    # all feasible and support-exact before this function is called.
    active_slots=sorted(set(active_slots)|set(starts))
    if not active_slots:raise ValueError('NO_WAN_TIMING_SUPPORT')
    first,last=min(active_slots),max(active_slots)
    boundaries=sorted(set(active_slots)|{t+1 for t in active_slots})
    v['wan_active']={t:m.addVar(vtype=gp.GRB.BINARY,name=f'wan_active[{j.uid},{t}]') for t in active_slots}
    v['wan_final']={t:m.addVar(vtype=gp.GRB.BINARY,name=f'wan_final[{j.uid},{t}]') for t in final_slots}
    v['remaining']={t:m.addVar(lb=0,ub=B,name=f'remaining[{j.uid},{t}]') for t in boundaries}
    v['sent']={t:m.addVar(lb=0,ub=B,name=f'sent[{j.uid},{t}]') for t in active_slots}
    y,q,f0,f1=(v[n] for n in ('y','q','f0','f1'));mig=gp.quicksum(q.values())
    amount=mig if optional else 1
    m.addConstr(gp.quicksum(y.values())==amount);m.addConstr(mig<=1)
    m.addConstr(gp.quicksum(f0.values())+mig==amount);m.addConstr(gp.quicksum(f1.values())==mig)
    m.addConstr(gp.quicksum(v['pair'].values())==mig)
    selected=m.addVar(lb=0,ub=1,name=f'migration_selected[{j.uid}]');v['migration_selected']={'selected':selected}
    m.addConstr(selected==gp.quicksum(v['pair'].values()))
    m.addConstr(gp.quicksum(v['wan_start'].values())==mig);m.addConstr(gp.quicksum(v['wan_final'].values())==mig)
    sources=sorted({k for k,d in pairs});dests=sorted({d for k,d in pairs})
    v['source_selected']={k:m.addVar(lb=0,ub=1) for k in sources}
    v['destination_selected']={d:m.addVar(lb=0,ub=1) for d in dests}
    src=v['source_selected'];dst=v['destination_selected']
    for k,x in src.items():m.addConstr(x==gp.quicksum(z for (a,d),z in v['pair'].items() if a==k))
    for d,x in dst.items():m.addConstr(x==gp.quicksum(z for (k,a),z in v['pair'].items() if a==d))
    for k in sources:m.addConstr(src[k]<=gp.quicksum(x for (a,s),x in y.items() if a==k))
    for (k,c),x in q.items():m.addConstr(x<=gp.quicksum(y[k,s] for s in g.compatible[k,c]))
    support=defaultdict(set)
    for k,d,t in g.events['w']:support[k,d].add(t)
    for p,x in v['pair'].items():m.addConstr(gp.quicksum(z for t,z in v['wan_start'].items() if t not in support[p])<=1-x)
    m.addConstr(v['remaining'][first]==0);m.addConstr(v['remaining'][last+1]==0)
    for t in range(first,last+1):
        start=v['wan_start'].get(t,0);a=v['wan_active'].get(t,0);f=v['wan_final'].get(t,0)
        prev=v['wan_active'].get(t-1,0);prevfinal=v['wan_final'].get(t-1,0)
        m.addConstr(a==prev+start-prevfinal);m.addConstr(f<=a)
        before=v['remaining'].get(t,0)+B*start;sent=v['sent'].get(t,0);after=v['remaining'].get(t+1,0)
        common=Counter(rates[k,d,t] for k,d in pairs).most_common(1)[0][0]
        # Identity using unique-pair total: common*M + deviations. This
        # eliminates identical pair coefficients without changing ANY rate.
        rate=common*selected+gp.quicksum((rates[k,d,t]-common)*x for (k,d),x in v['pair'].items() if rates[k,d,t]!=common)
        m.addConstr(before<=B*a);m.addConstr(before>=a)
        m.addConstr(sent<=before);m.addConstr(sent<=rate);m.addConstr(sent<=B*a)
        m.addConstr(sent>=rate-B*(1-a+f));m.addConstr(sent>=before-B*(1-f))
        m.addConstr(after==before-sent);m.addConstr(after<=B*(a-f));m.addConstr(after>=a-f)
    m.addConstr(v['wan_active'][last]==v['wan_final'].get(last,0))
    departure_keys=sorted({(k,t) for k,d,t in g.events['w']})
    v['depart']={key:(v['h'].get((key[0],key[1]-1),0)-v['h'].get(key,0)+q.get(key,0)) if depart else m.addVar(lb=0,ub=1) for key in departure_keys}
    if depart:
        for x in v['depart'].values():m.addConstr(x>=0,name='depart_projection_lower_bound')
    for t in starts:
        m.addConstr(gp.quicksum(v['depart'].get((k,t),0) for k in sources)==v['wan_start'][t])
        for k in sources:
            if (k,t) in v['depart']:m.addConstr(v['depart'][k,t]<=src[k])
    arrival_keys=sorted({(d,tr.restart) for (k,d,t),tr in g.transfers.items() if tr.feasible and tr.restart<H})
    restart_times=sorted({R for d,R in arrival_keys})
    v['arrive']={key:(v['r1'].get(key,0)-v['r1'].get((key[0],key[1]-1),0)+f1.get(key,0)) if arrive else m.addVar(lb=0,ub=1) for key in arrival_keys}
    if arrive:
        for x in v['arrive'].values():m.addConstr(x>=0,name='arrive_projection_lower_bound')
    for R in restart_times:
        m.addConstr(gp.quicksum(v['arrive'].get((d,R),0) for d in dests)==v['wan_final'][R-1-r.restart_slots])
        for d in dests:
            if (d,R) in v['arrive']:m.addConstr(v['arrive'][d,R]<=dst[d])
    leave0=defaultdict(list)
    for key,x in f0.items():leave0[key].append(x)
    for key,x in q.items():leave0[key].append(x)
    flows=(('r0',y,leave0),('h',q,{key:[x] for key,x in v['depart'].items()}),
        ('r1',v['arrive'],{key:[x] for key,x in f1.items()}))
    for n,enter,leave in flows:
        active=v[n];sites=sorted({k for k,t in active}|{k for k,t in enter}|{k for k,t in leave})
        for k in sites:
            times=[t for site,t in active if site==k]+[t for site,t in enter if site==k]+[t for site,t in leave if site==k]
            for t in range(min(times),max(times)+1):
                if (depart and n=='h' and (k,t) in v['depart']) or (arrive and n=='r1' and (k,t) in v['arrive']):continue
                m.addConstr(gp.LinExpr(active.get((k,t),0))-active.get((k,t-1),0)-enter.get((k,t),0)+gp.quicksum(leave.get((k,t),[]))==0)
    # Unique destination entry plus nonnegative unit balances and one exit
    # already force all post-run occupancy/finish to that destination.
    m.addConstr(gp.quicksum(v['r0'].values())+gp.quicksum(v['r1'].values())==j.service_slots*amount)
    m.addConstr(gp.quicksum(v['r1'].values())>=mig)
    link_keys=sorted({(l,t) for tr in g.transfers.values() for l,t,n in tr.wan if n>0})
    links=sorted({l for l,t in link_keys})
    representatives={};groups={}
    for l in links:
        incidence=tuple(p for p in pairs if l in r.paths[p]) if link else (l,)
        rep=representatives.setdefault(incidence,l);groups[l]=rep
    unique=sorted(set(groups.values()))
    universal={l for l in unique if link and all(l in r.paths[p] for p in pairs)}
    members={l:selected if l in universal else m.addVar(lb=0,ub=1) for l in unique}
    v['link_selected']={l:members[groups[l]] for l in links}
    if byte_scale<=0 or byte_scale!=2.**round(__import__('math').log2(byte_scale)):raise ValueError('BYTE_SCALE_MUST_BE_EXACT_POWER_OF_TWO')
    flow={(l,t):quantum*v['sent'][t] if l in universal else byte_scale*m.addVar(lb=0,ub=B*quantum/byte_scale,name=f'link_bytes_scaled[{j.uid},{l},{t}]') if byte_scale!=1 else m.addVar(lb=0,ub=B*quantum) for l,t in sorted({(groups[l],t) for l,t in link_keys})}
    v['link_bytes']={key:flow[groups[key[0]],key[1]] for key in link_keys}
    for l in unique:
        if l in universal:continue # sent is zero without migration; this fixed link is always on the selected path
        member=v['link_selected'][l]
        m.addConstr(member==gp.quicksum(x for p,x in v['pair'].items() if l in r.paths[p]))
        for t in (slot for link,slot in flow if link==l):
            u=flow[l,t]/byte_scale;sent=quantum*v['sent'][t]/byte_scale
            m.addConstr(u<=sent);m.addConstr(u<=B*quantum/byte_scale*member);m.addConstr(u>=sent-B*quantum/byte_scale*(1-member))
    return v

def stay(m,j,g,N,*,compress=False,starts=None,eliminate_f0=None,eliminate_state=None):
    """Exact integer histogram of fixed-duration, nonmigrating paths."""
    f0_removed=compress if eliminate_f0 is None else eliminate_f0
    state_removed=compress if eliminate_state is None else eliminate_state
    keys=tuple(g.events['y'] if starts is None else starts)
    typ=gp.GRB.BINARY if N==1 else gp.GRB.INTEGER
    y={key:m.addVar(lb=0,ub=N,vtype=typ,name=f'Y[{j.uid},{i}]') for i,key in enumerate(keys)}
    v=dict(y=y,q={},w={},f0={},f1={},r0={},h={},r1={})
    for k,s in keys:
        key=k,s+j.service_slots
        if f0_removed:v['f0'][key]=y[k,s]
        else:
            x=m.addVar(lb=0,ub=N,vtype=typ,name=f'F0_count[{j.uid},{k},{key[1]}]');v['f0'][key]=x
            m.addConstr(x==y[k,s],name='fixed_duration_count_finish')
    states=sorted({(k,t) for k,s in keys for t in range(s,s+j.service_slots)})
    # Exact same finite incidence; avoid rescanning every site's full support
    # at every slot when V2 restores long reference-tail start intervals.
    from bisect import bisect_left, bisect_right
    bysite=defaultdict(list)
    for k,s in keys:bysite[k].append(s)
    bysite={k:sorted(ss) for k,ss in bysite.items()}
    for k,t in states:
        ss=bysite[k];a=bisect_left(ss,t-j.service_slots+1);b=bisect_right(ss,t)
        expr=gp.quicksum(y[k,s] for s in ss[a:b])
        if state_removed:v['r0'][k,t]=expr
        else:
            x=m.addVar(lb=0,ub=N,name=f'R0_count[{j.uid},{k},{t}]');v['r0'][k,t]=x
            m.addConstr(x==expr,name='fixed_duration_count_occupancy')
    return v

def contributions(j,g,v):
    from v42_compact.formulation import contributions as old
    if 'pair' not in v:return old(j,g,v)
    use=defaultdict(gp.LinExpr)
    for n in ('r0','r1'):
        for (k,t),x in v[n].items():use['GPU',k,t]+=j.gpu*x
    for (l,t),x in v['link_bytes'].items():use['WAN',l,t]+=x
    for t,x in v['wan_active'].items():use['ACTIVE','',t]+=x
    return use

def mapping(j,g,r,o):
    from v42_compact.graph import old_to_compact
    a=old_to_compact(o)
    if not g.events['w']:return a
    pairs,quantum,B,rates=authority(j,g,r);H=r.control_end
    a['w']={};a['pair']={};a['migration_selected']={'selected':int(o.migrated)};a['source_selected']={};a['destination_selected']={};a['link_selected']={};a['wan_start']={};a['wan_active']={};a['wan_final']={};a['remaining']={};a['sent']={};a['depart']={};a['arrive']={};a['link_bytes']={}
    if o.migrated:
        a['source_selected'][o.initial_site]=1;a['destination_selected'][o.destination]=1
        a['link_selected']={l:1 for l in r.paths[o.initial_site,o.destination]}
        a['pair'][o.initial_site,o.destination]=1;a['wan_start'][o.transfer_start]=1
        a['wan_final'][o.transfer_end-1]=1;a['depart'][o.initial_site,o.transfer_start]=1;a['arrive'][o.destination,o.restart_end]=1
        amount=defaultdict(float)
        for l,t,n in o.wan:a['link_bytes'][l,t]=n;amount[t]=n/quantum
        left=0.
        for t in range(H):
            a['remaining'][t]=left
            if t==o.transfer_start:left=B
            if o.transfer_start<=t<o.transfer_end:
                a['wan_active'][t]=1;a['sent'][t]=amount[t];left-=amount[t]
        a['remaining'][H]=left
    return a

def reconstruct(j,b,r,g,a):
    if 'pair' not in a:return compact_reconstruct(j,b,r,g,a)
    from v42_boundary.generator import Generator
    from v42_compact.graph import old_to_compact
    chosen=lambda n:[k for k,x in a[n].items() if x>.5]
    pairs=chosen('pair');starts=chosen('wan_start');q=chosen('q')
    if len(pairs)!=len(starts) or len(pairs)!=len(q) or len(q)>1:raise ValueError('WAN_EVENT_CARDINALITY')
    old={n:a[n] for n in ('y','q','w','f0','f1','r0','h','r1')};old['w']={}
    if q:
        k,d=pairs[0];tau=starts[0];key=(k,d,tau)
        if key not in g.transfers:raise ValueError('UNSUPPORTED_PAIR_TIME')
        old['w'][key]=1
    o=compact_reconstruct(j,b,r,g,old);expected=mapping(j,g,r,o)
    for n in a:
        if n=='tie_rank':continue
        for key in set(a[n])|set(expected.get(n,{})):
            want=expected.get(n,{}).get(key,0);got=a[n].get(key,0)
            if abs(got-want)>max(1e-5,abs(want)*1e-9):raise ValueError('NONPHYSICAL_FACTORIZED_STATE:'+n+':'+str(key))
    validate(j,o,b,r);return o

def tie_expression(m,j,old,g,v,offset):
    """Exactly retain PR99's global event ranks, including removed keys.

    One continuous rank and two finite conditional rows per pair implement
    the pair-specific lookup against the global start event. No product
    binary (or pair/time product continuous variable) is introduced.
    """
    ranks={};rank=offset
    for n in ('y','q','w','f0','f1'):
        for key in old.events[n]:rank+=1;ranks[n,key]=rank
    expr=gp.quicksum(ranks[n,key]*x for n in ('y','q','f0','f1') for key,x in v[n].items())
    if 'pair' not in v:return expr+gp.quicksum(ranks['w',key]*x for key,x in v['w'].items()),rank
    # Subtract the job's offset in the table to avoid unnecessary large M.
    localmax=sum(len(keys) for keys in old.events.values())
    z=m.addVar(lb=0,ub=localmax,name=f'tie_w_rank[{j.uid}]');v['tie_rank']={'w':z}
    mig=gp.quicksum(v['pair'].values());m.addConstr(z<=localmax*mig)
    for p,x in v['pair'].items():
        lookup=gp.quicksum((ranks['w',(p[0],p[1],t)]-offset)*start for t,start in v['wan_start'].items() if (p[0],p[1],t) in old.transfers)
        m.addConstr(z-lookup<=localmax*(1-x));m.addConstr(lookup-z<=localmax*(1-x))
    return expr+z+offset*mig,rank
