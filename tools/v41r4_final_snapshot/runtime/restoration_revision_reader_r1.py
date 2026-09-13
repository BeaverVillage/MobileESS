"""No-op control schema reader: instantiate full MESS slots only for restoration."""
import inspect,sys
from pathlib import Path
import restoration_revision_v1 as base
source=inspect.getsource(base.audit_day)
old="            initial=MessTrajectory(tuple(_restore_slots(original_d['MESS_trajectory'])))\n            final=MessTrajectory(tuple(_restore_slots(d['MESS_trajectory'])))"
assert source.count(old)==1
source=source.replace(old,'            initial=final=None')
old="            if primary=='FAIL':\n"
assert source.count(old)==1
source=source.replace(old,old+"                initial=MessTrajectory(tuple(_restore_slots(original_d['MESS_trajectory'])))\n                final=MessTrajectory(tuple(_restore_slots(d['MESS_trajectory'])))\n")
ns=dict(vars(base));exec(compile(source,__file__+'::no_op_reader','exec'),ns)
if __name__=='__main__':
    seal=base.OUT/'READER_R1_BINDING.json'
    if sys.argv[1]=='freeze':base.save(seal,dict(status='FROZEN',adapter=base.record(__file__),rule=base.record(base.OUT/'RULE_FREEZE.json'),reason='B0/B1 no-op commands omit unused travel statistics; defer full trajectory construction until Primary Fresh FAIL; no numerical rule change'))
    else:
        base.verify(base.read(seal)['adapter']);ns['audit_day'](sys.argv[1])
