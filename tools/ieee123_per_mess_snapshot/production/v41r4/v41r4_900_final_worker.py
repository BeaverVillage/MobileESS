"""Frozen final pipeline with a new MESS runtime and isolated result paths."""
import os, sys
from pathlib import Path


def main(day, phase):
    from v41r4_900_namespace import bind, bind_actual, verify_release, RUN, OUT
    if not phase.startswith('CHECK_'):verify_release()
    bind()
    import v41r4_exact_runtime as exact_runtime
    import v41r4_exact_final_worker as exact_final
    import v41r4_resited_final_worker as final
    from v41r4_loop_budget import adapted
    from v41r4_per_mess_budget import CONTRACT_SHA
    exact_runtime.launch_request = adapted(exact_runtime.launch_request, [
        ("search=c.ROOT/'mess_cache'/day/policy/'search'", "search=NEW_RUN/day/policy/'search'"),
        ("'v41r4_exact_mess_worker'", "'v41r4_900_mess_worker'")], dict(NEW_RUN=RUN))
    # The original wrapper is resolved through this module at configuration time.
    prior_wrap = exact_final.wrap_bounded
    def wrap_bounded(fn):
        run = prior_wrap(fn)
        def call(day, jobs, context, output):
            trajectory, result = run(day, jobs, context, output)
            from dayahead.paper_analysis.storage import write_json
            result.update(runtime_budget_contract_SHA=CONTRACT_SHA,
                algorithm='INHERITED_MESS_SEARCH_PER_DEPTH_900S_SOFT_WALL_CLOCK',
                termination='ALL_FOUR_DEPTHS_COMPLETED_UNDER_SOFT_BUDGET',
                MESS_scientific_semantics='PHYSICS_RANKING_UNCHANGED_RUNTIME_BUDGET_UPDATED')
            write_json(Path(output)/'M1_RESULT.json', result)
            return trajectory, result
        return call
    exact_final.wrap_bounded = wrap_bounded
    bind_actual(final)
    if phase.startswith('CHECK_'):
        import gurobipy as gp
        gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(AssertionError('PRECHECK_OPTIMIZATION_FORBIDDEN'))
        exact_runtime.install()
        if phase=='CHECK_ACTUAL':final.load_current_actual()
        else:exact_final.configure(day,phase.split('_')[1])
        from dayahead.paper_analysis.storage import write_json
        write_json(ROOT_PARENT/'manifests/per_mess_900s'/f'{phase}_PASS.json',dict(status='PASS',day=day,phase=phase,optimizer_calls=0))
        print('CONFIGURE_PRECHECK_PASS',phase,flush=True)
        return
    exact_final.main(day, phase)
    from dayahead.paper_analysis.storage import read, write_json
    path=OUT/day/f'PHASE_{phase}.json'; value=read(path)
    value['runtime_budget_contract_SHA']=CONTRACT_SHA
    write_json(path,value)


ROOT_PARENT=Path(__file__).resolve().parent.parent
if __name__ == '__main__':main(sys.argv[1], sys.argv[2])
