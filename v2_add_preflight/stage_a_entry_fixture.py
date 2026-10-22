"""Bind the production A1 factory to the exact tested source entrypoint."""
import uuid
from .stage_common import *
from .prestart_native import native_zero


def certify():
    from .stage_a_casefactory import current_stage
    from v42_may_campaign_native90 import a_stage
    with measured('A_PRODUCTION_ENTRY_BINDING.json') as (report,start),native_zero() as denied:
        root=WORK/('A_ENTRY_'+uuid.uuid4().hex[:8]);root.mkdir()
        request=dict(day='2025-05-01',arm='B1',stage='A1',output=str(root/'A1'),campaign_root=str(root),
            input_folder=str(Path(day_inputs()['files']['native']['path']).parent))
        code=a_stage.run.__code__
        with current_stage(request) as actual:
            assert actual.__code__ is code
            assert actual.__globals__['_paths'](request)[0]=='2025-05-01'
            assert callable(actual.__globals__['prepare']) and callable(actual.__globals__['_physical'])
            assert actual.__globals__['_paths'](request)[2]==(root/'A1').resolve()
        refused=False
        try:
            with current_stage(dict(request,arm='B3',stage='A2'),dict(PASS=True,fixture=True)):pass
        except ValueError as exc:
            assert str(exc)=='FINITE_M_FIXTURE_IS_NOT_A_PRODUCTION_M_PARENT';refused=True
        assert refused and not denied
        report.update(PASS=True,production_A1_factory_yields_literal_original_r043_run_code=True,
            source_entry=record(ROOT/'v42_may_campaign_native90/a_stage.py'),
            current_static_grid_copied_and_every_byte_compared_by_factory=True,
            full_actual_A1_Native0_prepare=record(OUT/'A1_VARIABLE_AIDC_FULL_NATIVE0.json'),
            full_actual_A2_Native0_prepare=record(OUT/'A2_FIXED_M1_FULL_NATIVE0.json'),
            production_A2_refuses_finite_M1_fixture=refused,accepted_A_result_or_gap_fabricated=False,
            PhaseI_pricing_integer_numerical_execution_deferred_to_campaign=True,denied_attempts=denied)


if __name__=='__main__':certify()
