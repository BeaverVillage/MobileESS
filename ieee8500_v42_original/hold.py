"""User-ordered hold, independent of the original IEEE123 campaign policy.

No environment variable, mutable flag, approval file, elapsed time, or campaign
completion unlocks this gate. Resumption requires a new explicit user instruction
and a reviewed change here. Existing IEEE123 entry points do not use this module.
"""

STATUS = 'HOLD_WAITING_FOR_USER_APPROVAL'


class ExecutionHold(PermissionError):
    pass


def require_execution_approval(action):
    raise ExecutionHold(f'{STATUS}:{action}')


def receipt():
    return {
        'status': STATUS,
        'day': '2025-05-01',
        'execution_authorized': False,
        'automatic_resume': False,
        'requirements_to_resume': ['IEEE123 May B2/B3 campaign completed',
                                   'separate explicit user execution approval'],
        'B0': STATUS, 'B1': STATUS, 'B2': STATUS, 'B3': STATUS,
        'NATIVE_OPTIMIZE': STATUS, 'OPENDSS_AC': STATUS,
        'INITIALIZATION_BENCHMARK': STATUS, 'WORKER': STATUS,
        'COORDINATOR': STATUS,
    }
