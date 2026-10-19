"""Project the original R0 file onto the exact native roster, with no schedule changes."""
from pathlib import Path
import numpy as np
from v44.common import read,record,atomic
from v44.daily import clone
from v43_arms.reference import project as _original_project


def roster(native,rows):
    known={r['job_uid'] for r in native['known_population']}
    old={r['job_uid']:r for r in rows}
    if len(old)!=len(rows) or not known<=set(old):raise ValueError('R045_REFERENCE_MISSING_OR_DUPLICATE_NATIVE_UID')
    extra=[old[u] for u in sorted(set(old)-known)]
    for row in extra:
        if (row.get('operating_day')!=native['day'] or row.get('terminal_class')!='POST_H_ONLY'
            or row.get('state_at_issue')!='PENDING' or row.get('AIDC_site')!='UNASSIGNED'
            or row.get('start_slot',0)<120 or row.get('end_slot',0)<120
            or row.get('common_terminal_obligation',{}).get('must_complete_by_H') is not False
            or row.get('accepted_A0_assignment_and_WAN') or row.get('migration_selected')):
            raise ValueError('R045_REFERENCE_EXTRA_HAS_CURRENT_HORIZON_OR_ASSIGNED_EFFECT')
    return [r for r in rows if r['job_uid'] in known],extra


def project(native):
    rows=read(native['reference']['path']);selected,extra=roster(native,rows)
    original_read=_original_project.__globals__['read'];source=Path(native['reference']['path']).resolve()
    def exact_read(path):return selected if Path(path).resolve()==source else original_read(path)
    result=clone(_original_project,read=exact_read)(native)
    # The canonical native roster and every original site/start/CC4 rule stay intact.
    if extra:
        from .operations import OPS
        atomic(OPS/'R045_R0_ROSTER_PROJECTION.json',dict(PASS=True,day=native['day'],
            original_reference=record(source),original_rows=len(rows),native_rows=len(selected),
            excluded_outside_native_reference_UIDs=[r['job_uid'] for r in extra],
            excluded_original_records=extra,current_horizon_effect=0,native_jobs_removed=0,
            original_sites_starts_durations_and_CC4_unchanged=True))
    return result
