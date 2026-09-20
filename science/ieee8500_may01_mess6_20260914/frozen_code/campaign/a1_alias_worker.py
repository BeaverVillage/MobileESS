"""Original A1 worker with a same-file seed-path adapter only."""
import traceback
import a1_worker as worker
from a1_seed_alias_binding import install
if __name__=='__main__':
    try:
        install()
        worker.main()
    except BaseException as error:
        worker.save(worker.H/'A1_WORKER_FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc()))
        raise
