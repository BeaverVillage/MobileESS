"""Select only an actually completed May19 four-objective certificate."""
from v42_pr134_b1.common import read,record
from .policy import OVERNIGHT
def final_acceptance():
    for name,engine in (('P2_CG_RESULT.json','WEIGHTED_CG'),('P2_CASE_RESULT.json','EXACT_CASES')):
        path=OVERNIGHT/name
        if path.exists():
            r=read(path)
            if r.get('A1_accepted'):
                if len(r['stages'])!=2 or {s['component'] for s in r['stages']}!={'shift_magnitude','prestart_relocation'}:raise ValueError('ALL_INHERITED_P2_STAGES_REQUIRED')
                for s in r['stages']:
                    if record(s['certificate']['path'])!=s['certificate'] or not read(s['certificate']['path'])['PASS']:raise ValueError('ACCEPTED_P2_CERTIFICATE_DRIFT')
                return path,engine
    raise PermissionError('ACTUAL_MAY19_A1_ACCEPTANCE_REQUIRED')
