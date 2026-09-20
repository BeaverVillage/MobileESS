"""Only the status/artifact writer changes; original replay/search is unchanged."""
from pathlib import Path
import traceback
import runtime
from durable_io import save, state
runtime.save = save
runtime.state = state
import full_actual
full_actual.save = save
full_actual.state = state

if __name__ == '__main__':
    try:
        save(runtime.H/'IO_REPAIR_SOURCE_SHA.json', dict(
            reason='Windows STATUS.json sharing violation in os.replace; bounded atomic-write retries only',
            files=[runtime.rec(Path(__file__)),runtime.rec(runtime.H/'durable_io.py'),runtime.rec(runtime.H/'runtime.py'),runtime.rec(runtime.H/'full_actual.py'),runtime.rec(runtime.H/'shared/qsafe_shell.py')]))
        full_actual.main()
        for record in runtime.read(runtime.H/'IO_REPAIR_SOURCE_SHA.json')['files']:
            assert runtime.sha(record['path']) == record['sha256']
    except BaseException as error:
        save(runtime.H/'ACTUAL_FAILURE.json', dict(error=repr(error), traceback=traceback.format_exc()))
        state(status='FAILED', stage='B2_ACTUAL_FAILURE')
        raise
