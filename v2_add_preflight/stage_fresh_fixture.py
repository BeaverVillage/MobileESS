"""Independent full120 AC backend fixture; no optimized dispatch is claimed."""
import uuid
import numpy as np
from .stage_common import *
from .prestart_native import native_zero


def certify():
    from .full_common import RUN as LEGACY
    from .stage_actual import fresh_handler
    with measured('ACTUAL_FULL120_FRESH_HANDLER_FIXTURE.json') as (report,start),native_zero() as denied:
        source=LEGACY/'daily_r0/2025-05-01/INPUTS.npz'
        with np.load(source) as z:a={k:z[k] for k in z.files}
        folder=WORK/('FRESH120_FIXTURE_'+uuid.uuid4().hex[:8])
        result=fresh_handler(day_inputs(),a,None,folder)
        report.update(PASS=result['PASS'],result=result,input=record(source),
            scope='Actual adopted B0 Job/C1 arrays; two new full120 TIME engines through the production Fresh callable',
            optimized_B1_B2_B3_outcome_claimed=False,denied_attempts=denied)


if __name__=='__main__':certify()
