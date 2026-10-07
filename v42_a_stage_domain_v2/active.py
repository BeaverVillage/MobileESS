"""Small deterministic matrices over the unchanged complete physical universe.

Reference distance and frozen grid scores rank initial activation only. Neither
removes a scientific option. Pools hold indices and reconstruct Option objects
and inherited coefficients on demand; they instantiate no native variables.
"""
from bisect import bisect_left
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
import math

from v42_boundary.generator import Domain, Generator
from v42_compact.graph import Graph
from v42_job_capability import Option, validate
from . import AUTHORITY
from .domain import (contains, digest, graph_content_hash, noflex_anchor,
                     physical_domain, physical_starts, verify_nesting)


def cache_noop_check():
    """Canonical picklable callback; it supplies no physical condition."""
    pass


@dataclass(frozen=True)
class ActivePolicy:
    same_site_radius: int = 2
    extra_stay_per_class: int = 8
    migration_extra_seeds: int = 0

    def require(self):
        if (type(self.same_site_radius) is not int or self.same_site_radius < 0
                or type(self.extra_stay_per_class) is not int or self.extra_stay_per_class < 0
                or self.migration_extra_seeds != 0):
            raise ValueError("PREREGISTERED_FINITE_ACTIVE_POLICY_REQUIRED")
        return self


@dataclass(frozen=True)
class SupportEvidence:
    name: str
    source_sha256: str
    class_options: dict
    independent_replay_valid: bool
    current_incumbent: bool = False

    def require(self):
        if (not self.name or not self.independent_replay_valid
                or len(self.source_sha256) != 64
                or any(char not in "0123456789abcdef" for char in self.source_sha256)):
            raise ValueError("INDEPENDENTLY_VALIDATED_SUPPORT_EVIDENCE_REQUIRED")
        return self


def option_from_json(value):
    fields = dict(value)
    fields["segments"] = tuple(tuple(part) for part in fields["segments"])
    fields["wan"] = tuple(tuple(part) for part in fields.get("wan", ()))
    return Option(**fields)


def support_from_membership_receipt(payload, source_sha256, name="VALIDATED_RESCUE"):
    if payload.get("PASS") is not True:
        raise ValueError("VALIDATED_RESCUE_RECEIPT_REQUIRED")
    selected = defaultdict(set)
    for group in payload["groups"].values():
        if group.get("PASS") is not True:
            raise ValueError("VALIDATED_RESCUE_GROUP_REQUIRED")
        for row in group["records"]:
            if row.get("PASS") is not True or row["checks"].get("full_attribute_membership") is not True:
                raise ValueError("VALIDATED_RESCUE_FULL_ATTRIBUTES_REQUIRED")
            attributes = row["scientific_attributes"]
            selected[attributes["class_id"]].add(option_from_json(attributes["option"]))
    return SupportEvidence(name, source_sha256,
                           {key: tuple(sorted(value)) for key, value in selected.items()}, True).require()


def support_from_verified_schedule(payload, classes, source_sha256, name="CURRENT_VALID_INCUMBENT"):
    physical = payload.get("independent_physical", {})
    if physical.get("PASS") is not True or physical.get("all_original_rows", {}).get("PASS") is not True:
        raise ValueError("INDEPENDENT_PHYSICAL_AND_ORIGINAL_ROW_REPLAY_REQUIRED")
    lookup = {uid: key for key, members in classes.items() for uid in members}
    if set(payload["selected_jobs"]) != set(lookup):
        raise ValueError("INCUMBENT_EXACT_CLASS_POPULATION_REQUIRED")
    selected = defaultdict(set)
    for uid, value in payload["selected_jobs"].items():
        selected[lookup[uid]].add(option_from_json(value))
    return SupportEvidence(name, source_sha256,
                           {key: tuple(sorted(value)) for key, value in selected.items()}, True, True).require()


def grid_priority_hash(scores):
    values = []
    for (site, slot), score in sorted(scores.items()):
        if not isinstance(site, str) or type(slot) is not int or not math.isfinite(float(score)):
            raise ValueError("FINITE_FROZEN_GRID_PRIORITY_AXIS_REQUIRED")
        values.append((site, slot, float(score)))
    return digest(values)


def indexed_contains(job, bound, resources, domain, option):
    """The same full-attribute membership over canonical sorted V2 indices."""
    try:
        validate(job, option, replace(bound, allowed_starts=physical_starts(job, bound)), resources)
    except ValueError:
        return False
    if not option.migrated:
        key = (option.start, option.initial_site)
        at = bisect_left(domain.stays, key)
        canonical = Option(option.start,option.initial_site,
                           ((option.initial_site,option.start,option.start+job.service_slots),))
        return at < len(domain.stays) and domain.stays[at] == key and option == canonical
    prefix = (option.start,option.initial_site,option.checkpoint,
              option.physical_checkpoint_seconds,option.destination,job.gpu)
    at = bisect_left(domain.blocks, prefix + ((),))
    if at == len(domain.blocks) or domain.blocks[at][:6] != prefix:
        return False
    taus = domain.blocks[at][-1]; timestamp = bisect_left(taus,option.transfer_start)
    if timestamp == len(taus) or taus[timestamp] != option.transfer_start:
        return False
    transfer = domain.cache.transfer(option.initial_site,option.destination,job.gpu,option.transfer_start)
    remaining = job.service_slots-(option.checkpoint-option.start)
    expected = Option(option.start,option.initial_site,
        ((option.initial_site,option.start,option.checkpoint),
         (option.destination,transfer.restart,transfer.restart+remaining)),
        option.checkpoint,option.physical_checkpoint_seconds,option.destination,
        option.transfer_start,transfer.end,transfer.restart,transfer.wan)
    return option == expected


def _intervals(keys):
    result = defaultdict(list)
    for start, site in sorted(keys, key=lambda value: (value[1], value[0])):
        intervals = result[site]
        if intervals and start == intervals[-1][1] + 1:
            intervals[-1] = (intervals[-1][0], start)
        else:
            intervals.append((start, start))
    return {site: tuple(values) for site, values in sorted(result.items())}


@dataclass(frozen=True)
class StayPool:
    class_id: str
    representative: str
    cardinality: int
    job: object
    physical_domain: object
    active: frozenset
    inactive_intervals: dict
    retained_mixed_flow: bool

    @property
    def physical_count(self):
        return len(self.physical_domain.stays)

    @property
    def inactive_count(self):
        return self.physical_count - len(self.active)

    def keys(self):
        for site, intervals in self.inactive_intervals.items():
            for lo, hi in intervals:
                for start in range(lo, hi + 1):
                    yield start, site

    def option(self, key):
        start, site = key
        if key not in self.physical_domain.stays:
            raise ValueError("HARD_PHYSICAL_STAY_KEY_REQUIRED")
        return Option(start, site, ((site, start, start + self.job.service_slots),))

    def scientific_column(self, key, *, runtime_provider=None, grid_gpu_rows=None):
        """Physical integer-path effect; mixed-flow LP closure is not implied."""
        from .stay_projection import incidence
        option = self.option(key)
        spec = incidence(self.job, ((option.initial_site, option.start),), self.cardinality, self.class_id)
        return spec.scientific_column((option.initial_site, option.start),
            runtime_provider=runtime_provider, grid_gpu_rows=grid_gpu_rows)

    def receipt(self):
        return dict(class_id=self.class_id, representative=self.representative,
                    exact_class_cardinality=self.cardinality, physical=self.physical_count,
                    active=len(self.active), inactive=self.inactive_count,
                    inactive_start_intervals_by_site=self.inactive_intervals,
                    active_support_sha256=digest(sorted(self.active)),
                    physical_support_sha256=digest(self.physical_domain.stays),
                    retained_original_singleton_mixed_flow=self.retained_mixed_flow,
                    inactive_native_variables=0,
                    path_effect_is_native_mixed_LP_column_asserted=False)


@dataclass(frozen=True)
class MigrationPool:
    class_id: str
    physical_domain: object
    active_keys: frozenset

    @property
    def physical_count(self):
        return self.physical_domain.count - len(self.physical_domain.stays)

    @property
    def inactive_count(self):
        return self.physical_count - len(self.active_keys)

    def receipt(self):
        return dict(class_id=self.class_id, physical=self.physical_count,
                    active=len(self.active_keys), inactive=self.inactive_count,
                    physical_compact_blocks=len(self.physical_domain.blocks),
                    representation="UNCHANGED_COMPACT_PHYSICAL_BLOCKS_MINUS_SMALL_ACTIVE_KEY_SET",
                    active_key_sha256=digest(sorted(self.active_keys)), inactive_native_variables=0)

    def blocks_with_active_timestamps(self):
        """Reuse physical blocks; do not copy their millions of inactive times."""
        excluded = defaultdict(set)
        for start,source,cp,physical,dest,tau in self.active_keys:
            excluded[start,source,cp,physical,dest].add(tau)
        for block in self.physical_domain.blocks:
            yield block, frozenset(excluded.get(block[:5], ()))


def _graph(job, stays, migration, domain, retained_flow):
    events = {name: set() for name in ("y", "q", "w", "f0", "f1")}
    states = {name: set() for name in ("r0", "h", "r1")}
    compatible = defaultdict(set); physical = {}; transfers = {}
    for start, site in stays:
        events["y"].add((site, start)); events["f0"].add((site, start + job.service_slots))
        states["r0"].update((site, slot) for slot in range(start, start + job.service_slots))
    for option in migration:
        source, start, cp, dest, tau = (option.initial_site, option.start, option.checkpoint,
                                       option.destination, option.transfer_start)
        events["y"].add((source, start)); events["q"].add((source, cp)); events["w"].add((source, dest, tau))
        events["f1"].add((dest, option.segments[-1][2]))
        states["r0"].update((source, slot) for slot in range(start, cp))
        states["h"].update((source, slot) for slot in range(cp, tau))
        states["r1"].update((dest, slot) for slot in range(option.restart_end, option.segments[-1][2]))
        compatible[source, cp].add(start)
        physical[source, cp, start] = option.physical_checkpoint_seconds
        transfers[source, dest, tau] = domain.cache.transfer(source, dest, job.gpu, tau)
    fixed = None
    if not retained_flow and len(events["y"]) == 1 and not migration:
        site, start = next(iter(events["y"]))
        fixed = Option(start, site, ((site, start, start + job.service_slots),))
    graph = Graph({key: tuple(sorted(value)) for key, value in events.items()},
                  {key: tuple(sorted(value)) for key, value in states.items()},
                  {key: tuple(sorted(value)) for key, value in compatible.items()}, physical, transfers, fixed)
    graph.sha = graph_content_hash(graph)
    return graph


def represented_migration_keys(graph, domain):
    """Exact graph recombination census without traversing every physical path."""
    events = {name: set(value) for name, value in graph.events.items()}
    states = {name: set(value) for name, value in graph.states.items()}
    by_pair = defaultdict(list)
    for source, dest, tau in events["w"]:
        by_pair[source, dest].append(tau)
    if not by_pair:
        return frozenset()
    result = set()
    for start, source, cp, physical, dest, gpu, taus in domain.blocks:
        candidates = by_pair.get((source, dest), ())
        if (not candidates or (source, start) not in events["y"] or (source, cp) not in events["q"]
                or start not in graph.compatible.get((source, cp), ())
                or graph.physical.get((source, cp, start)) != physical
                or not all((source, slot) in states["r0"] for slot in range(start, cp))):
            continue
        for tau in candidates:
            at = bisect_left(taus, tau)
            if at == len(taus) or taus[at] != tau:
                continue
            transfer = graph.transfers[source, dest, tau]
            end = transfer.restart + domain.duration - (cp - start)
            if ((dest, end) in events["f1"]
                    and all((source, slot) in states["h"] for slot in range(cp, tau))
                    and all((dest, slot) in states["r1"] for slot in range(transfer.restart, end))):
                result.add((start, source, cp, physical, dest, tau))
    return frozenset(result)


def _ledger(data, domains, selection_records):
    _, jobs, _, _, _, graphs, _, prep = data
    stays, migrations = {}, {}
    retained = set(prep["preserve_singleton_mixed_flow"])
    rows = []
    for key, members in sorted(prep["classes"].items()):
        uid = members[0]; graph = graphs[uid]; domain = domains[uid]; job = jobs[uid]
        physical_stay = set(domain.stays); finishes = set(graph.events["f0"])
        support = frozenset((start, site) for site, start in graph.events["y"]
                            if (start, site) in physical_stay
                            and (site, start + job.service_slots) in finishes)
        pool = StayPool(key, uid, len(members), job, domain, support,
                        _intervals(physical_stay - support), uid in retained)
        migration = MigrationPool(key, domain, represented_migration_keys(graph, domain))
        stays[key] = pool; migrations[key] = migration
        rows.append(dict(pool.receipt(), migration=migration.receipt(), selection=selection_records.get(key, {})))
    receipt = dict(PASS=True, authority=AUTHORITY, hard_physical_domain_defined=True,
        active_subset_physical=True, active_union_pool_equals_physical=True,
        physical_STAY=sum(pool.physical_count for pool in stays.values()),
        active_STAY=sum(len(pool.active) for pool in stays.values()),
        inactive_STAY=sum(pool.inactive_count for pool in stays.values()),
        physical_migration=sum(pool.physical_count for pool in migrations.values()),
        active_migration=sum(len(pool.active_keys) for pool in migrations.values()),
        inactive_migration=sum(pool.inactive_count for pool in migrations.values()),
        active_migration_is_actual_graph_recombination_count=True,
        inactive_native_variables=0, exact_class_cardinality_preserved=True,
        scientific_candidates_permanently_removed=0, reference_is_hard_cutoff=False,
        low_grid_priority_scientifically_removed=False, LP_pricing_closed=False,
        integer_domain_closure_proven=False, classes=rows)
    return dict(stay_pools=stays, migration_pools=migrations, receipt=receipt,
                selection_records=selection_records)


def prepare_fast_active(data, *, policy=ActivePolicy(), required_support=(), grid_scores=None,
                        expected_grid_priority_hash=None, physical_domains=None):
    """Initial engineering seed; complete scientific domains remain unchanged."""
    policy.require()
    bundle, jobs, bounds, resources, raw, old_graphs, old, prep = data
    classes = prep["classes"]
    if sorted(uid for members in classes.values() for uid in members) != sorted(jobs):
        raise ValueError("CLASS_EXACT_CARDINALITY_MEMBERSHIP")
    scores = {} if grid_scores is None else dict(grid_scores)
    score_hash = grid_priority_hash(scores)
    if scores and expected_grid_priority_hash != score_hash:
        raise ValueError("PREREGISTERED_GRID_PRIORITY_HASH_REQUIRED")
    horizon = max(bound.latest_completion for bound in bounds.values())
    score_prefix = {}
    for site in resources.capacities:
        prefix = [0.]
        for slot in range(horizon):
            prefix.append(prefix[-1] + scores.get((site, slot), 0.))
        score_prefix[site] = prefix
    supports = tuple(evidence.require() for evidence in required_support)
    if any(key not in classes for evidence in supports for key in evidence.class_options):
        raise ValueError("UNKNOWN_REQUIRED_SUPPORT_CLASS")
    generator = None if physical_domains is not None else Generator(resources, max(b.latest_completion for b in bounds.values()))
    domains, new_bounds, graphs, records, retained_flow = {}, {}, {}, {}, []
    for key, members in sorted(classes.items()):
        uid = members[0]; job = jobs[uid]; bound = bounds[uid]; original = old_graphs[uid]
        for member in members:
            if (replace(job, uid=member) != jobs[member] or bound != bounds[member]
                    or original.sha != old_graphs[member].sha):
                raise ValueError("CLASS_PHYSICAL_OPTION_UNIFORMITY")
        domain = physical_domains[uid] if physical_domains is not None else physical_domain(job, bound, resources, generator)
        if domain.cache.r != resources or domain.duration != job.service_slots:
            raise ValueError("COMPLETE_PHYSICAL_DOMAIN_RESOURCE_IDENTITY")
        wide = replace(bound, allowed_starts=physical_starts(job, bound, resources.control_end))
        physical_stay = set(domain.stays)
        mandatory = {(start, site) for site, start in original.events["y"] if (start, site) in physical_stay}
        historical_count = len(mandatory)
        anchor = noflex_anchor(job, bound, resources)
        if anchor is not None:
            if (anchor.start, anchor.initial_site) not in physical_stay:
                raise ValueError("NOFLEX_ANCHOR_NOT_PHYSICAL")
            mandatory.add((anchor.start, anchor.initial_site))
        migration = set(); included = {}; invalid = []
        for evidence in supports:
            accepted = 0
            for option in evidence.class_options.get(key, ()):
                if not indexed_contains(job, bound, resources, domain, option):
                    if evidence.current_incumbent:
                        raise ValueError("CURRENT_REPLAY_VALID_INCUMBENT_OUTSIDE_PHYSICAL_DOMAIN")
                    invalid.append(dict(source=evidence.name, option=asdict(option), reason="HARD_PHYSICAL_MEMBERSHIP"))
                    continue
                accepted += 1
                if option.migrated:
                    migration.add(option)
                else:
                    mandatory.add((option.start, option.initial_site))
            included[evidence.name] = accepted
        # Native class histograms also use any hard-valid STAY beginning at a
        # migration seed's source/start; include and report those induced axes.
        induced = {(option.start, option.initial_site) for option in migration} & physical_stay
        mandatory.update(induced)
        local = {(start, job.reference_site) for start in range(job.reference_start-policy.same_site_radius,
                     job.reference_start+policy.same_site_radius+1)} & physical_stay
        active = mandatory | local
        def rank(candidate):
            start, site = candidate
            prefix = score_prefix[site]
            benefit = job.gpu * (prefix[start + job.service_slots] - prefix[start])
            return (-benefit, abs(start-job.reference_start), int(site != job.reference_site), start, site)
        extras = sorted(physical_stay-active, key=rank)[:policy.extra_stay_per_class]
        active.update(extras)
        retain = len(members) == 1 and bool(original.events["w"])
        if retain:
            retained_flow.append(uid)
        graph = _graph(job, active, tuple(sorted(migration)), domain, retain)
        records[key] = dict(historical_hard_valid_STAY=historical_count,
            valid_anchor_included=anchor is not None, uncapped_mandatory_STAY=len(mandatory),
            required_sources=included, invalid_historical_support=invalid,
            migration_explicit_seed_options=len(migration), induced_STAY_from_migration_sources=len(induced),
            local_STAY_added=len(local-mandatory), grid_ranked_extra_STAY=len(extras),
            engineering_extra_cap=policy.extra_stay_per_class, no_scientific_cutoff=True)
        for member in members:
            domains[member] = domain; new_bounds[member] = wide; graphs[member] = graph
    nesting = verify_nesting(jobs, bounds, resources, domains)
    if not nesting["PASS"]:
        raise ValueError("A_NOFLEX_NOT_NESTED")
    metadata = dict(prep, domain_authority=AUTHORITY, fast_active_domain=True,
        preserve_singleton_mixed_flow=tuple(sorted(retained_flow)),
        active_policy=asdict(policy), active_policy_sha256=digest(asdict(policy)),
        grid_priority_sha256=score_hash, frozen_grid_priority_available=bool(scores),
        required_support_sources=[dict(name=e.name,sha256=e.source_sha256,current_incumbent=e.current_incumbent) for e in supports],
        full_migration_domain_active=False, complete_stay_active=False,
        class_exact_cardinality_preserved=True, scientific_classes_unchanged=True,
        stay_active_policy="MANDATORY_SUPPORT_PLUS_PREREGISTERED_SMALL_ENGINEERING_SEED; COMPLETE_POOL",
        noflex_nesting=nesting, physical_domain_hash=digest({uid:domain.sha for uid,domain in sorted(domains.items())}))
    active_data = (dict(bundle, aidc_domain_authority=AUTHORITY), jobs, new_bounds, resources, raw, graphs, old, metadata)
    ledger = _ledger(active_data, domains, records)
    metadata.update(active_STAY=ledger["receipt"]["active_STAY"], inactive_STAY=ledger["receipt"]["inactive_STAY"],
                    active_migration=ledger["receipt"]["active_migration"], inactive_migration=ledger["receipt"]["inactive_migration"],
                    complete_stay_active=ledger["receipt"]["inactive_STAY"] == 0)
    return active_data, domains, ledger


def activate_fast(active_data, physical_domains, ledger, selections):
    """Exact monotone finite restoration in the retained native representation."""
    from .domain import activate_migration, activate_stay
    stay, migration = {}, {}
    for key, options in sorted(selections.items()):
        if key not in active_data[7]["classes"]:
            raise ValueError("UNKNOWN_SCIENTIFIC_CLASS")
        uid = active_data[7]["classes"][key][0]; job = active_data[1][uid]
        for option in sorted(set(options)):
            if not indexed_contains(job, active_data[2][uid], active_data[3], physical_domains[uid], option):
                raise ValueError("HARD_PHYSICAL_ACTIVATION_MEMBERSHIP_REQUIRED")
            target = migration if option.migrated else stay
            target.setdefault(key, []).append(option)
            if option.migrated and (option.start, option.initial_site) in set(physical_domains[uid].stays):
                stay.setdefault(key, []).append(Option(option.start,option.initial_site,
                    ((option.initial_site,option.start,option.start+job.service_slots),)))
    updated = activate_stay(active_data, physical_domains, stay)
    updated = activate_migration(updated, physical_domains, migration)
    fresh = _ledger(updated, physical_domains, ledger["selection_records"])
    for key, old_pool in ledger["stay_pools"].items():
        if not old_pool.active <= fresh["stay_pools"][key].active:
            raise ValueError("NONMONOTONE_ACTIVE_STAY_DOMAIN")
        if not ledger["migration_pools"][key].active_keys <= fresh["migration_pools"][key].active_keys:
            raise ValueError("NONMONOTONE_ACTIVE_MIGRATION_DOMAIN")
    updated[7].update(active_STAY=fresh["receipt"]["active_STAY"], inactive_STAY=fresh["receipt"]["inactive_STAY"],
                     active_migration=fresh["receipt"]["active_migration"], inactive_migration=fresh["receipt"]["inactive_migration"])
    return updated, fresh
