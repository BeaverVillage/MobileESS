"""Real full-dated B0 event handler and independent execution IO checks.

No campaign coordinator, approval, OS peer lease or solver is invoked. The
only substituted current() is this explicit Native0 fixture authority.
"""
from unittest.mock import patch
import uuid,copy
import numpy as np
from .stage_common import *
from .prestart_native import native_zero


def certify():
    from . import stage_handlers as handlers
    from .stage_reference import prepare
    from .stage_checkpoint import seal,restore
    from .prestart_execution import owned_lock
    from .stage_campaign import validate
    from .full_common import RUN as LEGACY
    with measured('PRODUCTION_HANDLER_FINITE_IO_FIXTURE.json') as (report,start),native_zero() as denied:
        root=WORK/('HANDLER_FIXTURE_'+uuid.uuid4().hex[:8]);root.mkdir()
        reference=root/'REFERENCE';prepare(reference)
        parent=dict(REFERENCE=dict(PASS=True,AIDC_reference=record(reference/'AIDC_REFERENCE.json')))
        request=dict(day='2025-05-01',arm='B0',stage='ACTUAL',output=str(root/'ACTUAL'))
        with patch.object(handlers,'current',lambda:dict(explicit_Native0_fixture=True)):
            result=handlers.actual(request,parent)
        validate('ACTUAL',result)
        with np.load(result['physical']['path']) as a,np.load(LEGACY/'daily_r0/2025-05-01/INPUTS.npz') as baseline:
            errors={k:float(np.max(abs(a[k]-baseline['ACTUAL_AIDC_'+k+'_kw' if k=='P' else 'ACTUAL_AIDC_Q_kvar']))) for k in ('P','Q')}
        assert max(errors.values())<1e-7
        identity=dict(day='2025-05-01',arm='B0',stage='ACTUAL',fixture=True)
        path=root/'CHECKPOINT.json';files=[result['physical'],result['events']]
        seal(path,identity,result,files);assert restore(path,identity)==result
        rejected=[]
        bad=dict(identity,day='2025-05-02')
        try:restore(path,bad)
        except ValueError:rejected.append('cross_date_checkpoint')
        original=path.read_bytes();value=read(path);value['result']['Native_seconds']=900.
        path.write_text(json.dumps(value),encoding='utf-8')
        try:restore(path,identity)
        except ValueError:rejected.append('tampered_result')
        path.write_bytes(original)
        sentinel=root/'FILE.txt';sentinel.write_text('original',encoding='utf-8')
        seal(root/'FILE_CHECKPOINT.json',identity,result,[record(sentinel)])
        sentinel.write_text('changed',encoding='utf-8')
        try:restore(root/'FILE_CHECKPOINT.json',identity)
        except ValueError:rejected.append('tampered_artifact')
        with owned_lock(root/'LOCK'):
            try:
                with owned_lock(root/'LOCK'):raise AssertionError('DUPLICATE_OS_LOCK_ADMITTED')
            except RuntimeError:rejected.append('duplicate_OS_worker')
        for stage,value in [('A1',dict(PASS=True)),('A2',dict(PASS=True)),('M1',dict(PASS=True)),('FRESH',dict(PASS=True))]:
            try:validate(stage,value)
            except (ValueError,KeyError):rejected.append('incomplete_'+stage)
        assert len(rejected)==8
        report.update(PASS=True,real_full2498_job_B0_Actual120_handler_executed=True,
            Native0_fixture_not_official_campaign=True,source_B0_C1_PQ_max_error=errors,
            result=result,checkpoint_roundtrip=True,negative_admission_rejections=rejected,
            source_controller_and_work_validator_called=True,external_worker_locks_acquired=False,
            no_fabricated_A_or_M_optimized_parent=True,denied_attempts=denied)


if __name__=='__main__':certify()
