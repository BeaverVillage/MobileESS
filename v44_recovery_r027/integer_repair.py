"""Restore continuous feasibility with exact fixed original integer decisions."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import inspect,linecache,textwrap
from functools import wraps
import numpy as np
from v44.common import atomic,record


def fixed_snapshot(snapshot,point):
    integer=np.asarray(snapshot.vtypes)!='C'; point=np.asarray(point)
    residual=float(np.max(abs(point[integer]-np.rint(point[integer])),initial=0))
    if residual>1e-5:raise ValueError('R027_REPAIR_REQUIRES_ORIGINAL_INTEGER_TOLERANCE')
    lower=snapshot.lower.copy(); upper=snapshot.upper.copy()
    chosen=np.rint(point[integer])
    if np.any(chosen<lower[integer]) or np.any(chosen>upper[integer]):
        raise ValueError('R027_FIXED_INTEGER_OUTSIDE_ORIGINAL_BOUNDS')
    lower[integer]=chosen;upper[integer]=chosen
    answer=replace(snapshot,lower=lower,upper=upper,vtypes=np.full(len(lower),'C'))
    answer.require()
    return answer,integer,residual


def restore(native,snapshot,point,folder):
    fixed,integer,residual=fixed_snapshot(snapshot,point)
    if residual<=1e-10:return None
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    # This is a separate solve after the original optimize has returned.
    # Use the existing shared native accountant and retain original raw files.
    before=getattr(native,'incumbent_callback',None)
    warm=getattr(native,'warm_point',None)
    native.incumbent_callback=None;native.warm_point=None
    try:rec,raw=native.solve(fixed,folder/'CONTINUOUS','INTEGER_CONTROL')
    finally:native.incumbent_callback=before;native.warm_point=warm
    from v42_a_stage_phase1.core import primal_replay
    if 'X' not in raw:raise ValueError('R027_FIXED_INTEGER_REPAIR_NO_POINT')
    repaired=np.asarray(raw['X']);replay=primal_replay(snapshot,repaired)
    exact=bool(np.array_equal(repaired[integer],np.rint(point[integer])))
    proof=dict(PASS=bool(replay['PASS'] and exact),original_snapshot=snapshot.fingerprint(),
        fixed_snapshot=fixed.fingerprint(),original_rows=replay,integer_decisions_exact=exact,
        previous_integer_residual=residual,Native_seconds=rec['native_seconds'],
        native_result=record(folder/'CONTINUOUS/NATIVE_RESULT.json'),
        shared_original_A5400_budget=True,original_raw_overwritten=False,
        physical_and_gap_revalidation_required=True,tolerances_relaxed=False)
    atomic(folder/'REPAIR_CERTIFICATE.json',proof)
    if not proof['PASS']:raise ValueError('R027_FIXED_INTEGER_ORIGINAL_REPLAY_FAILED')
    return rec,raw


def compile_run(function):
    source=textwrap.dedent(inspect.getsource(function))
    old="        if 'X' in raw:\n            validate(raw['X'], rec['objective'])"
    assert source.count(old)==1,'R027_POST_INTEGER_BOUNDARY_DRIFT'
    new=("        if 'X' in raw:\n"
         "            _repair=_r027_restore(native,typed,raw['X'],output/'EXACT_INTEGER_REPAIR')\n"
         "            if _repair is not None:\n"
         "                rec,raw=_repair;candidates.clear()\n"
         "            validate(raw['X'], rec['objective'])")
    source=source.replace(old,new)
    # Inspect-based A2 routing must see the complete adapted function body.
    filename=__file__+'.run.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(function.__globals__,_r027_restore=restore)
    exec(compile(source,filename,'exec'),ns)
    return ns[function.__name__]


@contextmanager
def install():
    from v42_may_campaign_native90 import a_stage
    base=compile_run(a_stage.run)
    from .planning_reuse import load_state,load_point,run_reused
    @wraps(base)
    def dispatch(request,budget,progress=None):
        function=run_reused(base) if request.get('planning_repair_parent') else base
        return function(request,budget,progress)
    # Keep the complete source body visible to the inherited A2 AST adapter.
    with patch.object(a_stage,'run',dispatch),patch.object(a_stage,'_r027_restore',restore,create=True),patch.object(a_stage,'_r027_load_state',load_state,create=True),patch.object(a_stage,'_r027_load_point',load_point,create=True):yield
