"""Pure live readers for independent Fresh; all solves and measurements remain."""
from contextlib import contextmanager,ExitStack
from unittest.mock import patch


@contextmanager
def live_fresh_scope(oracle):
    if not getattr(oracle,'_independent_fresh',False):
        raise PermissionError('R020_INDEPENDENT_FRESH_SCOPE_REQUIRED')
    from v44.svr12 import scope
    from v44.svr11_ac import SVR11CurrentAC
    from .current_ac_performance import direct_reader,live_properties,ratings_reader,state_reader
    from .property_metadata import equipment_reader
    from .class_metadata import ClassPropertySchema
    schema=ClassPropertySchema()
    with scope():
        from v42_regcontrol import authority
        import v42_voltage_control.integration as integration
        import v42_voltage_control.svr as svr
        source=authority.source()
        reader=lambda engine:live_properties(engine,schema)
        before=dict(oracle.performance)
        with ExitStack() as stack:
            stack.enter_context(patch.object(integration,'_equipment',equipment_reader(integration._equipment)))
            stack.enter_context(patch.dict(source,inventory=direct_reader(source['inventory'],2,reader)))
            stack.enter_context(patch.object(svr,'_properties',direct_reader(svr._properties,1,reader)))
            stack.enter_context(patch.object(SVR11CurrentAC,'_state',state_reader(SVR11CurrentAC._state)))
            stack.enter_context(patch.object(integration.PhysicalScenario,'_ratings',ratings_reader(integration.PhysicalScenario._ratings)))
            # Keep original SeriesSVRCollection.measure, measure_full_network,
            # persist and every TIME SolveSnap. No bank/history copy/reuse.
            try:
                yield
            finally:
                for key in ('verified_history_reuses','legacy_branch_measurement_reuses'):
                    if oracle.performance.get(key,0)!=before.get(key,0):
                        raise ValueError('R020_FRESH_HISTORY_MEASUREMENT_REUSED:'+key)
                oracle._r020_fresh_live_name_reads=getattr(oracle,'_r020_fresh_live_name_reads',0)+schema.reads
                oracle._r020_fresh_schema_hits=getattr(oracle,'_r020_fresh_schema_hits',0)+schema.hits
