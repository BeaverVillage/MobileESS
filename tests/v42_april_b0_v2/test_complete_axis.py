"""Complete synthetic grid axes; never exported as April execution evidence."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from v42_april_b0_v2.statistics import complete_calibration_residuals, residuals


DAYS = ['2025-04-01', '2025-04-30']
GRID = {('n1', 'a'), ('n1', 'b'), ('n2', 'c')}


def curves():
    plan = []
    for day in DAYS:
        start = datetime.fromisoformat(day + 'T00:00:00+10:00')
        for node, phase in sorted(GRID):
            for slot in range(96):
                plan.append(dict(day=day, node=node, phase=phase, slot=slot,
                                 timestamp=(start + timedelta(minutes=15*(slot+1))).isoformat(),
                                 voltage_pu=1.))
    da = [dict(r, voltage_pu=1.002) for r in plan]
    actual = [dict(r, voltage_pu=1.006 if r['phase'] == 'a' else .992) for r in plan]
    return plan, da, actual


def complete(values, days=DAYS, grid=GRID):
    return complete_calibration_residuals(*values, days, expected_node_phases=grid)


def test_complete_authoritative_axis_including_April_final_interval():
    rows = complete(curves())
    assert len(rows) == 2*3*96
    assert {(r['node'], r['phase']) for r in rows} == GRID
    assert all(sum(r['day'] == day and r['node'] == node and r['phase'] == phase
                   for r in rows) == 96 for day in DAYS for node, phase in GRID)
    last = next(r for r in rows if r['day'] == '2025-04-30' and r['node'] == 'n1'
                and r['phase'] == 'a' and r['slot'] == 95)
    assert last['timestamp'] == '2025-05-01T00:00:00+10:00'
    assert last['r_up'] == pytest.approx(.006)
    assert next(r for r in rows if r['phase'] == 'b')['r_down'] == pytest.approx(.008)


@pytest.mark.parametrize('missing_slot', [0, 47, 95])
def test_identically_truncated_curves_do_not_establish_full_days(missing_slot):
    truncated = [[r for r in values if r['slot'] != missing_slot] for values in curves()]
    # Matching axes remain useful for arithmetic, but cannot enter calibration.
    assert residuals(*truncated, DAYS)
    with pytest.raises(ValueError, match='INCOMPLETE_GRID_AXIS'):
        complete(truncated)


def test_identically_missing_grid_node_is_not_inferred_from_remaining_curves():
    truncated = [[r for r in values if r['node'] != 'n2'] for values in curves()]
    with pytest.raises(ValueError, match='INCOMPLETE_GRID_AXIS'):
        complete(truncated)


def test_missing_one_node_phase_slot_on_one_day_is_rejected():
    truncated = [[r for r in values if not (r['day'] == DAYS[1] and r['node'] == 'n1'
                  and r['phase'] == 'b' and r['slot'] == 13)] for values in curves()]
    with pytest.raises(ValueError, match='INCOMPLETE_GRID_AXIS'):
        complete(truncated)


def test_unexpected_node_phase_cannot_replace_authoritative_phase():
    changed = deepcopy(curves())
    for values in changed:
        for row in values:
            if row['node'] == 'n2':
                row['phase'] = 'a'
    with pytest.raises(ValueError, match='INCOMPLETE_GRID_AXIS'):
        complete(changed)


def test_one_curve_missing_sample_fails_three_curve_alignment():
    changed = list(curves())
    changed[1] = changed[1][:-1]
    with pytest.raises(ValueError, match='THREE_CURVE_ALIGNMENT'):
        complete(changed)


@pytest.mark.parametrize('grid,error', [
    (None, 'COMPLETE_GRID_AUTHORITY_REQUIRED'),
    (set(), 'COMPLETE_GRID_AUTHORITY_REQUIRED'),
    ({'n1': ['a']}, 'COMPLETE_GRID_AUTHORITY_REQUIRED'),
    ({('n1', 'd')}, 'EXPECTED_NODE_PHASE_AXIS'),
    ({('', 'a')}, 'EXPECTED_NODE_PHASE_AXIS'),
    ([('n1', 'a', 'extra')], 'EXPECTED_NODE_PHASE_AXIS'),
    ([('n1', 'a'), ('n1', 'a')], 'DUPLICATE_EXPECTED_NODE_PHASE'),
])
def test_expected_grid_authority_must_be_explicit_valid_and_unique(grid, error):
    with pytest.raises(ValueError, match=error):
        complete(curves(), grid=grid)


def test_empty_date_population_cannot_pass_vacuously():
    with pytest.raises(ValueError, match='COMPLETE_FROZEN_DATES_REQUIRED'):
        complete(([], [], []), days=[])


@pytest.mark.parametrize('field,value,error', [
    ('slot', 96, 'DAY_SLOT_AXIS'),
    ('phase', 'd', 'NODE_PHASE_AXIS'),
    ('timestamp', '2025-04-01T00:00:00+10:00', 'TIMESTAMP_SLOT_ALIGNMENT'),
])
def test_invalid_supplied_sample_axis_is_rejected(field, value, error):
    changed = deepcopy(curves())
    for values in changed:
        values[0][field] = value
    with pytest.raises(ValueError, match=error):
        complete(changed)
