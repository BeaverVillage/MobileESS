"""Current 31-day input routing; no prior A1/MESS decision is a new result."""
import copy
import math
import types
from pathlib import Path
from .common import *


def build_inputs(root, days):
    import pandas as pd
    from v42_holdout.common import source_freeze
    import v42_holdout.inputs as frozen
    from v42_capacity.reference import build_reference
    from v42_may01.state import cohort_key
    from v42_boundary.boundaries import known_window
    from v42_job_capability import Job, checkpoint_records
    spec = source_freeze()
    # Same exact raw request-only projection. Retrospective start/end columns are
    # not read. Its diagnostic write is routed to this new run's input directory.
    raw = types.FunctionType(frozen.requests.__code__, dict(frozen.requests.__globals__, OUT=root / 'inputs'))(spec)
    template = read(ROOT / 'docs/v42_final_integration/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json')
    bundles = {}; sources = [record(Path(spec['archive']['path']))]
    day_specs = {s['day']: s for s in spec['day_sources']}
    for day in days:
        folder = ROOT / 'docs/v42_may_b0_zero_margin_holdout/INPUT/BUNDLE' / ('DAY_' + day.replace('-', ''))
        p = read(folder / 'PLANNING_INPUT_BUNDLE.json')
        refs, audit = build_reference(p['known_population'], p['capacities'], p['rack_compatibility'], issue_time=p['issue_time'])
        if not audit['full_reference_ready']:
            raise ValueError('CURRENT_COMMON_REFERENCE_NOT_READY:' + day)
        old_path = CODE / f'frozen_artifacts/v41r3_may/inputs/{day}/common_q90_v3/COMMON_B0_REFERENCE_JOBS.json'
        if not old_path.exists():
            candidates = sorted((CODE / f'frozen_artifacts/v41r3_may/inputs/{day}').glob('common_q90*/COMMON_B0_REFERENCE_JOBS.json'))
            old_path = candidates[0] if candidates else None
        r0 = {r['job_uid']: r for r in read(old_path)} if old_path else {}
        if old_path: sources.append(record(old_path))
        jobs = []; windows = []; snapshot = day_specs[day]['snapshot']
        for ref in refs:
            uid = ref['job_uid']; request = raw[uid][0]
            if request['source_member'] != ref['source_member'] or request['source_row'] != ref['source_row']:
                raise ValueError('EXACT_CURRENT_RAW_IDENTITY_DRIFT')
            start = int(ref['reference_start']); n = ref['service_slots']; state = ref['state']
            cohort = cohort_key(request['qos'], request['partition'], ref['GPU_gang'], request['requested_seconds'], request['nodes_req'])
            j = dict(ref, known_at_issue=True, planning_eligible=True,
                     reference_start_if_authorized=start, reference_end=start+n,
                     V10_Q50_total_seconds=ref['Q50_total_seconds'],
                     exact_service_seconds=ref['nominal_remaining_seconds'] if state == 'RUNNING' else ref['Q50_total_seconds'],
                     risk_nominal_completion_issue_slot=(math.ceil((ref['Q50_total_seconds']-ref['elapsed_seconds'])/900)
                                                        if state == 'RUNNING' else math.ceil(start+ref['Q50_total_seconds']/900)),
                     cohort=cohort, source_snapshot_sha=snapshot['sha256'], can_timeshift=False,
                     can_prestart_place=state == 'PENDING' and n > 0 and len(ref['compatible_sites']) > 1,
                     can_checkpoint_migrate=False, delay_budget_slots=0, synthetic_completion=False)
            source = r0.get(uid)
            # The accepted known_window fails closed for missing authority. A
            # historical reference with a different current start is not promoted
            # to a new source window or silently shifted to match the current R0.
            usable = source is not None and source['start_slot'] == start and source['source_snapshot_sha256'] == snapshot['sha256']
            window = known_window(j, source if usable else None)
            if source is not None and not usable:
                window['reason'] = 'CURRENT_REFERENCE_DIFFERS_FROM_SOURCE_WINDOW_FIXED_START'
            j['can_timeshift'] = window['can_timeshift']
            j['delay_budget_slots'] = window['latest_start'] - start
            probe = Job(uid, state, 0, 0, start, ref['reference_site'], n, ref['GPU_gang'],
                        qos=str(request['qos']), protected=cohort.split('|')[3] == 'True',
                        initial_sites=tuple(ref['compatible_sites']), checkpoint_authorized=True,
                        elapsed_seconds=ref['elapsed_seconds'], duration_authority=ref['runtime_authority']) if n > 0 else None
            j['can_checkpoint_migrate'] = n > 0 and len(ref['compatible_sites']) > 1 and any(
                24 <= cp < 118 for cp, _ in checkpoint_records(probe, start, min(start+n,120)))
            jobs.append(j); windows.append(window)
        cc = p['forecast_inputs']['current_CC4']
        bundle = copy.deepcopy(template)
        bundle.update(schema='V42_B1_CURRENT_MAY_NATIVE_INPUT_V1', day=day, issue_time=p['issue_time'],
                      role='B1_PRODUCTION', known_population=jobs, capacities=p['capacities'],
                      racks=[dict(aidc_id=s, compatibility_GPU_limit=c, rack_pool_id=f'{s}_LP{i:02d}')
                             for s, values in p['rack_compatibility'].items() for i,c in enumerate(values,1)],
                      reference=dict(rows=refs, audit=audit),
                      C0_Q50=cc['Q50_GPUh'], C0_Q90=cc['Q90_GPUh'], RUNTIME_PROVIDER_READY=True,
                      current_reference_generated=True, old_A1_freeze_reused=False,
                      electrical_certificate=record(CODE / f'frozen_artifacts/v41r4_may/e/{day.replace("-", "")}/V41_ELECTRICAL_CERTIFICATE.json'),
                      current_day_folder=str(folder), source_window_audit=windows)
        bundle['unknown_nominal_GPU_96'] = cc['nominal_unknown_GPU_96']
        bundle['unknown_nominal_GPU'] = cc['nominal_unknown_GPU_96']
        bundle['CC4_reserve_GPU'] = cc['spread_headroom_GPU_96']
        bundle['grid_outputs'] = read(bundle['electrical_certificate']['path'])['outputs']
        bundle['source_versions'] = 'Current V42 full physical known population/common Q50 reference; current day C0/C1/electrical input authority; historical implementation only'
        bundle['forecast_inputs'] = p['forecast_inputs']
        dest = root / 'inputs' / day
        atomic(dest / 'NATIVE_INPUT.json', bundle)
        atomic(dest / 'COMMON_REFERENCE.json', dict(rows=refs, audit=audit))
        bundles[day] = record(dest / 'NATIVE_INPUT.json')
        sources.extend(record(x) for x in folder.iterdir() if x.is_file())
        sources.append(record(Path(snapshot['path'])))
        sources.append(bundle['electrical_certificate'])
        cert = read(bundle['electrical_certificate']['path'])
        sources.extend(record(Path(x['path'])) for x in cert['outputs'].values())
    # Immutable static WAN/model fields inherited from the verified current V42
    # native schema, not from any historical B1 optimized decision.
    sources.append(record(ROOT / 'docs/v42_final_integration/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'))
    return bundles, list({s['path']: s for s in sources}.values())
