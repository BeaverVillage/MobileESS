"""Frozen non-admission is a service ledger, never a physical IDC.

This applies the existing V41 P0-07 full-backlog authority to a Q90 interval
that newly overlaps Day D. It does not admit, assign, or remove any job.
"""
from .migration import active, BEGIN, END


def unadmitted(row):
    if not active(row) or row.get('r1_reference_site') != 'UNASSIGNED':
        return False
    if row['AIDC_site'] != 'UNASSIGNED' or row.get('migration_selected'):
        raise ValueError('FROZEN_UNADMITTED_JOB_CANNOT_EXECUTE_OR_MIGRATE')
    return True


def overlapping_backlog(row):
    return unadmitted(row) and max(BEGIN, row['start_slot']) < min(END, row['end_slot'])


def physical_parts(row, parts):
    if not unadmitted(row):
        return parts
    if any(p['site'] != 'UNASSIGNED' for p in parts):
        raise ValueError('FROZEN_UNADMITTED_JOB_HAS_PHYSICAL_SEGMENT')
    return []
