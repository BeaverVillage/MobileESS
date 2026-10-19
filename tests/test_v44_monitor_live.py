import json
from v44_monitor_live import actual_state


def write(root, name, data):
    path = root/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def test_live_activity_does_not_advance_physical_slot_or_variant_counter(tmp_path):
    write(tmp_path, 'ACTUAL/progress.json', dict(UTC='2026-10-18T04:00:00+00:00',
          phase='EVENT_ACTUAL_CURRENT_AC', completed_control_ticks=47,
          control_time_seconds=1000, current_AC_calls=517))
    write(tmp_path, 'CURRENT_AC_R029_PERFORMANCE.json', dict(arm='B3',
          UTC='2026-10-18T04:05:00+00:00', complete_probe_calls=631))
    p, _, activity = actual_state(tmp_path, 'B3', now=1792296302)
    assert p['completed_control_ticks'] == 47
    assert p['control_time_seconds'] == 1000
    assert p['current_AC_calls'] == 517
    assert activity['completed_probe_calls'] == 631
    assert activity['activity_scope'] == 'ACTUAL_ALL_VARIANTS_COMPLETED_PROBES'


def test_newer_heartbeat_snapshot_is_used(tmp_path):
    write(tmp_path, 'ACTUAL/progress.json', dict(UTC='2026-10-18T04:00:00+00:00', completed_control_ticks=10))
    write(tmp_path, 'ACTUAL/HEARTBEAT.json', dict(UTC='2026-10-18T04:01:00+00:00', latest=dict(completed_control_ticks=11)))
    assert actual_state(tmp_path, 'B3')[0]['completed_control_ticks'] == 11


def test_older_heartbeat_does_not_replace_newer_event(tmp_path):
    write(tmp_path, 'ACTUAL/progress.json', dict(UTC='2026-10-18T04:02:00+00:00', completed_control_ticks=12))
    write(tmp_path, 'ACTUAL/HEARTBEAT.json', dict(UTC='2026-10-18T04:01:00+00:00', latest=dict(completed_control_ticks=11)))
    assert actual_state(tmp_path, 'B3')[0]['completed_control_ticks'] == 12


def test_fresh_does_not_display_old_actual_activity(tmp_path):
    write(tmp_path, 'ACTUAL/progress.json', dict(phase='INDEPENDENT_FRESH'))
    write(tmp_path, 'CURRENT_AC_R029_PERFORMANCE.json', dict(arm='B3', UTC='2026-10-18T04:00:00+00:00', complete_probe_calls=631))
    assert 'completed_probe_calls' not in actual_state(tmp_path, 'B3')[2]


def test_wrong_arm_or_partial_json_is_not_published(tmp_path):
    write(tmp_path, 'CURRENT_AC_R029_PERFORMANCE.json', dict(arm='B1', UTC='2026-10-18T04:00:00+00:00', complete_probe_calls=631))
    assert 'completed_probe_calls' not in actual_state(tmp_path, 'B3')[2]
    (tmp_path/'CURRENT_AC_R029_PERFORMANCE.json').write_text('{"partial":', encoding='utf-8')
    assert 'completed_probe_calls' not in actual_state(tmp_path, 'B3')[2]
