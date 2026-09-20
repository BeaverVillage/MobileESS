"""One new B2 or B3-M1 search; independent budgets and selected beam output."""
import os, sys, time
from pathlib import Path


def main(request):
    from v41r4_900_namespace import verify_release, bind
    verify_release(); bind()
    import v41r4_exact_cache as cache
    from v41r4_exact_runtime import install as exact_install
    from dayahead.paper_analysis.storage import read, write_json
    from dayahead.v41.preflight import record
    data = read(request); output = Path(request).parent
    os.environ.update(IEEE123_MESS_SEARCH_ROOT=data['search_output'], IEEE123_MESS_POLICY=data['policy'])
    exact_install()
    from dayahead.v41.electrical import load
    from dayahead.v41.reserve import bind as reserve_bind
    from dayahead.v41.execution import run_m1
    from dayahead.v41r1.bounded_mess import validate
    from dayahead.v41r1.mess_search_contract import verify_search_completion
    from dayahead.v35r3 import algorithm as r3
    from dayahead.v35r3e import algorithm as r3e
    ctx = load(data['day'])
    reserve_bind(ctx, data['ML_snapshot']['path'], data['ML_snapshot']['sha256'])
    def guard(day):
        if day != data['day'] or not day.startswith('2025-05-'):raise ValueError('DAY_SCOPE')
    r3.assert_apr01_only = r3e.assert_apr01_only = guard
    from v41r4_per_mess_budget import install, CONTRACT_SHA, PATCHES
    neutral = read(output/'seed/POLICY_REFERENCE_SEED.json')['MESS']
    install(nodes=ctx.nodes, neutral=neutral)
    write_json(output/'RUNTIME_BINDING.json', dict(runtime_budget_contract_SHA=CONTRACT_SHA, patches=PATCHES))
    try:
        trajectory, result = run_m1(data['day'], data['jobs'], ctx, Path(data['search_output']))
        verify_search_completion(result, len(ctx.coefficients))
        assert result['runtime_budget_contract_SHA'] == CONTRACT_SHA
        physics, grid = validate(data['jobs'], trajectory, ctx)
        write_json(output/'BOUNDED_FLEET_INCUMBENT.json', dict(trajectory_slots=result['trajectory_slots'],
            rho=grid['rho_max'], physics=physics, grid=grid, source='NEW_RUNTIME_FINAL_RETAINED_BEAM',
            runtime_budget_contract_SHA=CONTRACT_SHA, accepted_at=time.time()))
        write_json(output/'MESS_SEARCH_COMPLETED.json', dict(status='PASS', request=record(request), result=result,
            runtime_budget_contract_SHA=CONTRACT_SHA))
    finally:
        cache.flush_all(); ctx.electrical.voltage.close(); ctx.electrical.current.close()


if __name__ == '__main__':main(sys.argv[1])
