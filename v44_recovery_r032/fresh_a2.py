"""Reuse completed tight M1; rebuild and solve A2 with correct CC4 work."""
import inspect, textwrap
from v44_recovery_r029 import fresh_a2_case


def compiled():
    source = textwrap.dedent(inspect.getsource(fresh_a2_case.run))
    replacements = {
        "('2025-05-02','B3','attempt001')": "('2025-05-02','B3','attempt014')",
        'from .parent_admission import validate as validate_parent':
            'from v44_recovery_r032.parent_admission import validate as validate_parent',
        'R029_USER_AUTHORIZATION.json': 'R032_CC4_DATE_REPAIR_AUTHORIZATION.json',
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError('R032_FRESH_A2_BOUNDARY_DRIFT:'+old)
        source = source.replace(old, new)
    namespace = dict(fresh_a2_case.run.__globals__)
    exec(compile(source, __file__+'.generated', 'exec'), namespace)
    return namespace['run']
