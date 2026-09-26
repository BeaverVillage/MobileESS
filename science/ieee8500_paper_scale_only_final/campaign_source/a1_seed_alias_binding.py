"""Normalize same-file B1 seed aliases without weakening the original gate."""
import copy,os
from pathlib import Path
import v41r4_ieee8500_adapter as adapter
ORIGINAL=adapter.validated_B1_assignment
def normalize(bundle,root):
    result=copy.deepcopy(bundle)
    for key,name in [('assignment','assignment.npz'),('variable_names','variable_names.npz')]:
        record=result[key]
        source=Path(record['path'])
        target=Path(root).absolute()/'B1_REUSE'/name
        assert os.path.samefile(source,target),('SEED_ALIAS_NOT_SAME_FILE',key)
        assert adapter.sha(source)==adapter.sha(target)==record['sha256'],('SEED_SHA_MISMATCH',key)
        record['path']=str(target)
    return result
def validated_B1_assignment(model,ctx):
    old=ctx.ieee8500_final_B1_seed
    ctx.ieee8500_final_B1_seed=normalize(old,ctx.new_production_root)
    try:return ORIGINAL(model,ctx)
    finally:ctx.ieee8500_final_B1_seed=old
def install():
    adapter.validated_B1_assignment=validated_B1_assignment
