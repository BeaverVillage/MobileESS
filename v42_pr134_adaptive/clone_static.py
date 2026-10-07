"""Clone completed static model only. No points, basis, locks or native clock."""
import sys,shutil
from .common import *
day,oldtag,newtag=sys.argv[1:];source=CASE/day/oldtag;target=CASE/day/newtag
if target.exists():raise PermissionError('FRESH_STATIC_IDENTITY_ALREADY_EXISTS')
target.mkdir(parents=True)
names=['EXPANDED_MATRIX.npz','EXPANDED_ATTRIBUTES.npz','NATIVE_NAMES.npz','SCIENTIFIC_INTERFACES.pkl.gz','DATA.pkl','OBJECTIVES.json','CENSUS.json','DOMAIN_AUTHORITY_AUDIT.json','GLOBAL_NUMERIC_IDENTITY.json','F2-CRA_MODEL_STATS.json']
for name in names:shutil.copyfile(source/name,target/name)
atomic(target/'STATIC_ONLY.json',dict(PASS=True,optimizer_calls=0,source_commit=BASE,
    matrix=record(target/'EXPANDED_MATRIX.npz'),attributes=record(target/'EXPANDED_ATTRIBUTES.npz'),descriptor=record(target/'SCIENTIFIC_INTERFACES.pkl.gz')))
atomic(target/'ZERO_START_STATIC_CLONE_AUDIT.json',dict(PASS=True,old_static=source,new_identity=target,
    copied=names,points_copied=0,locks_copied=0,warm_starts_copied=0,basis_copied=0,native_clock_copied=0,
    reason='diagnostic report metadata missing; repeat fresh LP/MIP with identical captured scientific matrix'))
