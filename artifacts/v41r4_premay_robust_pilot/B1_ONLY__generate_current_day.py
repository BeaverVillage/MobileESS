def _generate_current_day(repo: Path, source: Path, artifacts: Path, day: str, context) -> dict[str, object]:
    reference, _vintage, background, binding, voltage_cache, _authority = context
    data = np.load(voltage_cache, allow_pickle=False)
    controls = tuple(map(str, data['control_names']))
    branches = tuple(binding.factories[0].data.branches)
    if len(controls) != CONTROL_AXIS_SIZE or len(branches) != BRANCH_AXIS_SIZE:
        raise RuntimeError('V163_CORR_AXIS_SIZE_MISMATCH')
    odd, adapter = _compile(source, repo, 'NATIVE')
    ratings, rating_rows = _branch_ratings(odd, binding)
    sensitivity = np.zeros((96, CONTROL_AXIS_SIZE, BRANCH_AXIS_SIZE), dtype=np.float64)
    anchor_pu = np.empty((96, BRANCH_AXIS_SIZE), dtype=np.float64)
    anchor_sampler_error = 0.0
    repeat_error = 0.0
    solve_count = 0
    for slot in range(96):
        taps = {name: float(data['regulator_taps'][slot, i]) for i, name in enumerate(REGULATORS)}
        caps = {name: [int(data['capacitor_states'][slot, i])] for i, name in enumerate(CAPACITORS)}
        anchor = np.asarray(data['anchor_control'][slot], dtype=float)
        _set_slot(odd, adapter, background, reference['plan_kw_96x12'], slot)
        _fix_controls(odd, taps, caps)
        odd.Solution.SolveSnap()
        solve_count += 1
        if not bool(odd.Solution.Converged()):
            raise RuntimeError(f'V163_CORR_ANCHOR_NONCONVERGENCE:{day}:{slot}')
        indices, coefficients = _current_sampler(odd, branches)
        sampled = _sample_currents(odd, indices, coefficients)
        anchor_sampler_error = max(anchor_sampler_error, float(np.max(np.abs(sampled - np.asarray(data['branch_current_a'][slot], dtype=float)))))
        anchor_pu[slot] = sampled / ratings
        for control_index, control in enumerate(controls[:12]):
            base = float(anchor[control_index])
            step = _perturbation(control, base)
            _apply_control(odd, control, base + step, reference['plan_kw_96x12'][slot])
            odd.Solution.SolveSnap()
            solve_count += 1
            if not bool(odd.Solution.Converged()):
                raise RuntimeError(f'V163_CORR_PLUS_NONCONVERGENCE:{day}:{slot}:{control}')
            plus = _sample_currents(odd, indices, coefficients) / ratings
            _apply_control(odd, control, base - step, reference['plan_kw_96x12'][slot])
            odd.Solution.SolveSnap()
            solve_count += 1
            if not bool(odd.Solution.Converged()):
                raise RuntimeError(f'V163_CORR_MINUS_NONCONVERGENCE:{day}:{slot}:{control}')
            minus = _sample_currents(odd, indices, coefficients) / ratings
            sensitivity[slot, control_index] = (plus - minus) / (2.0 * step)
            _apply_control(odd, control, base, reference['plan_kw_96x12'][slot])
            if slot == 0 and control_index == 0:
                _apply_control(odd, control, base + step, reference['plan_kw_96x12'][slot])
                odd.Solution.SolveSnap()
                solve_count += 1
                repeat = _sample_currents(odd, indices, coefficients) / ratings
                repeat_error = float(np.max(np.abs(repeat - plus)))
                _apply_control(odd, control, base, reference['plan_kw_96x12'][slot])
    if anchor_sampler_error > YPRIM_DIRECT_CURRENT_TOLERANCE_A:
        raise RuntimeError(f'V163_CORR_YPRIM_CURRENT_MISMATCH:{day}:{anchor_sampler_error}')
    target = _current_cache_path(artifacts, day)
    target.parent.mkdir(parents=True, exist_ok=True)
    coefficient_sha = hashlib.sha256(sensitivity.tobytes()).hexdigest()
    np.savez_compressed(target, schema=np.asarray(CURRENT_CACHE_SCHEMA), operating_day=np.asarray(day), source_voltage_cache_sha256=np.asarray(sha256_file(voltage_cache)), native_master_sha256=np.asarray(NATIVE_MASTER_SHA), branch_names=np.asarray(data['branch_names']), control_names=np.asarray(controls), rating_a=ratings, anchor_current_loading_pu=anchor_pu, current_sensitivity_pu_per_control=sensitivity, coefficient_sha256=np.asarray(coefficient_sha), deterministic_repeat_max_abs_error_pu=np.asarray(repeat_error), anchor_yprim_vs_direct_max_abs_error_a=np.asarray(anchor_sampler_error))
    return {'operating_day': day, 'path': str(target.resolve()), 'sha256': sha256_file(target), 'bytes': target.stat().st_size, 'coefficient_sha256': coefficient_sha, 'anchor_solve_count': 96, 'central_difference_solve_count': 96 * 60 * 2, 'determinism_repeat_solve_count': 1, 'OpenDSS_solve_count': solve_count, 'anchor_yprim_vs_direct_max_abs_error_a': anchor_sampler_error, 'deterministic_repeat_max_abs_error_pu': repeat_error, 'rating_side_rows': rating_rows}
