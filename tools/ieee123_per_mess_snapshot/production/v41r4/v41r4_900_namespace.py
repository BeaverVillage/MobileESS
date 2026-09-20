"""Bind new decisions and Actual artifacts to a clean namespace."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4'
RUN = ROOT/'frozen_artifacts/v41r4_may/per_mess_900_v1'
OUT = RUN/'audit'
ACTUAL = ROOT/'frozen_artifacts/v41r4_actual_per_mess_900_v1'
OLD_ACTUAL = ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1'
LOGS = ROOT/'logs/v41r4_may/per_mess_900_v1'


def bind():
    import v41r4_loop_runtime as loop
    loop.MAY_RUN, loop.MAY_OUT, loop.LOGS = RUN, OUT, LOGS
    import v41r4_loop_worker as worker
    worker.MAY_RUN, worker.MAY_OUT = RUN, OUT
    worker.retained = lambda *a, **k:None  # B2/B3 never reuse historical decisions.
    import mission_loop_archive as archive
    original = archive.check_path
    def check_path(file, root):
        from fast_prepare import read, record
        relative = file.relative_to(root)
        if '..' in relative.parts:raise ValueError('ARCHIVE_PATH_TRAVERSAL')
        if file.resolve().is_relative_to(root.resolve()):return
        day, policy = root.relative_to(RUN).parts
        assert policy in ('B0','B1') and relative.parts[0] == 'dayahead'
        reuse = read(OUT/day/f'REUSED_DA_PRODUCER_{policy}.json')
        assert record(reuse['source']['path']) == reuse['source']
        target = (OLD/day/policy/'dayahead').resolve()
        assert Path(reuse['source']['path']).parent.resolve() == target
        assert (root/'dayahead').resolve() == target
        file.resolve().relative_to(target)
        assert read(reuse['source']['path'])['science'] == reuse['science']
    archive.MAY_RUN, archive.MAY_OUT = RUN, OUT
    archive.check_path = check_path
    # Bind aliases imported before or after this function identically.
    for name in ('v41r4_report', 'v41r4_readback_v2', 'v41r4_b3_equivalent'):
        module = __import__(name)
        module.MAY_RUN, module.MAY_OUT = RUN, OUT
    return loop


def bind_actual(final):
    from v41r4_loop_budget import adapted
    def load_current_actual():
        sys.path.insert(0, str(ACTUAL))
        import binding
        assert Path(binding.__file__).parent == ACTUAL
        binding.RUN = binding.common.RUN = RUN
        binding.common.protect = adapted(binding.common.protect,
            [('p=Path(os.path.abspath(os.fsdecode(p)))', 'p=Path(os.path.abspath(os.fsdecode(p))).resolve()')],
            dict(OUT=ROOT.parent.resolve()))
        import actual_worker as current
        import input_adapter, robust_search, qsafe
        current.RUN = input_adapter.RUN = current.frozen.RUN = RUN
        current.namespace['RUN'] = RUN
        current.input_for = adapted(current.input_for,
            [("if not p.exists() and (old/'READY.json').exists():", "if policy in ('B0','B1') and not p.exists() and (old/'READY.json').exists():")])
        current.namespace['input_for'] = current.input_for
        current.main = adapted(current.main,
            [('        if old_b.exists():', "        if policy in ('B0','B1') and old_b.exists():")])
        sys.path.insert(0, str(ROOT/'tools/qsafe_v2_shell'))
        from activate import activate
        proof = activate(robust_search, current.frozen)
        current.namespace['run_qsafe'] = robust_search.run_qsafe
        return current, proof, ACTUAL
    final.load_current_actual = load_current_actual


def verify_release():
    from fast_prepare import read, record
    from v41r4_per_mess_budget import CONTRACT_SHA
    gate = read(OUT/'IEEE123_MESS_PER_VEHICLE_15MIN_BUDGET_PASS.json')
    assert gate['status'] == 'IEEE123_MESS_PER_VEHICLE_15MIN_BUDGET_PASS'
    assert gate['runtime_budget_contract_SHA'] == CONTRACT_SHA
    for f in gate['runtime_files']: assert record(f['path']) == f
    return gate
