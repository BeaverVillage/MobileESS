"""Original A1/A2 run callables with explicit current electrical parameters."""
from contextlib import contextmanager
import types
import numpy as np
from .stage_common import *
from .stage_aidc import power_bounds
from .stage_a_canary import scope


@contextmanager
def current_stage(request,m1_result=None):
    tag=request['stage']
    if tag not in ('A1','A2') or request['day']!='2025-05-01':raise ValueError('ORIGINAL_MAY01_A_STAGE_REQUIRED')
    root=Path(request['output']);adapter=root.parent/('ADAPTER_'+tag)
    if tag=='A1':
        # This frozen proof covers the full original C1 GPU box, not a B0
        # dispatch or accepted point. Fresh source Job models are still built.
        certificate=OUT/'A1_VARIABLE_GRID_INDEPENDENT_VERIFICATION.json'
        assert read(certificate)['PASS']
        from shutil import copytree
        adapter.mkdir(parents=True,exist_ok=False)
        copytree(WORK/'A1/grid',adapter/'grid')
        for path in (WORK/'A1/grid').rglob('*'):
            if path.is_file():
                target=adapter/'grid'/path.relative_to(WORK/'A1/grid')
                assert record(path)['sha256']==record(target)['sha256']
        with scope('A1',adapter_root=adapter,output_root=request['campaign_root'],grid_certificate=certificate) as source:
            yield source.run
        return
    from v44.stages import require_m1
    from .stage_origin import require_m
    require_m(m1_result)
    plan=require_m1(m1_result,request['day']);services=[f'{s}{i:02d}' for s in ('IDC','STA') for i in range(1,13)]
    mess=np.array([[plan['P_by_site'][s][t] for s in services]+[plan['Q_by_site'][s][t] for s in services] for t in range(96)])
    bundle=read(day_inputs()['files']['native']['path']);bounds,_=power_bounds(bundle)
    adapter.mkdir(parents=True,exist_ok=False);base=adapter/'A2';proof=adapter/'EVIDENCE';proof.mkdir()
    @contextmanager
    def measured(name):
        result=dict(PASS=False,stage='A2',fixed_M1_plan_sha=plan['plan_sha']);start=time.perf_counter()
        try:yield result,start
        finally:
            result['wall_seconds']=time.perf_counter()-start
            (proof/name).write_text(json.dumps(result,default=str,ensure_ascii=False,indent=2),encoding='utf-8')
    from . import stage_a_grid as grid,stage_a_verify as independent
    # Source-YY derivatives remain the same dated frozen Planning response.
    # Every M1 parameter change regenerates the static implication proof.
    builder=types.FunctionType(grid.prepare_grid.__code__,dict(grid.prepare_grid.__globals__,WORK=adapter))
    receipt=builder('A2',bounds,mess)
    verifier=types.FunctionType(independent.verify.__code__,dict(independent.verify.__globals__,WORK=adapter,measured=measured))
    verifier('A2');certificate=proof/'A2_VARIABLE_GRID_INDEPENDENT_VERIFICATION.json'
    assert read(certificate)['PASS'] and receipt['MESS_parameter_sha']==digest(mess.tolist())
    with scope('A2',mess=mess,m1_result=m1_result,adapter_root=base,output_root=request['campaign_root'],grid_certificate=certificate) as source:
        yield source.run


def run(request,budget,m1_result=None,progress=None):
    with current_stage(request,m1_result) as original:
        return original(request,budget,progress)
