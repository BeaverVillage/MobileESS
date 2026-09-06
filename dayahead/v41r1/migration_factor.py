"""Exact factorization of existing option columns with uniform transfer duration.

Every feasible route/arrival pair maps bijectively to one enumerated Option.
The native option-rank P5 is split algebraically, without a new tie rule.
"""
from collections import defaultdict
import gurobipy as gp
from gurobipy import GRB
from .migration import pending_in_day,BEGIN,END
from dayahead.v40g.domain import Option


def eligible(row,opts):
    moves=[o for o in opts if o.migrated]
    return pending_in_day(row) and bool(moves) and len({o.transfer_end-o.transfer_start for o in moves})==1


def compile(model,row,opts,costs,index,load,wan_active,*,inject_reference=False):
    gpu=row['requested_GPU'];duration=row['safe_duration_slots'];by_arrival=defaultdict(list)
    cp=next(o.checkpoint for o in opts if o.migrated)
    from .migration import checkpoints
    assert {o.checkpoint for o in opts if o.migrated}==set(checkpoints(row))
    length=next(o.transfer_end-o.transfer_start for o in opts if o.migrated)
    for k,o in enumerate(opts):
        if o.migrated:by_arrival[o.site,o.transfer_end+1].append((k,o))
    rank={};base={};pairs=set()
    for key,values in by_arrival.items():
        base[key]=values[0][0]+1
        for position,(k,o) in enumerate(values):
            pair=(o.initial_site,o.site);pairs.add(pair)
            assert k+1==base[key]+position
            if pair in rank:assert rank[pair]==position
            rank[pair]=position
    # Equal source sets at every arrival prove that route/arrival marginals
    # introduce no option absent from the original finite domain.
    for destination in {d for s,d in pairs}:
        sets=[{o.initial_site for k,o in values} for (d,r),values in by_arrival.items() if d==destination]
        assert all(s==sets[0] for s in sets)
    stay={};routes={};arrivals={};dev=gp.LinExpr();tie=gp.LinExpr()
    reference=Option(row['AIDC_site'],row['start_slot'],row['end_slot'])
    def binary(name,start=0):
        v=model.addVar(vtype=GRB.BINARY,name=name);v.Start=start
        if inject_reference:v.LB=start;v.UB=start
        return v
    for k,o in enumerate(opts):
        if o.migrated:continue
        v=binary(f'placement[{index},{k}]',int(o==reference));stay[o]=v
        dev+=costs[k]*v;tie+=(index+1)*(k+1)*v
        for s,a,b in o.segments(row):
            for t in range(max(BEGIN,a),min(END,b)):load[t-BEGIN,s]+=gpu*v
    for source,destination in sorted(pairs):
        v=binary(f'migration_route[{index},{source},{destination}]');routes[source,destination]=v
        overlap=cp-row['start_slot'] if source==row['AIDC_site'] else 0
        dev+=gpu*(2*duration-2*overlap)*v
        tie+=(index+1)*rank[source,destination]*v
    for source in sorted({s for s,d in pairs}):
        source_choice=model.addVar(vtype=GRB.BINARY,name=f'migration_source[{index},{source}]')
        model.addConstr(source_choice==gp.quicksum(v for (s,d),v in routes.items() if s==source))
        for t in range(max(BEGIN,row['start_slot']),min(END,cp)):load[t-BEGIN,source]+=gpu*source_choice
    for (destination,restart),values in sorted(by_arrival.items()):
        v=binary(f'migration_arrival[{index},{destination},{restart}]');arrivals[destination,restart]=v
        opt=values[0][1]
        for t in range(restart,min(END,opt.end)):load[t-BEGIN,destination]+=gpu*v
        overlap=max(0,min(row['end_slot'],opt.end)-max(row['start_slot'],restart)) if destination==row['AIDC_site'] else 0
        dev-=2*gpu*overlap*v;tie+=(index+1)*base[destination,restart]*v
        for t in range(restart-1-length,restart-1):wan_active[t]+=v
    for destination in sorted({d for s,d in pairs}):
        model.addConstr(gp.quicksum(v for (s,d),v in routes.items() if d==destination)==
            gp.quicksum(v for (d,r),v in arrivals.items() if d==destination))
    migration=gp.quicksum(routes.values());model.addConstr(gp.quicksum(stay.values())+migration==1)
    start=gp.quicksum((r-1-length)*v for (d,r),v in arrivals.items())
    return dict(stay=stay,routes=routes,arrivals=arrivals,migration=migration,start=start,length=length*migration,
        deviation=dev,tie=tie,checkpoint=cp,remaining=duration-(cp-row['start_slot']),
        original_option_count=len(opts),factored_choice_count=len(stay)+len(routes)+len(arrivals))


def selected(factor,row):
    for opt,v in factor['stay'].items():
        if v.X>.5:return opt
    source,destination=next(pair for pair,v in factor['routes'].items() if v.X>.5)
    dest,restart=next(pair for pair,v in factor['arrivals'].items() if v.X>.5)
    assert destination==dest
    length=round(factor['length'].getValue())
    return Option(dest,row['start_slot'],restart+factor['remaining'],factor['checkpoint'],
        restart-1-length,restart-1,source)


def verify_gate():
    from dayahead.paper_analysis.storage import read
    from dayahead.v41.preflight import OUT,record
    from dayahead.v41.reserve import require
    gate=read(OUT/'EXACT_COMPRESSION_GATE.json')
    from .migration import CONTRACT
    require(gate.get('contract')==CONTRACT,'SUPERSEDED_COMPRESSION_CONTRACT')
    require(gate['status']=='PASS' and gate['equivalence_test_count']>=6,'EXACT_COMPRESSION_GATE_NOT_PASSED')
    for ref in gate['sources']+[gate['test_results']]:
        require(ref==record(ref['path']),'COMPRESSION_EQUIVALENCE_EVIDENCE_DRIFT')
    return gate
