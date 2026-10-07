"""Independent tiny enumeration and lazy-fallback checks; no optimizer calls."""
from dataclasses import replace

import pytest

from v42_job_capability import (
    Job, Option, Resources, ServiceBoundary, checkpoint_records, validate,
)
from v42_a_stage_domain_v2.domain import (
    activate_stay, contains, physical_domain, prepare_active,
)


def brute_authorized_options(job, bound, resources):
    """Enumerate explicit tiny paths without Generator masks or transfer cache."""
    duration = job.service_slots
    starts = ((job.reference_start,) if job.protected
              else tuple(range(max(job.submit, job.event), bound.latest_completion - duration + 1)))
    wide = replace(bound, allowed_starts=starts)
    expected = set()

    def keep(option):
        try:
            validate(job, option, wide, resources)
        except ValueError:
            return
        expected.add(option)

    for start in starts:
        for site in ("A", "B"):
            keep(Option(start, site, ((site, start, start + duration),)))
            for cp, physical in checkpoint_records(job, start,
                    min(start + duration, resources.control_end)):
                for dest in ("A", "B"):
                    if dest == site:
                        continue
                    for transfer_start in range(cp, resources.control_end):
                        path = resources.paths[site, dest]
                        left = resources.bytes_per_gpu * job.gpu
                        end = transfer_start
                        usage = []
                        while left > 0 and end < resources.control_end:
                            amount = min(left, *(max(0, resources.wan_capacities.get((link, end), 0))
                                                 for link in path))
                            if amount:
                                usage.extend((link, end, amount) for link in path)
                            left -= amount
                            end += 1
                        if left:
                            continue
                        restart = end + resources.restart_slots
                        keep(Option(start, site,
                                    ((site, start, cp), (dest, restart,
                                      restart + duration - (cp - start))),
                                    cp, physical, dest, transfer_start, end, restart, tuple(usage)))
    return expected


def test_independent_full_attribute_enumeration_32_fixtures_294_paths():
    cases, paths = 0, 0
    for duration in (2, 3, 4, 5):
        for latest in (8, 13):
            for restart_slots in (1, 2):
                for protected in (False, True):
                    job = Job("TINY_INDEPENDENT_CENSUS", "PENDING", 0, 0, 2, "A", duration, 1,
                              protected=protected, initial_sites=("A", "B"), checkpoint_authorized=True,
                              duration_authority="EXPLICIT_TINY_FIXTURE")
                    bound = ServiceBoundary("TINY", True, True, (2,), latest)
                    resources = Resources(
                        {"A": 3, "B": 3}, {"A": (3,), "B": (3,)},
                        {(link, t): (1 if t % 3 == 0 else 2)
                         for link in ("AB", "BA") for t in range(8)},
                        {("A", "B"): ("AB",), ("B", "A"): ("BA",)}, 8, 2,
                        {("A", 1): 3, ("B", 7): 3}, {("AB", 3): 1}, {5: 1},
                        restart_slots=restart_slots, max_active_transfers=1)
                    expected = brute_authorized_options(job, bound, resources)
                    domain = physical_domain(job, bound, resources)
                    actual = set(domain)
                    assert actual == expected
                    assert all(contains(job, bound, resources, domain, option) for option in expected)
                    cases += 1
                    paths += len(actual)
    assert cases == 32
    assert paths == 294


def fallback_fixture(cardinality=1, remove_anchor=False):
    from v42_exact.support import ExactFactory
    job = Job("j", "PENDING", 0, 0, 4, "A", 4, 2,
              initial_sites=("A", "B"), checkpoint_authorized=True,
              duration_authority="EXPLICIT_FALLBACK_TINY_FIXTURE")
    bound = ServiceBoundary("TINY", True, True, (4, 5), 12)
    resources = Resources({"A": 8, "B": 8}, {"A": (4,), "B": (4,)},
                          {(link, t): 8 for link in ("AB", "BA") for t in range(12)},
                          {("A", "B"): ("AB",), ("B", "A"): ("BA",)},
                          12, 4, {}, {}, {}, max_active_transfers=2)
    graph = ExactFactory(resources, 12).graph(job, bound)
    assert graph.events["w"]
    if remove_anchor:
        events = dict(graph.events)
        events["y"] = tuple(key for key in events["y"] if key != ("A", 4))
        events["f0"] = tuple(key for key in events["f0"] if key != ("A", 8))
        graph = replace(graph, events=events, sha="EXPLICIT_CORRUPTED_ANCHOR_FIXTURE")
    members = [f"j{i}" for i in range(cardinality)]
    jobs = {uid: replace(job, uid=uid) for uid in members}
    data = ({}, jobs, {uid: bound for uid in members}, resources, {},
            {uid: graph for uid in members}, {uid: graph for uid in members},
            dict(classes={"c": members}))
    return data


def test_singleton_mixed_flow_retains_s0_plus_anchor_and_new_stay_lazy():
    data = fallback_fixture()
    active, domains = prepare_active(data)
    uid = active[7]["classes"]["c"][0]
    old, new = data[5][uid], active[5][uid]
    domain = domains[uid]
    assert (0, "A") in domain.stays
    assert ("A", 0) not in new.events["y"]
    assert set(new.events["y"]) == set(old.events["y"])
    for family in ("q", "w", "f1"):
        assert new.events[family] == old.events[family]
    assert new.compatible == old.compatible
    assert new.physical == old.physical
    assert new.transfers == old.transfers
    assert not active[7]["complete_stay_active"]
    assert active[7]["active_stay_support"]["c"]["lazy"] > 0
    assert active[7]["noflex_nesting"]["PASS"]
    assert active[7]["classes"] == data[7]["classes"]


def test_singleton_fallback_repairs_valid_noflex_anchor_even_if_missing_s0():
    data = fallback_fixture(remove_anchor=True)
    active, _ = prepare_active(data)
    uid = active[7]["classes"]["c"][0]
    assert ("A", 4) not in data[5][uid].events["y"]
    assert ("A", 4) in active[5][uid].events["y"]
    assert ("A", 8) in active[5][uid].events["f0"]
    assert all(("A", t) in active[5][uid].states["r0"] for t in range(4, 8))
    assert active[7]["noflex_nesting"]["PASS"]


def test_already_proven_class_histogram_activates_complete_stay():
    data = fallback_fixture(cardinality=2)
    active, domains = prepare_active(data)
    uid = active[7]["classes"]["c"][0]
    assert all((site, start) in active[5][uid].events["y"] for start, site in domains[uid].stays)
    assert active[7]["complete_stay_active"]
    assert active[7]["active_stay_support"]["c"]["lazy"] == 0
    assert active[7]["classes"] == data[7]["classes"]
    assert len(active[7]["classes"]["c"]) == 2


def test_lazy_stay_activation_preserves_existing_migration_attributes():
    active, domains = prepare_active(fallback_fixture())
    uid = active[7]["classes"]["c"][0]
    old = active[5][uid]
    option = Option(0, "A", (("A", 0, 4),))
    expanded = activate_stay(active, domains, {"c": [option]})
    graph = expanded[5][uid]
    assert ("A", 0) in graph.events["y"] and ("A", 4) in graph.events["f0"]
    assert all(("A", t) in graph.states["r0"] for t in range(4))
    for family in ("q", "w", "f1"):
        assert graph.events[family] == old.events[family]
    assert graph.compatible == old.compatible
    assert graph.physical == old.physical
    assert graph.transfers == old.transfers
    assert expanded[7]["classes"] == active[7]["classes"]
    assert not expanded[7]["full_migration_domain_active"]
    with pytest.raises(ValueError, match="HARD_PHYSICAL_STAY_MEMBERSHIP"):
        activate_stay(active, domains, {"c": [replace(option, checkpoint=-2, transfer_start=999)]})


def test_lazy_stay_activation_updates_counts_and_is_content_idempotent():
    active, domains = prepare_active(fallback_fixture())
    uid = active[7]["classes"]["c"][0]
    option = Option(0, "A", (("A", 0, 4),))
    expanded = activate_stay(active, domains, {"c": [option]})
    before = active[7]["active_stay_support"]["c"]
    after = expanded[7]["active_stay_support"]["c"]
    assert after["physical"] == before["physical"]
    assert after["active"] == before["active"] + 1
    assert after["lazy"] == before["lazy"] - 1
    repeated = activate_stay(expanded, domains, {"c": [option]})
    assert repeated[5][uid].sha == expanded[5][uid].sha
    assert repeated[7]["active_stay_support"] == expanded[7]["active_stay_support"]
