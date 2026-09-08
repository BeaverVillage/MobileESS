def _anchor_and_sensitivity_day(repo: Path, source: Path, background, plan, binding: FullGridBinding, day: str, cache: Path, build_sensitivity: bool=True) -> dict[str, object]:
    import numpy as np
    plan_sha = _hash_payload(plan)
    schema = 'V16_3_D1_AC_ANCHOR_SENSITIVITY_NPZ_V1'
    if cache.exists():
        try:
            existing = np.load(cache, allow_pickle=False)
            if str(existing['schema_version']) == schema and str(existing['operating_day']) == day and (str(existing['native_master_sha']) == NATIVE_MASTER_SHA) and (str(existing['plan_sha256']) == plan_sha) and (not build_sensitivity or existing['sensitivity'].shape[0] == 96):
                return _cache_record(cache, day)
        except KeyError:
            pass
    odd, adapter = _compile(source, repo, 'NATIVE')
    nodes = _node_axis(binding)
    controls = _control_axis(odd)
    branches = binding.factories[0].data.branches
    v2 = np.empty((96, len(nodes)))
    h = np.zeros((96, len(controls), len(nodes))) if build_sensitivity else np.zeros((0, 0, 0))
    taps = np.empty((96, len(REGULATORS)))
    caps = np.empty((96, len(CAPACITORS)), dtype=np.int8)
    branch_p = np.empty((96, len(branches)))
    branch_q = np.empty_like(branch_p)
    branch_i = np.empty_like(branch_p)
    root_pq = np.empty((96, 2))
    converged = []
    anchor_control = np.zeros((96, len(controls)))
    deterministic_error = 0.0
    for slot in range(96):
        _enable_native_controls(odd)
        _set_slot(odd, adapter, background, plan, slot)
        odd.Solution.SolveSnap()
        converged.append(bool(odd.Solution.Converged()))
        if not converged[-1]:
            raise RuntimeError(f'V163_ANCHOR_NONCONVERGENCE:{day}:{slot}')
        tap = _regulator_taps(odd)
        cap = _capacitor_states(odd)
        vm = _voltage_map(odd, nodes)
        v2[slot] = [vm[node] ** 2 for node in nodes]
        taps[slot] = [tap[name] for name in REGULATORS]
        caps[slot] = [cap[name][0] for name in CAPACITORS]
        for index, branch in enumerate(branches):
            branch_p[slot, index], branch_q[slot, index], branch_i[slot, index] = _terminal_phase(odd, branch.branch_id, branch.parent_bus, branch.phase)
        odd.Circuit.SetActiveElement('Transformer.reg1a')
        conductors = int(odd.CktElement.NumConductors())
        powers = list(map(float, odd.CktElement.Powers()))
        root_pq[slot] = [sum((powers[2 * i] for i in range(conductors) if i < 3)), sum((powers[2 * i + 1] for i in range(conductors) if i < 3))]
        for index, control in enumerate(controls):
            anchor_control[slot, index] = float(plan[slot][int(control[-3:-1]) - 1]) if control.startswith('aidc_') else 0.0
        if not build_sensitivity:
            continue
        _fix_controls(odd, tap, cap)
        for index, control in enumerate(controls[:12]):
            base = anchor_control[slot, index]
            delta = _perturbation(control, base)
            _apply_control(odd, control, base + delta, plan[slot])
            odd.Solution.SolveSnap()
            plus = np.array([value ** 2 for value in _voltage_map(odd, nodes).values()])
            _apply_control(odd, control, base - delta, plan[slot])
            odd.Solution.SolveSnap()
            minus = np.array([value ** 2 for value in _voltage_map(odd, nodes).values()])
            h[slot, index] = (plus - minus) / (2 * delta)
            _apply_control(odd, control, base, plan[slot])
            if slot == 0 and index == 0:
                _apply_control(odd, control, base + delta, plan[slot])
                odd.Solution.SolveSnap()
                repeat = np.array([value ** 2 for value in _voltage_map(odd, nodes).values()])
                deterministic_error = max(deterministic_error, float(np.max(np.abs(repeat - plus))))
                _apply_control(odd, control, base, plan[slot])
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, schema_version=np.asarray(schema), operating_day=np.asarray(day), native_master_sha=np.asarray(NATIVE_MASTER_SHA), plan_sha256=np.asarray(plan_sha), deterministic_repeat_max_abs_error=np.asarray(deterministic_error), node_names=np.asarray(nodes), control_names=np.asarray(controls), branch_names=np.asarray([f'{b.branch_id}::{b.phase}' for b in branches]), anchor_v_squared=v2, sensitivity=h, anchor_control=anchor_control, regulator_taps=taps, capacitor_states=caps, branch_p_kw=branch_p, branch_q_kvar=branch_q, branch_current_a=branch_i, root_pq=root_pq)
    return _cache_record(cache, day)
