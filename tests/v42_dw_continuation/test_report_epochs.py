import json
import pytest
from v42_dw_continuation.audit_helpers import ordered_events, check_segment_chain


def test_reboot_and_certificate_subround_do_not_reorder_scientific_points():
    rmps = [dict(round=15, status=2, interval=[458000, 458020]),
            dict(round=16, status=11, interval=[458030, 458031]),
            dict(round=28, status=2, interval=[35000, 35020])]
    certs = [dict(iteration=28, round=1, certified=True)]
    events = ordered_events(rmps, certs)
    assert [(point, kind) for point, kind, _ in events] == [
        (15, 'RMP'), (28, 'RMP'), (28, 'CERTIFICATION')]


def saved_segments(tmp_path):
    # Overlapping workers consume one wall interval; a new clock epoch can
    # overlap old timestamps without reducing the carried authorized debit.
    first = dict(intervals=[[10, 20], [12, 22]], budget_carried=0,
                 current_segment_union=12, union_seconds=12,
                 previous_intervals_file=None)
    second = dict(intervals=[[11, 16]], budget_carried=12,
                  current_segment_union=5, union_seconds=17,
                  previous_intervals_file='prior.json')
    for name, value in [('prior.json', first), ('latest.json', second)]:
        (tmp_path / name).write_text(json.dumps(value), encoding='utf-8')
    return second


def test_carried_wall_debit_survives_clock_epoch_overlap(tmp_path):
    saved_segments(tmp_path)
    assert check_segment_chain(tmp_path, 'latest.json')['total'] == 17


def test_reset_carried_budget_is_rejected(tmp_path):
    value = saved_segments(tmp_path)
    value.update(budget_carried=0, union_seconds=5)
    (tmp_path / 'latest.json').write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(AssertionError):
        check_segment_chain(tmp_path, 'latest.json')


def test_cyclic_segment_chain_is_rejected(tmp_path):
    value = saved_segments(tmp_path)
    value['previous_intervals_file'] = 'latest.json'
    (tmp_path / 'latest.json').write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(AssertionError):
        check_segment_chain(tmp_path, 'latest.json')
