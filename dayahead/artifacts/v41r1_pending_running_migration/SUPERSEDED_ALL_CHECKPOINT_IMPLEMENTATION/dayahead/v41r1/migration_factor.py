"""Exact all-checkpoint state formulation with the original finite-domain rank."""
import gurobipy as gp
from gurobipy import GRB
from .migration import BEGIN,END
from .migration_choices import CompactChoices
from dayahead.v40g.domain import Option


def eligible(row,opts):return isinstance(opts,CompactChoices)


def compile(model,row,opts,costs,index,load,wan_active,*,inject_reference=False):
    assert isinstance(opts,CompactChoices)
    gpu=row['requested_GPU'];duration=row['safe_duration_slots'];length=opts.length
    stay={};routes={};source_cp={};arrivals={};ends={};gaps={};dev=gp.LinExpr();tie=gp.LinExpr()
    def binary(name,start=0):
        v=model.addVar(vtype=GRB.BINARY,name=name);v.Start=start
        if inject_reference:v.LB=start;v.UB=start
        return v
    for site in opts.initial:
        opt=Option(site,row['start_slot'],row['end_slot']);k=opts.index(opt)
        v=binary(f'placement[{index},{site}]',int(site==row['AIDC_site']));stay[opt]=v
        dev+=costs[k]*v;tie+=(index+1)*(k+1)*v
        for t in range(max(BEGIN,opt.start),min(END,opt.end)):load[t-BEGIN,site]+=gpu*v
    for source,destination in opts.routes:
        v=binary(f'migration_route[{index},{source},{destination}]');routes[source,destination]=v
        rank=opts.prefix[destination]+int(destination in opts.initial)+1+opts.sources[destination].index(source)
        tie+=(index+1)*rank*v
    migration=gp.quicksum(routes.values());dev+=2*gpu*duration*migration
    model.addConstr(gp.quicksum(stay.values())+migration==1)
    for source in opts.initial:
        for ordinal,cp in enumerate(opts.cps):
            v=binary(f'checkpoint_source[{index},{source},{cp}]');source_cp[source,cp]=v
            if source==row['AIDC_site']:dev-=2*gpu*(cp-row['start_slot'])*v
            tie+=(index+1)*opts.nsource*ordinal*v
            for t in range(max(BEGIN,row['start_slot']),cp):load[t-BEGIN,source]+=gpu*v
        model.addConstr(gp.quicksum(v for (s,c),v in source_cp.items() if s==source)==
            gp.quicksum(v for (s,d),v in routes.items() if s==source))
    minimum_restart=min(max(BEGIN+2,c)+length+1 for c in opts.cps)
    gap_values=sorted({g for g,c in opts.pairs})
    for destination in opts.sites:
        if not opts.sources[destination]:continue
        dest_selected=gp.quicksum(v for (s,d),v in routes.items() if d==destination)
        for restart in range(minimum_restart,END):
            v=binary(f'destination_start[{index},{destination},{restart}]');arrivals[destination,restart]=v
            if destination==row['AIDC_site']:dev-=2*gpu*max(0,row['end_slot']-restart)*v
            for t in range(restart,END):load[t-BEGIN,destination]+=gpu*v
            for t in range(restart-1-length,restart-1):wan_active[t]+=v
        for end in range(min(END,row['end_slot']+min(gap_values)),END+1):
            v=binary(f'destination_release_capped_D24[{index},{destination},{end}]');ends[destination,end]=v
            for t in range(end,END):load[t-BEGIN,destination]-=gpu*v
        model.addConstr(gp.quicksum(v for (d,r),v in arrivals.items() if d==destination)==dest_selected)
        model.addConstr(gp.quicksum(v for (d,e),v in ends.items() if d==destination)==dest_selected)
    for gap in gap_values:
        v=binary(f'migration_pause_slots[{index},{gap}]');gaps[gap]=v
        previous=sum(g<gap for g,c in opts.pairs)
        excluded=sum(max(BEGIN+2,c)+length+1>c+gap for c in opts.cps)
        tie+=(index+1)*opts.nsource*(previous-excluded)*v
    model.addConstr(gp.quicksum(gaps.values())==migration)
    checkpoint=gp.quicksum(c*v for (s,c),v in source_cp.items())
    restart=gp.quicksum(r*v for (d,r),v in arrivals.items())
    pause=gp.quicksum(g*v for g,v in gaps.items())
    model.addConstr(restart-checkpoint==pause)
    implied_completion=model.addVar(vtype=GRB.INTEGER,lb=0,ub=row['end_slot']+max(gap_values),name=f'derived_completion_scalar[{index}]')
    model.addConstr(implied_completion==row['end_slot']*migration+pause)
    capped=model.addVar(vtype=GRB.INTEGER,lb=0,ub=END,name=f'derived_D24_capped_release[{index}]')
    model.addGenConstrMin(capped,[implied_completion],constant=END)
    model.addConstr(gp.quicksum(e*v for (d,e),v in ends.items())==capped)
    # This is the inherited WAN release bound; the global cursor also enforces
    # UID order, exact start=max(previous completion,selected checkpoint).
    model.addConstr(restart>=(BEGIN+2+length+1)*migration)
    model.addConstr(restart>=checkpoint+(length+1)*migration)
    return dict(stay=stay,routes=routes,source_cp=source_cp,arrivals=arrivals,ends=ends,gaps=gaps,
        migration=migration,start=restart-(length+1)*migration,length=length*migration,checkpoint=checkpoint,
        deviation=dev,tie=tie,domain=opts,original_option_count=len(opts),
        factored_choice_count=len(stay)+len(routes)+len(source_cp)+len(arrivals)+len(ends)+len(gaps))


def selected(factor,row):
    for opt,v in factor['stay'].items():
        if v.X>.5:return opt
    source,destination=next(pair for pair,v in factor['routes'].items() if v.X>.5)
    src,cp=next(pair for pair,v in factor['source_cp'].items() if v.X>.5)
    dest,restart=next(pair for pair,v in factor['arrivals'].items() if v.X>.5)
    assert source==src and destination==dest
    opt=factor['domain'].make(source,destination,cp,restart-cp)
    assert opt in factor['domain']
    return opt


def verify_gate():
    from dayahead.paper_analysis.storage import read
    from dayahead.v41.preflight import OUT,record
    from dayahead.v41.reserve import require
    gate=read(OUT/'EXACT_COMPRESSION_GATE.json')
    require(gate['status']=='PASS' and gate['equivalence_test_count']>=6,'EXACT_COMPRESSION_GATE_NOT_PASSED')
    for ref in gate['sources']+[gate['test_results']]:
        require(ref==record(ref['path']),'COMPRESSION_EQUIVALENCE_EVIDENCE_DRIFT')
    return gate
