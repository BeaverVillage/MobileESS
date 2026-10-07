"""Independent tiny active/pool partition and retained-flow BUILD-only checks."""
from dataclasses import asdict, replace
from fractions import Fraction
from itertools import product

import gurobipy as gp
import numpy as np
import pytest

from v42_job_capability import Job, Option, Resources, ServiceBoundary
from v42_exact.support import ExactFactory
from v42_compact.graph import old_to_compact
from v42_a_stage_domain_v2.active import (ActivePolicy, SupportEvidence, activate_fast,
    grid_priority_hash, prepare_fast_active, represented_migration_keys,
    support_from_verified_schedule, support_from_membership_receipt, indexed_contains)
from v42_a_stage_domain_v2.domain import contains, physical_domain


def fixture(cardinality=1):
    job = Job("j", "PENDING", 0, 0, 4, "A", 4, 2, initial_sites=("A", "B"),
              checkpoint_authorized=True, duration_authority="EXPLICIT_ACTIVE_TINY_FIXTURE")
    bound = ServiceBoundary("TINY", True, True, (4, 5), 12)
    resources = Resources({"A": 8, "B": 8}, {"A": (4,), "B": (4,)},
        {(link, slot): 8 for link in ("AB", "BA") for slot in range(12)},
        {("A", "B"): ("AB",), ("B", "A"): ("BA",)}, 12, 4, {}, {}, {}, max_active_transfers=2)
    graph = ExactFactory(resources, 12).graph(job, bound)
    members = ["j" + str(index) for index in range(cardinality)]
    jobs = {uid: replace(job, uid=uid) for uid in members}
    return ({}, jobs, {uid: bound for uid in members}, resources, {},
            {uid: graph for uid in members}, {}, dict(classes={"c": members}))


def exact_partition(ledger):
    for pool in ledger["stay_pools"].values():
        inactive = set(pool.keys())
        assert not inactive & pool.active
        assert inactive | pool.active == set(pool.physical_domain.stays)
        assert len(inactive) == pool.inactive_count
    receipt = ledger["receipt"]
    assert receipt["active_STAY"] + receipt["inactive_STAY"] == receipt["physical_STAY"]
    assert receipt["active_migration"] + receipt["inactive_migration"] == receipt["physical_migration"]


def test_uncapped_old_support_anchor_small_default_and_exact_pool_partition():
    data = fixture(2)
    active, domains, ledger = prepare_fast_active(data, policy=ActivePolicy(0, 0))
    assert active[7]["class_exact_cardinality_preserved"]
    assert set(active[1]) == set(data[1])
    assert ledger["receipt"]["active_STAY"] == 4
    assert ledger["receipt"]["physical_STAY"] == 18
    assert ledger["receipt"]["active_migration"] == 0
    assert (0, "A") in set(ledger["stay_pools"]["c"].keys())
    assert (4, "A") in ledger["stay_pools"]["c"].active
    assert not active[7]["preserve_singleton_mixed_flow"]
    assert domains["j0"].sha == physical_domain(data[1]["j0"], data[2]["j0"], data[3]).sha
    default, _, default_ledger = prepare_fast_active(data)
    assert 4 < default_ledger["receipt"]["active_STAY"] < 18
    assert default_ledger["receipt"]["classes"][0]["selection"]["engineering_extra_cap"] == 8
    assert not default[7]["frozen_grid_priority_available"]
    exact_partition(ledger); exact_partition(default_ledger)


def test_required_support_bypasses_cap_and_incumbent_cannot_be_silently_discarded():
    data = fixture(2)
    option = Option(0, "B", (("B", 0, 4),))
    evidence = SupportEvidence("CURRENT", "a" * 64, {"c": (option,)}, True, True)
    _, _, ledger = prepare_fast_active(data, policy=ActivePolicy(0, 0), required_support=(evidence,))
    assert option.start < data[1]["j0"].reference_start
    assert (0, "B") in ledger["stay_pools"]["c"].active
    assert ledger["receipt"]["active_STAY"] == 5
    invalid = replace(evidence, class_options={"c": (replace(option, checkpoint=-2),)})
    with pytest.raises(ValueError, match="INCUMBENT_OUTSIDE_PHYSICAL_DOMAIN"):
        prepare_fast_active(data, required_support=(invalid,))
    with pytest.raises(ValueError, match="VALIDATED_SUPPORT_EVIDENCE"):
        prepare_fast_active(data, required_support=(replace(evidence, independent_replay_valid=False),))


def test_frozen_grid_rank_and_hash_are_deterministic_ranking_only():
    data = fixture(2); scores = {("B", 0): 10.}
    kwargs = dict(policy=ActivePolicy(0, 1), grid_scores=scores,
                  expected_grid_priority_hash=grid_priority_hash(scores))
    first, domains, ledger = prepare_fast_active(data, **kwargs)
    second, other_domains, other = prepare_fast_active(data, **kwargs)
    assert (0, "B") in ledger["stay_pools"]["c"].active
    assert ledger["receipt"] == other["receipt"]
    assert first[5]["j0"].sha == second[5]["j0"].sha
    assert domains["j0"].sha == other_domains["j0"].sha
    assert ledger["receipt"]["scientific_candidates_permanently_removed"] == 0
    with pytest.raises(ValueError, match="GRID_PRIORITY_HASH"):
        prepare_fast_active(data, grid_scores=scores)
    with pytest.raises(ValueError, match="FINITE_FROZEN_GRID_PRIORITY"):
        grid_priority_hash({("A", 0): np.nan})


def test_activation_is_monotone_idempotent_and_preserves_full_physical_support():
    data = fixture()
    active, domains, ledger = prepare_fast_active(data, policy=ActivePolicy(0, 0))
    option = Option(0, "A", (("A", 0, 4),))
    expanded, fresh = activate_fast(active, domains, ledger, {"c": (option,)})
    repeated, again = activate_fast(expanded, domains, fresh, {"c": (option,)})
    assert (0, "A") in fresh["stay_pools"]["c"].active
    assert fresh["receipt"] == again["receipt"]
    assert expanded[5]["j0"].sha == repeated[5]["j0"].sha
    assert expanded[7]["preserve_singleton_mixed_flow"] == ("j0",)
    exact_partition(fresh)
    with pytest.raises(ValueError, match="ACTIVATION_MEMBERSHIP"):
        activate_fast(active, domains, ledger, {"c": (replace(option, transfer_start=9),)})


def test_actual_migration_recombination_count_matches_independent_complete_path_replay():
    data = fixture()
    physical = physical_domain(data[1]["j0"], data[2]["j0"], data[3])
    for option in physical:
        assert indexed_contains(data[1]["j0"],data[2]["j0"],data[3],physical,option)
        assert not indexed_contains(data[1]["j0"],data[2]["j0"],data[3],physical,
                                    replace(option,transfer_end=option.transfer_end+1))
    migrations = [option for option in physical if option.migrated]
    # Several seeds share primitives; every additional represented trajectory
    # is counted, rather than claiming active count equals explicit seed count.
    seeds = tuple(migrations[index] for index in (0, 2, 8, 15))
    evidence = SupportEvidence("MIGRATION_RESCUE", "b" * 64, {"c": seeds}, True)
    active, domains, ledger = prepare_fast_active(data, policy=ActivePolicy(0, 0), required_support=(evidence,))
    graph = active[5]["j0"]; expected = set()
    for option in physical:
        if not option.migrated:
            continue
        assignment = old_to_compact(option)
        if (all(set(assignment[name]) <= set(keys) for name, keys in {**graph.events, **graph.states}.items())
                and option.start in graph.compatible.get((option.initial_site, option.checkpoint), ())
                and graph.physical.get((option.initial_site, option.checkpoint, option.start)) == option.physical_checkpoint_seconds):
            expected.add((option.start, option.initial_site, option.checkpoint,
                          option.physical_checkpoint_seconds, option.destination, option.transfer_start))
    actual = represented_migration_keys(graph, domains["j0"])
    assert actual == expected
    assert len(actual) >= len(set(seeds))
    assert ledger["receipt"]["active_migration"] == len(actual)
    assert all(contains(data[1]["j0"], data[2]["j0"], data[3], domains["j0"], option) for option in seeds)
    exact_partition(ledger)


def test_empty_migration_seed_retains_original_singleton_flow_fractional_lp_counterexample():
    from v42_root.factor import add_job
    from v42_a_stage_domain_v2.domain import augment_stay_graph
    from v42_a_stage_domain_v2.lexstage import LinearSnapshot, Objective
    # Reuse the known D3 source-flow counterexample with start1 and mixed finish
    # mass at3/5. It must survive when active M is empty.
    data = fixture(); job = replace(data[1]["j0"], service_slots=3, reference_start=1)
    bound = replace(data[2]["j0"], allowed_starts=(0, 1, 2))
    graph = ExactFactory(data[3], 12).graph(job, bound)
    data = (data[0], {"j0": job}, {"j0": bound}, data[3], {}, {"j0": graph}, {}, data[7])
    evidence = SupportEvidence("ALL_TINY_STARTS", "c" * 64,
        {"c": tuple(Option(start,"A",(("A",start,start+3),)) for start in (0,1,2))}, True)
    active, _, ledger = prepare_fast_active(data, policy=ActivePolicy(0, 0), required_support=(evidence,))
    assert active[7]["preserve_singleton_mixed_flow"] == ("j0",)
    assert not active[5]["j0"].events["w"] and active[5]["j0"].fixed is None
    model = gp.Model("TINY_BUILD_ONLY_ORIGINAL_SOURCE_FLOW"); model.Params.OutputFlag = 0
    try:
        v = add_job(model, job, active[5]["j0"], data[3], eliminate_f0=True,
                    eliminate_state=True, preserve_stay_flow=True)
        model.update()
        assert all(isinstance(value, gp.Var) for value in v["f0"].values())
        assert all(isinstance(value, gp.Var) for value in v["r0"].values())
        values = np.zeros(model.NumVars)
        point = {"y": {("A",1):1}, "f0": {("A",3):.5,("A",5):.5},
                 "r0": {("A",1):1,("A",2):1,("A",3):.5,("A",4):.5}}
        for name, family in point.items():
            for key, value in family.items():
                values[v[name][key].index] = value
        A = model.getA(); rhs = model.getAttr("RHS"); senses = model.getAttr("Sense")
        for row in range(A.shape[0]):
            lo, hi = A.indptr[row:row+2]
            activity = sum(Fraction(float(a))*Fraction(float(values[column]))
                           for column, a in zip(A.indices[lo:hi], A.data[lo:hi]))
            target = Fraction(rhs[row])
            assert activity == target if senses[row] == "=" else activity <= target
        assert ledger["receipt"]["classes"][0]["retained_original_singleton_mixed_flow"]
    finally:
        model.dispose()


def test_validated_support_loaders_require_replay_and_preserve_full_attributes():
    option = Option(0,"A",(("A",0,4),))
    payload = dict(independent_physical=dict(PASS=True,all_original_rows=dict(PASS=True)),
                   selected_jobs={"j0":asdict(option)}, accepted=False)
    evidence = support_from_verified_schedule(payload, {"c":["j0"]}, "d"*64)
    assert evidence.current_incumbent and evidence.class_options["c"] == (option,)
    with pytest.raises(ValueError, match="EXACT_CLASS_POPULATION"):
        support_from_verified_schedule(payload, {"c":["j0","j1"]}, "d"*64)
    payload["independent_physical"]["all_original_rows"]["PASS"] = False
    with pytest.raises(ValueError, match="ORIGINAL_ROW_REPLAY"):
        support_from_verified_schedule(payload, {"c":["j0"]}, "d"*64)
    receipt = dict(PASS=True,groups={"r":dict(PASS=True,records=[dict(PASS=True,
        checks=dict(full_attribute_membership=True), scientific_attributes=dict(class_id="c",option=asdict(option)))])})
    assert support_from_membership_receipt(receipt,"e"*64).class_options["c"] == (option,)


def test_histogram_capacity_cuts_exclude_retained_flow_even_when_active_w_empty():
    from types import SimpleNamespace
    from v42_a_stage_domain_v2.lexstage import LinearSnapshot, Objective
    from v42_a_stage_domain_v2.strengthening import strengthen_histogram_capacity
    import scipy.sparse as sp
    snapshot = LinearSnapshot(sp.csr_matrix([[-2.,1.]]),np.zeros(2),np.array([2.,3.]),
        np.array(["="]),np.array([0.]),np.array(["I","C"]),
        tuple(Objective(name,()) for name in ("rho","migration_count","shift_magnitude","prestart_relocation")))
    descriptor = dict(units=[dict(uid="j",id="j",retained_mixed_flow=True,stay_count=False,
        v=dict(y={("A",0):("v",0)}))],known={("A",0):("v",1)})
    data = ({},{"j":SimpleNamespace(service_slots=1,gpu=2)},{},SimpleNamespace(capacities={"A":3}),
            {},{"j":SimpleNamespace(events={"w":()})},{},{})
    _, receipt = strengthen_histogram_capacity(snapshot,snapshot,descriptor,data,np.arange(2))
    assert receipt["cuts_added"] == 0
