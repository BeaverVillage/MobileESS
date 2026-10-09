from v42_b2_seed_recovery_v18.common import *
from pathlib import Path
import os,json,uuid
from v42_pr134_b1.common import clean,replace_file,write_lock

def io_path(path):
    """Windows extended paths affect storage only, never recorded authority."""
    path=Path(path).absolute();value=str(path)
    if os.name!='nt' or value.startswith('\\\\?\\'):return path
    if value.startswith('\\\\'):return Path('\\\\?\\UNC\\'+value[2:])
    return Path('\\\\?\\'+value)

def atomic(path,value):
    path=Path(path);io_path(path.parent).mkdir(parents=True,exist_ok=True)
    # Old writer appended the full destination name + PID + UUID and exceeded
    # MAX_PATH in feasibility-stage directories before the Solver was called.
    temporary=path.with_name('.'+uuid.uuid4().hex+'.tmp')
    with write_lock(path):
        try:
            io_path(temporary).write_text(json.dumps(clean(value),ensure_ascii=False,
                indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
            replace_file(io_path(temporary),io_path(path))
        finally:io_path(temporary).unlink(missing_ok=True)
