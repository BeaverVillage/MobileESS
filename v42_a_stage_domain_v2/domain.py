"""Complete physical STAY support and lossless matrix-free migration blocks.

Reference starts are objective metadata. No price, probability, or distance
participates in physical membership. Coupled schedulability is not inferred
from the locally hard-valid domain.
"""
from collections import defaultdict
from dataclasses import asdict, replace
import hashlib
import json
import numpy as np
from v42_job_capability import Option, validate, checkpoint_records
from v42_boundary.generator import Generator, Domain
from . import AUTHORITY


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     default=str, allow_nan=False).encode()).hexdigest()


def graph_content_hash(graph):
    """Domain identity is independent of activation order and repetitions."""
    return digest(dict(authority=AUTHORITY,events=graph.events,states=graph.states,
        compatible=sorted(graph.compatible.items()),physical=sorted(graph.physical.items()),
        transfers=[(k,asdict(v)) for k,v in sorted(graph.transfers.items())],
        fixed=asdict(graph.fixed) if graph.fixed else None))


def support_metadata(prep,graphs,physical_domains):
    counts={}
    for class_id,members in prep['classes'].items():
        uid=members[0];domain=physical_domains[uid];graph=graphs[uid]
        duration=domain.duration
        available=set(domain.stays)
        active={(s,k) for k,s in graph.events['y'] if (k,s+duration) in graph.events['f0']
                and all((k,t) in graph.states['r0'] for t in range(s,s+duration))} & available
        counts[class_id]=dict(physical=len(available),active=len(active),lazy=len(available)-len(active))
    return dict(active_stay_support=counts,complete_stay_active=all(v['lazy']==0 for v in counts.values()))


def flexible(job):
    return (job.admitted and job.state == 'PENDING' and not job.protected
            and job.qos not in ('high', 'urgent') and not job.unknown_arrival)


def physical_starts(job, bound, control_end=120, hard_release=None):
    """Unchanged completion ceiling, including authorized representation tail.

    control_end constrains checkpoint/transfer/restart, not STAY completion or
    the reference tail. hard_release may only be an independently issued hard
    temporal release; neither R0 nor the old allowed-start lower endpoint is
    such a release. Nonflexible timing retains the frozen reference choice.
    """
    bound.require()
    if hard_release is not None and type(hard_release) is not int:
        raise ValueError('HARD_RELEASE_INTEGER_REQUIRED')
    lo = max(job.submit, job.event, hard_release if hard_release is not None else 0)
    hi = bound.latest_completion - job.service_slots
    if not flexible(job):
        return (job.reference_start,) if lo <= job.reference_start <= hi else ()
    return tuple(range(lo, hi + 1))


def physical_domain(job, bound, resources, gen=None, hard_release=None):
    """One block per (start, source, physical checkpoint, destination).

    A block stores every feasible transfer timestamp. It never identifies
    distinct timestamps as duplicate scientific columns. Options/WAN payloads
    are reconstructed on demand from the unchanged Resources authority.
    """
    starts = physical_starts(job, bound, resources.control_end, hard_release)
    if not job.admitted:
        raise ValueError('UNADMITTED_REQUIRES_SEPARATE_BACKLOG_LEDGER')
    gen = gen or Generator(resources, bound.latest_completion)
    if gen.r != resources:
        raise ValueError('PHYSICAL_RESOURCE_IDENTITY')
    if resources.restart_slots < 1 or resources.bytes_per_gpu <= 0:
        raise ValueError('MIGRATION_COST_AUTHORITY_REQUIRED')
    if not starts:
        return Domain((), (), gen, job.service_slots)
    wide = replace(bound, allowed_starts=starts)
    initial, dests = gen.static_sites(job)
    stays, blocks = [], []
    for start in starts:
        for site in initial:
            if gen.fits(site, start, job.service_slots, job.gpu):
                option = Option(start, site, ((site, start, start + job.service_slots),))
                validate(job, option, wide, resources)
                stays.append((start, site))
            if not job.checkpoint_authorized or job.unknown_arrival or job.migrations_used:
                continue
            for cp, physical in checkpoint_records(job, start, min(start + job.service_slots, resources.control_end)):
                remaining = job.service_slots - (cp - start)
                if remaining <= 0 or not gen.fits(site, start, cp - start, job.gpu):
                    continue
                for dest in dests:
                    if dest == site:
                        continue
                    latest = min(resources.control_end - resources.restart_slots - 2,
                                 bound.latest_completion - remaining - resources.restart_slots - 1)
                    if cp > latest:
                        continue
                    ids = np.arange(cp, latest + 1, dtype=int)
                    feasible, restarts = gen.transfer_series(site, dest, job.gpu)
                    good = feasible[ids] & (restarts[ids] + remaining <= bound.latest_completion)
                    good &= gen.mask(remaining, job.gpu, dest)[np.minimum(restarts[ids], gen.max_slot)]
                    taus = tuple(int(t) for t in ids[good])
                    if taus:
                        # Validate a representative for adapter identity. All
                        # timestamps have individually passed the exact masks.
                        tr = gen.transfer(site, dest, job.gpu, taus[0])
                        option = Option(start, site, ((site, start, cp), (dest, tr.restart, tr.restart + remaining)),
                                        cp, physical, dest, taus[0], tr.end, tr.restart, tr.wan)
                        validate(job, option, wide, resources)
                        blocks.append((start, site, cp, physical, dest, job.gpu, taus))
    domain = Domain(tuple(sorted(set(stays))), tuple(sorted(set(blocks))), gen, job.service_slots)
    domain.sha = digest(dict(authority=AUTHORITY, resources=gen.identity,
                             job={k:v for k,v in asdict(job).items() if k != 'uid'},
                             completion=bound.latest_completion, stays=domain.stays, blocks=domain.blocks))
    return domain


def noflex_anchor(job, bound, resources):
    """A_NOFLEX uses the same population, quantities, and physical authority."""
    option = Option(job.reference_start, job.reference_site,
                    ((job.reference_site, job.reference_start, job.reference_start + job.service_slots),))
    # Independent of the flexible support generator: historical R0 metadata
    # supplies this one choice, and the common hard validator decides validity.
    if not max(job.submit, job.event) <= option.start <= bound.latest_completion - job.service_slots:
        return None
    try:
        validate(job, option, replace(bound, allowed_starts=(option.start,)), resources)
    except ValueError:
        return None
    return option


def verify_nesting(jobs, bounds, resources, domains):
    """Independent anchor validation and physical support inclusion; no solve."""
    records = []
    for uid, job in sorted(jobs.items()):
        anchor = noflex_anchor(job, bounds[uid], resources)
        included = anchor is None or (anchor.start, anchor.initial_site) in domains[uid].stays
        records.append(dict(uid=uid, valid_noflex_anchor=anchor is not None, included=included))
    return dict(PASS=all(r['included'] for r in records), authority=AUTHORITY,
                implication='Every feasible A_NOFLEX assignment has identical scientific coefficients in A_FLEX',
                global_noflex_feasibility_claimed=False, records=records)


def contains(job, bound, resources, domain, option):
    """Membership checks complete option attributes, including deterministic WAN."""
    try:
        validate(job, option, replace(bound, allowed_starts=physical_starts(job, bound)), resources)
    except ValueError:
        return False
    if not option.migrated:
        canonical = Option(option.start, option.initial_site,
                           ((option.initial_site,option.start,option.start+job.service_slots),))
        return option == canonical and (option.start, option.initial_site) in domain.stays
    for start, source, cp, physical, dest, gpu, taus in domain.blocks:
        if (start, source, cp, physical, dest) != (option.start, option.initial_site, option.checkpoint,
                                                option.physical_checkpoint_seconds, option.destination):
            continue
        if option.transfer_start not in taus:
            return False
        tr = domain.cache.transfer(source, dest, gpu, option.transfer_start)
        remaining = job.service_slots - (cp - start)
        expected = Option(start, source, ((source, start, cp), (dest, tr.restart, tr.restart + remaining)),
                          cp, physical, dest, option.transfer_start, tr.end, tr.restart, tr.wan)
        return option == expected
    return False


def augment_stay_graph(job, bound, graph, domain):
    """Retain inherited migration representation; add full hard-valid STAY.

    The singleton mixed flow LP is deliberately retained. Replacing it by a
    histogram changes its LP projection, as the independent study demonstrates.
    """
    from v42_compact.graph import Graph
    events = {n:set(v) for n,v in graph.events.items()}
    states = {n:set(v) for n,v in graph.states.items()}
    for start, site in domain.stays:
        events['y'].add((site, start))
        events['f0'].add((site, start + job.service_slots))
        states['r0'].update((site, t) for t in range(start, start + job.service_slots))
    result = Graph({n:tuple(sorted(v)) for n,v in events.items()},
                   {n:tuple(sorted(v)) for n,v in states.items()},
                   dict(graph.compatible), dict(graph.physical), dict(graph.transfers), None)
    if len(events['y']) == 1 and not events['q'] and not events['w']:
        site, start = next(iter(events['y']))
        if (start, site) in domain.stays:
            result.fixed = Option(start, site, ((site, start, start + job.service_slots),))
    result.sha = graph_content_hash(result)
    return result


def active_stay_domain(job, bound, resources, graph, domain, cardinality):
    """Complete active support only where histogram LP projection is proven.

    Singleton mixed-flow new STAY choices remain losslessly lazy. The active
    graph keeps S0 and every physically valid no-action anchor by construction.
    """
    if cardinality > 1 or not graph.events['w']:
        return domain
    support = {(s,k) for k,s in graph.events['y'] if (s,k) in domain.stays}
    anchor = noflex_anchor(job,bound,resources)
    if anchor is not None:
        support.add((anchor.start,anchor.initial_site))
    return Domain(tuple(sorted(support)), (), domain.cache, job.service_slots)


def prepare_active(data, *, complete_stay=False):
    """Build-free adapter; full activation retains singleton original flow LP.

    The qualification expansion adds every hard-valid STAY path to the same
    original singleton flow representation. It never substitutes an unproved
    histogram projection for that representation.
    """
    bundle, jobs, bounds, resources, raw, graphs, old, prep = data
    gen = Generator(resources, max(b.latest_completion for b in bounds.values()))
    domains, new_bounds, new_graphs, active_stay_support = {}, {}, {}, {}
    classes = prep['classes']
    if sorted(u for us in classes.values() for u in us) != sorted(jobs):
        raise ValueError('CLASS_EXACT_CARDINALITY_MEMBERSHIP')
    for key, members in sorted(classes.items()):
        uid = members[0]; job = jobs[uid]; bound = bounds[uid]
        for member in members:
            if replace(job, uid=member) != jobs[member] or bound != bounds[member] or graphs[uid].sha != graphs[member].sha:
                raise ValueError('CLASS_PHYSICAL_OPTION_UNIFORMITY')
        domain = physical_domain(job, bound, resources, gen)
        wide = replace(bound, allowed_starts=physical_starts(job, bound, resources.control_end))
        active = domain if complete_stay else active_stay_domain(job,wide,resources,graphs[uid],domain,len(members))
        graph = augment_stay_graph(job, wide, graphs[uid], active)
        active_stay_support[key] = dict(physical=len(domain.stays),active=len(active.stays),
                                       lazy=len(domain.stays)-len(active.stays))
        for member in members:
            domains[member] = domain; new_bounds[member] = wide; new_graphs[member] = graph
    nesting = verify_nesting(jobs, bounds, resources, domains)
    if not nesting['PASS']:
        raise ValueError('A_NOFLEX_NOT_NESTED')
    metadata = dict(prep, domain_authority=AUTHORITY,
                    complete_stay_active=all(v['lazy']==0 for v in active_stay_support.values()),
                    active_stay_support=active_stay_support,
                    stay_active_policy=('COMPLETE_PROVEN_HISTOGRAM; COMPLETE_ORIGINAL_SINGLETON_FLOW'
                        if complete_stay else 'COMPLETE_PROVEN_HISTOGRAM; SINGLETON_MIXED_FLOW_S0_PLUS_ANCHOR_WITH_LAZY_STAY'),
                    full_migration_domain_active=False, class_exact_cardinality_preserved=True,
                    scientific_classes_unchanged=True, noflex_nesting=nesting,
                    physical_domain_hash=digest({u:d.sha for u,d in sorted(domains.items())}))
    return (dict(bundle, aidc_domain_authority=AUTHORITY), jobs, new_bounds, resources,
            raw, new_graphs, old, metadata), domains


def activate_stay(active_data, physical_domains, selections):
    """Restore hard-valid fallback STAY choices with existing event-flow rows."""
    bundle,jobs,bounds,resources,raw,graphs,old,prep = active_data
    result = dict(graphs)
    activated = []
    for class_id, options in sorted(selections.items()):
        if class_id not in prep['classes']:
            raise ValueError('UNKNOWN_SCIENTIFIC_CLASS')
        members=prep['classes'][class_id];uid=members[0];job=jobs[uid]
        support=[]
        for option in sorted(set(options)):
            if option.migrated or not contains(job,bounds[uid],resources,physical_domains[uid],option):
                raise ValueError('HARD_PHYSICAL_STAY_MEMBERSHIP_REQUIRED')
            for member in members:
                validate(jobs[member],option,bounds[member],resources)
            support.append((option.start,option.initial_site))
            activated.append(dict(class_id=class_id,option=asdict(option)))
        lazy_subset=Domain(tuple(support),(),physical_domains[uid].cache,job.service_slots)
        expanded=augment_stay_graph(job,bounds[uid],result[uid],lazy_subset)
        for member in members:
            result[member]=expanded
    return (bundle,jobs,bounds,resources,raw,result,old,
            dict(prep,activated_stay_options=prep.get('activated_stay_options',[])+activated,
                 **support_metadata(prep,result,physical_domains)))


def activate_migration(active_data, physical_domains, selections):
    """Admit explicitly selected hard-valid lazy options without heuristic cuts.

    selections maps a scientific class ID to complete Option values. Physical
    membership is necessary; pricing priority does not authorize new physics.
    """
    from v42_compact.graph import Graph
    bundle,jobs,bounds,resources,raw,graphs,old,prep = active_data
    result = dict(graphs)
    activated = []
    for class_id, options in sorted(selections.items()):
        if class_id not in prep['classes']:
            raise ValueError('UNKNOWN_SCIENTIFIC_CLASS')
        members = prep['classes'][class_id]; uid = members[0]; job = jobs[uid]
        graph = result[uid]
        events = {n:set(v) for n,v in graph.events.items()}
        states = {n:set(v) for n,v in graph.states.items()}
        compat = {k:set(v) for k,v in graph.compatible.items()}
        physical, transfers = dict(graph.physical), dict(graph.transfers)
        for option in sorted(set(options)):
            if not option.migrated or not contains(job,bounds[uid],resources,physical_domains[uid],option):
                raise ValueError('HARD_PHYSICAL_MIGRATION_MEMBERSHIP_REQUIRED')
            for member in members:
                validate(jobs[member], option, bounds[member], resources)
            site,start,cp,dest,tau = option.initial_site,option.start,option.checkpoint,option.destination,option.transfer_start
            events['y'].add((site,start));events['q'].add((site,cp));events['w'].add((site,dest,tau))
            events['f1'].add((dest,option.segments[-1][2]))
            states['r0'].update((site,t) for t in range(start,cp))
            states['h'].update((site,t) for t in range(cp,tau))
            states['r1'].update((dest,t) for t in range(option.restart_end,option.segments[-1][2]))
            compat.setdefault((site,cp),set()).add(start)
            physical[site,cp,start] = option.physical_checkpoint_seconds
            transfers[site,dest,tau] = physical_domains[uid].cache.transfer(site,dest,job.gpu,tau)
            activated.append(dict(class_id=class_id,option=asdict(option)))
        expanded = Graph({n:tuple(sorted(v)) for n,v in events.items()},
                         {n:tuple(sorted(v)) for n,v in states.items()},
                         {k:tuple(sorted(v)) for k,v in compat.items()}, physical, transfers, None)
        expanded.sha = graph_content_hash(expanded)
        for member in members:
            result[member] = expanded
    return (bundle,jobs,bounds,resources,raw,result,old,
            dict(prep, activated_migration_options=prep.get('activated_migration_options',[]) + activated,
                 full_migration_domain_active=False,**support_metadata(prep,result,physical_domains)))
