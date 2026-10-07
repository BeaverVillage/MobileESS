"""Immutable, reloadable Day-Ahead Planning boundary; no AC or kernel producer."""
from dataclasses import dataclass
import json
from pathlib import Path
from .contracts import digest, require, write_once

SCHEMA_VERSION = 'V42_DAYAHEAD_PLANNING_FREEZE_V1'
PLAN_FIELDS = ('aidc_schedule', 'known_job_actions', 'unknown_arrival_policy',
               'mess_route', 'movement', 'charge_mode', 'P', 'Q', 'SOC',
               'aidc_electrical_footprint', 'grid_anchor', 'input_authority_hashes')


def require_sha(value):
    require(isinstance(value, str) and len(value) == 64
            and all(c in '0123456789abcdef' for c in value), 'SHA256_REQUIRED')


def validate_plan(plan):
    require(isinstance(plan, dict) and all(k in plan for k in PLAN_FIELDS),
            'DAYAHEAD_FREEZE_FIELDS_REQUIRED')
    require(all(plan[k] is not None for k in PLAN_FIELDS), 'DAYAHEAD_FREEZE_NULL_FIELD')
    require(all(isinstance(plan[k], (dict, list, tuple)) for k in PLAN_FIELDS),
            'DAYAHEAD_FREEZE_FIELD_SHAPE')
    policy = plan['unknown_arrival_policy']
    require(isinstance(policy, dict)
            and policy.get('interface') == 'v42_native.actual.unknown_arrival',
            'EXISTING_CAUSAL_POLICY_INTERFACE_REQUIRED')
    require_sha(policy.get('authority_sha'))
    grid = plan['grid_anchor']
    require(isinstance(grid, dict), 'GRID_ANCHOR_REQUIRED')
    require_sha(grid.get('grid_sha'))
    inputs = plan['input_authority_hashes']
    require(isinstance(inputs, dict) and inputs, 'INPUT_AUTHORITY_HASHES_REQUIRED')
    for value in inputs.values():
        require_sha(value)
    # Also rejects NaN, infinity and non-JSON values before publication.
    digest(plan)


@dataclass(frozen=True)
class FrozenDayAheadPlan:
    """Canonical bytes are the state. Every exposed mapping is a detached copy."""
    canonical_json: str

    def __post_init__(self):
        self.verify()

    @property
    def document(self):
        return json.loads(self.canonical_json)

    @property
    def plan(self):
        return self.document['plan']

    @property
    def plan_sha(self):
        return self.document['DAYAHEAD_PLAN_SHA']

    @property
    def policy_sha(self):
        return self.document['POLICY_SHA']

    @property
    def grid_sha(self):
        return self.document['GRID_SHA']

    def verify(self):
        doc = self.document
        require(set(doc) == {'schema_version', 'plan', 'DAYAHEAD_PLAN_SHA',
                             'POLICY_SHA', 'GRID_SHA'}, 'FREEZE_DOCUMENT_FIELDS')
        require(doc['schema_version'] == SCHEMA_VERSION, 'FREEZE_SCHEMA_VERSION')
        validate_plan(doc['plan'])
        require(doc['DAYAHEAD_PLAN_SHA'] == digest(doc['plan']), 'DAYAHEAD_PLAN_SHA_MISMATCH')
        require(doc['POLICY_SHA'] == digest(doc['plan']['unknown_arrival_policy']), 'POLICY_SHA_MISMATCH')
        require(doc['GRID_SHA'] == doc['plan']['grid_anchor']['grid_sha'], 'GRID_SHA_MISMATCH')
        return True

    @classmethod
    def load(cls, path):
        return cls(Path(path).read_text(encoding='utf-8'))


def freeze_day_ahead_plan(final_plan, output, *, grid_sha):
    from v42_a_stage_domain_v2.execution import require_action_authorized
    require_action_authorized(final_plan,'PLANNING_FREEZE',require_day=False)
    validate_plan(final_plan)
    require(final_plan['grid_anchor']['grid_sha'] == grid_sha, 'BACKEND_GRID_SHA_MISMATCH')
    doc = dict(schema_version=SCHEMA_VERSION, plan=final_plan,
               DAYAHEAD_PLAN_SHA=digest(final_plan),
               POLICY_SHA=digest(final_plan['unknown_arrival_policy']), GRID_SHA=grid_sha)
    frozen = FrozenDayAheadPlan(json.dumps(doc, sort_keys=True, separators=(',', ':'), allow_nan=False))
    output = Path(output)
    # Exclusive creation: an existing freeze can never be silently replaced.
    write_once(output / 'DAYAHEAD_PLANNING_FREEZE.json', frozen.document)
    for name in ('DAYAHEAD_PLAN_SHA', 'POLICY_SHA', 'GRID_SHA'):
        with (output / name).open('x', encoding='ascii', newline='\n') as stream:
            stream.write(doc[name] + '\n')
    return frozen
