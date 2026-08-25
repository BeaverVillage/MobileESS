import pytest

from pfr.cpu_topology import allocate_disjoint_cpu_groups


SIBLINGS_8X2 = tuple((2 * core, 2 * core + 1) for core in range(8))


@pytest.mark.parametrize(
    ("workers", "threads", "expected_used"),
    ((4, 4, 16), (5, 3, 15), (6, 2, 12)),
)
def test_affinity_groups_are_disjoint_and_sibling_free(
    workers: int,
    threads: int,
    expected_used: int,
) -> None:
    groups = allocate_disjoint_cpu_groups(
        SIBLINGS_8X2,
        workers=workers,
        threads_per_worker=threads,
    )
    flattened = [cpu for group in groups for cpu in group]
    core_by_cpu = {
        cpu: core for core, siblings in enumerate(SIBLINGS_8X2) for cpu in siblings
    }

    assert len(groups) == workers
    assert all(len(group) == threads for group in groups)
    assert len(flattened) == expected_used
    assert len(flattened) == len(set(flattened))
    assert all(
        len({core_by_cpu[cpu] for cpu in group}) == threads for group in groups
    )


def test_affinity_allocation_fails_closed_on_oversubscription() -> None:
    with pytest.raises(ValueError, match="needs 18 logical CPUs"):
        allocate_disjoint_cpu_groups(
            SIBLINGS_8X2,
            workers=6,
            threads_per_worker=3,
        )


def test_6x2_balances_smt_contention_across_worker_pairs() -> None:
    groups = allocate_disjoint_cpu_groups(
        SIBLINGS_8X2,
        workers=6,
        threads_per_worker=2,
    )

    assert groups == (
        (0, 2),
        (4, 6),
        (8, 10),
        (12, 14),
        (1, 5),
        (9, 13),
    )


@pytest.mark.parametrize(
    ("workers", "threads", "expected_sizes"),
    (
        (4, 4, (4, 4, 4, 4)),
        (5, 3, (4, 3, 3, 3, 3)),
        (6, 2, (3, 3, 3, 3, 2, 2)),
    ),
)
def test_full_process_budgets_use_every_allowed_cpu(
    workers: int,
    threads: int,
    expected_sizes: tuple[int, ...],
) -> None:
    groups = allocate_disjoint_cpu_groups(
        SIBLINGS_8X2,
        workers=workers,
        threads_per_worker=threads,
        use_all_cpus=True,
    )

    assert tuple(map(len, groups)) == expected_sizes
    assert sorted(cpu for group in groups for cpu in group) == list(range(16))
