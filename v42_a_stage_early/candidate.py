"""Concrete physical class columns, never fractional block directions.

An equivalent class-column representation has normalization sum(theta)=1.
Each column is an ORIGINAL locally feasible assignment of every class member.
Its coefficient vector is the sum of original physical path couplings. For a
frozen global Pi, lambda=the independently certified active local box/row dual
bound is a legal normalization potential. rc=-Pi.Bz-lambda is evaluated as an
exact rational. No native primitive RC or fractional closure is inferred.
"""
from dataclasses import asdict
from fractions import Fraction
import numpy as np
from v42_job_capability import Option
from v42_root.factor import mapping
from v42_a_stage_domain_v2.active import indexed_contains, _graph
from v42_a_stage_domain_v2.domain import graph_content_hash
from v42_a_stage_domain_v2.fast_pricing import physical_option_coefficients
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_phase1.backend import evaluate
from v42_pr134_b1.common import digest

def point_for_option(cache, job, resources, option, cardinality):
    values=mapping(job,cache['graph'],resources,option)
    point=np.zeros(cache['snapshot'].matrix.shape[1]);assigned=set()
    for unit in cache['units']:
        count=cardinality if unit['stay_count'] or unit.get('summed_identical_continuous_lanes') else 1
        use=not unit['optional'] if not option.migrated else not unit['stay_count']
        for family,items in unit['v'].items():
            for key,e in items.items():
                want=count*values.get(family,{}).get(key,0) if use else 0
                if e[0]=='v':point[e[1]]=want;assigned.add(int(e[1]))
    for unit in cache['units']:
        count=cardinality if unit['stay_count'] or unit.get('summed_identical_continuous_lanes') else 1
        use=not unit['optional'] if not option.migrated else not unit['stay_count']
        for family,items in unit['v'].items():
            for key,e in items.items():
                if e[0]=='e' and len(e[2])==1 and int(e[2][0]) not in assigned:
                    want=count*values.get(family,{}).get(key,0) if use else 0
                    point[e[2][0]]=(want-e[1])/e[3][0];assigned.add(int(e[2][0]))
    return point

def exact_coupling(B, point):
    result={}
    for row in range(B.shape[0]):
        first,last=B.indptr[row:row+2]
        value=sum((Fraction(float(a))*Fraction(float(point[j])) for j,a in zip(B.indices[first:last],B.data[first:last]) if point[j]),Fraction(0))
        if value:result[row]=value
    return result

def physical_price(option,job,raw,bundle,axes,pi,cardinality,potential):
    coefficients=physical_option_coefficients(option,job,raw,bundle,axes)
    vector={axes[key]:value*cardinality/(2**20 if key[0]=='WAN' else 1) for key,value in coefficients.items() if value}
    return -sum((Fraction(float(pi[row]))*value for row,value in vector.items()),Fraction(0))-Fraction(potential),vector

def validate(cache,job,bound,resources,domain,raw,bundle,axes,pi,cardinality,potential,option,class_id):
    if not indexed_contains(job,bound,resources,domain,option):raise ValueError('CANDIDATE_PHYSICAL_MEMBERSHIP_FAIL')
    point=point_for_option(cache,job,resources,option,cardinality)
    replay=primal_replay(cache['snapshot'],point)
    if not replay['PASS']:raise ValueError('CANDIDATE_NATIVE_LOCAL_FEASIBILITY_FAIL:'+str(replay))
    price,physical=physical_price(option,job,raw,bundle,axes,pi,cardinality,potential)
    native=exact_coupling(cache['B'],point)
    if native!=physical:raise ValueError('CANDIDATE_ORIGINAL_COUPLING_RECONSTRUCTION_FAIL')
    independent=-sum((Fraction(float(pi[r]))*v for r,v in native.items()),Fraction(0))-Fraction(potential)
    if price!=independent:raise ValueError('CANDIDATE_EXACT_PRICE_REPLAY_FAIL')
    identity=digest((class_id,asdict(option),cardinality))
    return dict(class_id=class_id,option=option,price=price,candidate_id=identity,
        identity=(class_id,option.initial_site,option.start,repr(option)),
        kind='MIGRATION' if option.migrated else 'STAY',cardinality=cardinality,
        native_local_replay=replay,physical_membership_PASS=True,exact_coupling_PASS=True,
        independent_price_PASS=True,normalization_potential=str(potential),
        coupling=tuple((r,str(v)) for r,v in sorted(native.items())),
        coefficient_sha256=digest(tuple((r,str(v)) for r,v in sorted(native.items()))),
        reduced_cost_definition='exact equivalent class-column normalization potential = certified active native local dual bound',
        original_native_primitive_RC_asserted=False)

def migration_witnesses(cache, point, job, domain):
    """Deterministic physical candidates supported by positive oracle events.

    This bounded recovery never claims migration or fractional closure.
    Every yielded path is independently checked against the complete domain.
    """
    ys=set();qs=set();pairs=set();times=set()
    for unit in cache['units']:
        if unit['stay_count']:continue
        for family,target in [('y',ys),('q',qs),('pair',pairs),('wan_start',times)]:
            target.update(key for key,e in unit['v'].get(family,{}).items() if evaluate(e,point)>1e-9)
    if not ys or not qs or not pairs or not times:return
    for start,source,cp,physical,dest,gpu,taus in domain.blocks:
        if (source,start) not in ys or (source,cp) not in qs or (source,dest) not in pairs:continue
        for tau in sorted(times):
            if tau not in taus:continue
            transfer=domain.cache.transfer(source,dest,job.gpu,tau)
            end=transfer.restart+job.service_slots-(cp-start)
            yield Option(start,source,((source,start,cp),(dest,transfer.restart,end)),cp,physical,dest,tau,transfer.end,transfer.restart,transfer.wan)

def recover(cache,data,domains,ledger,key,coupling_pi,potential,oracle_point,epsilon,budget):
    uid=data[7]['classes'][key][0];job=data[1][uid];count=len(data[7]['classes'][key]);domain=domains[uid]
    axes={k:i for i,k in enumerate(cache['coupling_axes'])}
    # Compute physical scores exactly, but only validate the single best
    # omitted candidate per class. Unvalidated scores are not counted as
    # independently valid negative columns.
    candidates=[]
    for start,site in ledger['stay_pools'][key].keys():
        option=Option(start,site,((site,start,start+job.service_slots),))
        price,_=physical_price(option,job,data[4][uid],data[0],axes,coupling_pi,count,potential)
        if price < -epsilon:candidates.append((price,site,start,repr(option),option))
    for option in migration_witnesses(cache,oracle_point,job,domain):
        identity=(option.start,option.initial_site,option.checkpoint,option.physical_checkpoint_seconds,option.destination,option.transfer_start)
        if identity in ledger['migration_pools'][key].active_keys:continue
        price,_=physical_price(option,job,data[4][uid],data[0],axes,coupling_pi,count,potential)
        if price < -epsilon:candidates.append((price,option.initial_site,option.start,repr(option),option))
    budget.remaining()
    if not candidates:return None
    option=min(candidates) [-1]
    return validate(cache,job,data[2][uid],data[3],domain,data[4][uid],data[0],axes,coupling_pi,count,potential,option,key)

def expanded_graph(active, option, job, domain, retained):
    added=_graph(job,() if option.migrated else ((option.start,option.initial_site),),
        (option,) if option.migrated else (),domain,True)
    # Union preserves every previous native primitive and physical candidate.
    from v42_compact.graph import Graph
    events={n:tuple(sorted(set(active.events[n])|set(added.events[n]))) for n in active.events}
    states={n:tuple(sorted(set(active.states[n])|set(added.states[n]))) for n in active.states}
    compatible={k:tuple(sorted(set(active.compatible.get(k,()))|set(added.compatible.get(k,())))) for k in set(active.compatible)|set(added.compatible)}
    graph=Graph(events,states,compatible,dict(active.physical,**{})|added.physical,active.transfers|added.transfers,None)
    graph.sha=graph_content_hash(graph)
    return graph
