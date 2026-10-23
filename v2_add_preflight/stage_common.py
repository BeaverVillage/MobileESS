"""May01 stage integration; append evidence without altering sealed M1 artifacts."""
from contextlib import contextmanager
from pathlib import Path
import json, time, threading, traceback
import psutil
from .static_common import ROOT, OUT, RUN, SOURCE, INITIAL, read, record, digest, guard as preparation_guard, resources
from .stage_resources import current,OFFICIAL,check_memory

WORK = RUN / 'stage_integration'


def guard(start,wall=7200):
    if current().phase==OFFICIAL.phase:
        # Official Native Runtime budgets are enforced by the source ledger.
        # Native0 memory and preparation wall limits do not apply there.
        return check_memory()
    return preparation_guard(start,wall)

def put(name, value):
    OUT.mkdir(exist_ok=True)
    p=OUT/name; tmp=p.with_suffix(p.suffix+'.new')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    tmp.replace(p)
    return value

@contextmanager
def measured(name):
    resources(); WORK.mkdir(exist_ok=True)
    from .stage_campaign import source_files
    entered_sources=source_files()
    start=time.perf_counter(); done=threading.Event(); proc=psutil.Process(); peak=[proc.memory_info().rss]
    def sample():
        while not done.wait(.1): peak[0]=max(peak[0],proc.memory_info().rss)
    th=threading.Thread(target=sample,daemon=True); th.start()
    report=dict(PASS=False,official_campaign_executed=False,Native_optimize_calls=0,Native_presolve_calls=0)
    try: yield report, start
    except BaseException as error:
        report.update(error=repr(error),traceback=traceback.format_exc()); raise
    finally:
        done.set();th.join(1)
        report.update(wall_seconds=time.perf_counter()-start,peak_RSS_bytes=max(peak[0],getattr(proc.memory_info(),'peak_wset',0)),
            system_available_bytes=psutil.virtual_memory().available,process_commit_bytes=proc.memory_info().vms,
            producer=record(ROOT/'v2_add_preflight'/Path(__import__('sys').modules[__name__].__file__).name))
        report['validation_source_files']=entered_sources
        report['validation_source_snapshot_unchanged']=source_files()==entered_sources
        if not report['validation_source_snapshot_unchanged']:
            report.update(PASS=False,source_snapshot_error='VALIDATION_CODE_OR_AUTHORITY_CHANGED_DURING_RUN')
        put(name,report)

def day_inputs():
    row=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    assert row['day']=='2025-05-01'
    return row
