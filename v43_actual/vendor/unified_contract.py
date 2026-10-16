import hashlib
import json


BINDING_FIELDS = ('science_sha', 'case_sha', 'physical_sha', 'time_axis_sha',
                  'qos_sha', 'cc4_sha', 'runtime_sha', 'response_sha',
                  'initial_state_sha', 'aidc_anchor', 'mess_anchor', 'interface_sha')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode('utf8')).hexdigest()


def require_bindings(actual, expected):
    for key in BINDING_FIELDS:
        value = actual.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('UNIFIED_COMPLETE_SHA_REQUIRED:' + key)
        if value != expected.get(key):
            raise ValueError('UNIFIED_SHARED_ANCHOR_DRIFT:' + key)
    return dict(actual)
