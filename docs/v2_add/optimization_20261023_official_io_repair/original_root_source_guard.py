"""Supplement the package source freeze with its flat Job capability module."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
from v2_add_preflight.stage_common import ROOT,SOURCE,record
from v2_add_preflight.stage_immutable_io import ImmutableRecords
from v2_add_preflight.prestart_execution import atomic

@contextmanager
def protect():
    path=ROOT/'v42_job_capability.py'
    original=subprocess.check_output(['git','rev-parse',SOURCE+':v42_job_capability.py'],cwd=ROOT,text=True).strip()
    actual=subprocess.check_output(['git','hash-object','--path=v42_job_capability.py',str(path)],cwd=ROOT,text=True).strip()
    if actual!=original:raise ValueError('ORIGINAL_R043_FLAT_JOB_CAPABILITY_SOURCE_CHANGED')
    frozen=ImmutableRecords([path])
    try:
        getter=frozen.wrap(record);row=getter(path)
        proof=dict(PASS=True,scope='Additional original flat module; package freeze remains intact',
            original_r043=SOURCE,original_git_blob=original,current_git_blob=actual,
            files=[row],write_and_replace_denied_for_context_lifetime=True,
            scientific_model_source_changed=False,producer=record(__file__))
        atomic(Path(__file__).parent/'ORIGINAL_ROOT_SOURCE_VERIFICATION.json',proof)
        yield proof
        if record(path)!=row:raise ValueError('ORIGINAL_ROOT_SOURCE_DRIFT')
    finally:frozen.close()
