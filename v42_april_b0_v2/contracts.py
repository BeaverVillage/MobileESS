"""User-defined B0, bound to current V42 inputs, never historical B0 semantics.

These validators do not generate missing reference decisions, run a solver,
or attest that an unbound physical producer is scientifically authorized.
"""
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from v42_final.common import MODEL

BASE = '86d77673a5f1cc04729cc742090bba1fb72a09fa'
QUANTILES = (.90, .95, .975, .99)
ZERO_ACTIONS = ('timeshift', 'migration', 'prestart_relocation', 'site_allocation',
                'mess_optimization', 'global_optimization', 'local_p_repair',
                'local_q_repair', 'route_repair', 'schedule_repair')
AUTHORITY_KEYS = ('workload', 'runtime', 'reference', 'capacity', 'it_pcc', 'grid', 'forecast')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def april(day):
    d = date.fromisoformat(day)
    require(d.year == 2025 and d.month == 4, 'APRIL_2025_ONLY')
    require(d.isoformat() == day, 'CANONICAL_DAY')
    return day


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha64(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def reference_missing(row):
    """No site/time inference; zero service is allowed only with current authority."""
    missing = []
    for field in ('job_id', 'reference_start', 'planning_site', 'service_slots', 'GPU_gang', 'runtime_authority'):
        value = row.get(field)
        if value is None or value == '' or value == 'NOT_AVAILABLE':
            missing.append(field)
    return missing


def validate_controls(controls):
    require(set(controls) == set(ZERO_ACTIONS), 'EXPLICIT_ZERO_ACTIONS_REQUIRED')
    require(all(type(controls[k]) is int and controls[k] == 0 for k in ZERO_ACTIONS), 'B0_ACTION_FORBIDDEN')


def validate_flags(flags):
    expected = dict(B0_ONLY=True, AIDC_PRESENT=True, AIDC_WORKLOAD_PRESENT=True,
                    AIDC_FLEXIBILITY_OPTIMIZATION=False, MESS_ACTIVE=False,
                    B1_RUN=False, B2_RUN=False, B3_RUN=False, M1_BENDERS_RUN=False,
                    MAY_USED_FOR_CALIBRATION=False, MAY_RUN=False, FINAL_MARGIN_ACCEPTED=False,
                    historical_requested_walltime_fallback=False)
    require(all(flags.get(k) is v for k, v in expected.items()), 'B0_SCOPE_VIOLATION')


@dataclass(frozen=True)
class FrozenReference:
    payload: str
    sha256: str

    @property
    def document(self):
        require(hashlib.sha256(self.payload.encode()).hexdigest() == self.sha256, 'FROZEN_REFERENCE_CHANGED')
        return json.loads(self.payload)


def freeze_reference(day, common_rows, reference_rows, authority, flags, controls, mess):
    april(day)
    validate_flags(flags)
    validate_controls(controls)
    require(all(sha64(authority.get(k)) for k in AUTHORITY_KEYS), 'COMMON_AUTHORITY_UNBOUND')
    require(isinstance(common_rows, list) and common_rows, 'COMMON_WORKLOAD_REQUIRED')
    require(len(reference_rows) == len(common_rows), 'WORKLOAD_DROP')
    require(all(not reference_missing(r) for r in common_rows), 'BLOCKED_REFERENCE_MAPPING')
    ids = [r['job_id'] for r in common_rows]
    require(len(set(ids)) == len(ids), 'DUPLICATE_JOB_ID')
    require(digest(common_rows) == digest(reference_rows), 'COMMON_WORKLOAD_CHANGED')
    for row in common_rows:
        require(row['runtime_authority'] == MODEL, 'CURRENT_V42_RUNTIME_REQUIRED')
        require(isinstance(row['planning_site'], str) and row['planning_site'].startswith('AIDC'), 'REFERENCE_SITE_REQUIRED')
        for field in ('reference_start', 'service_slots', 'GPU_gang'):
            require(type(row[field]) is int and row[field] >= (1 if field == 'GPU_gang' else 0), 'CANONICAL_INTEGER_FIELDS')
    require(set(mess) == {'P', 'Q', 'movement'}, 'MESS_OFF_FIELDS')
    require(all(isinstance(mess[k], list) and len(mess[k]) > 0 for k in mess), 'MESS_ARRAYS_REQUIRED')
    require(len({len(mess[k]) for k in mess}) == 1, 'MESS_AXIS')
    require(all(math.isfinite(x) and x == 0 for values in mess.values() for x in values), 'MESS_MUST_BE_ZERO')
    doc = dict(day=day, jobs=reference_rows, authority=authority, flags=flags, controls=controls,
               mess=mess, primary_band=[.95, 1.05], production_band_modified=False)
    payload = canonical(doc)
    return FrozenReference(payload, hashlib.sha256(payload.encode()).hexdigest())


def presence(receipt, expected_workload_sha):
    require(receipt.get('AIDC_PRESENT') is True, 'AIDC_OFF')
    for k in ('it_energy_kwh', 'pcc_energy_kwh', 'active_slots', 'served_workload'):
        value = receipt.get(k)
        require(isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value > 0, 'NONZERO_AIDC_REQUIRED:' + k)
    require(receipt.get('common_workload_sha256') == expected_workload_sha, 'WORKLOAD_CHANGED')
    require(receipt.get('workload_dropped') is False, 'WORKLOAD_DROP')


def replay_receipt(frozen, receipt, *, actual):
    doc = frozen.document
    require(receipt.get('day') == doc['day'], 'REPLAY_DAY')
    require(receipt.get('frozen_reference_sha256') == frozen.sha256, 'FROZEN_REFERENCE_CHANGED')
    require(receipt.get('common_authority') == doc['authority'], 'COMMON_AUTHORITY_CHANGED')
    validate_controls(receipt.get('controls', {}))
    require(receipt.get('engine') == 'OpenDSS' and receipt.get('fresh') is True
            and receipt.get('synthetic') is False, 'FRESH_REAL_OPENDSS_REQUIRED')
    for key in ('physical_arrays_sha256', 'inputs_sha256', 'grid_sha256'):
        require(sha64(receipt.get(key)), 'REPLAY_LINEAGE_REQUIRED')
    require(receipt.get('grid_sha256') == doc['authority'].get('grid'), 'GRID_CHANGED')
    if actual:
        require(receipt.get('execution_layer') == 'DDAY_ACTUAL', 'ACTUAL_LAYER')
        require(receipt.get('DayAhead_power_arrays_copied') is False, 'FORECAST_COPIED_TO_ACTUAL')
        require(receipt.get('IT_recomputed_from_actual_occupancy') is True, 'ACTUAL_OCCUPANCY_REQUIRED')
        require(receipt.get('realized_authority_verified') is True, 'REALIZED_AUTHORITY_UNAVAILABLE')
    else:
        require(receipt.get('execution_layer') == 'OFFLINE_CALIBRATION', 'OFFLINE_LAYER')
        require(receipt.get('OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY') is True, 'OFFLINE_ONLY')
        require(receipt.get('operational_gate') is False, 'OFFLINE_NOT_OPERATIONAL_GATE')
        require(receipt.get('inputs_sha256') == doc['authority'].get('forecast'), 'FORECAST_CHANGED')
    # No convergence/physical PASS requirement here: diagnostic failures are
    # retained and must never trigger schedule repair or outcome date filtering.


def pair_receipts(frozen, offline, actual):
    replay_receipt(frozen, offline, actual=False)
    replay_receipt(frozen, actual, actual=True)
    require(actual['inputs_sha256'] != offline['inputs_sha256'], 'ACTUAL_INPUT_PROVENANCE_DISTINCT')
