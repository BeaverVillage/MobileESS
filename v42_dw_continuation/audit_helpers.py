"""Read-only report ordering and independent segmented wall-budget checks."""
import json
import math


def ordered_events(rmps, certificates):
    # perf_counter epochs can change after reboot; iteration is durable.
    events = [(r['round'], 'RMP', r) for r in rmps if r['status'] == 2]
    events += [(c['iteration'], 'CERTIFICATION', c)
               for c in certificates if c['certified']]
    return sorted(events, key=lambda e: (e[0], e[1] != 'RMP'))


def check_segment_chain(directory, name='DW_OPTIMIZE_INTERVALS.json'):
    seen = set()
    segments = []
    while name:
        assert name not in seen, 'Cyclic optimize segment chain'
        seen.add(name)
        data = json.loads((directory / name).read_text(encoding='utf-8'))
        merged = []
        for start, end in sorted(data['intervals']):
            assert math.isfinite(start) and math.isfinite(end) and start <= end
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        own = sum(end - start for start, end in merged)
        carried = data['budget_carried']
        assert abs(own - data['current_segment_union']) < 1e-8
        assert abs(carried + own - data['union_seconds']) < 1e-8
        previous = data['previous_intervals_file']
        if previous:
            parent = json.loads((directory / previous).read_text(encoding='utf-8'))
            assert abs(parent['union_seconds'] - carried) < 1e-8
        else:
            assert carried == 0
        segments.append(dict(file=name, own_union=own, carried=carried,
                             total=data['union_seconds']))
        name = previous
    assert abs(sum(s['own_union'] for s in segments) - segments[0]['total']) < 1e-8
    return dict(PASS=True, segments=segments, total=segments[0]['total'],
                monotonic_clock_epochs_not_combined=True)
