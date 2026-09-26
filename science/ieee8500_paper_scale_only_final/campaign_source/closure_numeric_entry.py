"""Audit solver residuals at restoration entry; keep final acceptance strict."""
from bootstrap import *
import inspect


def bind(restore, clone, folder, optimize=None):
    import mess_grid8500
    from dayahead.v40a.grid import controls_from_trajectory
    original_adapter = restore.__globals__['adapted']
    calls = [0]

    def audit_entry(before, pcc, trajectory, context):
        # This is an admission to corrective optimization, never an acceptance.
        started = time.perf_counter()
        values = controls_from_trajectory(context.coefficients, pcc, trajectory.slots)
        maximum = -float('inf'); count = 0; witness = None
        for slot, coefficient in enumerate(context.coefficients):
            for kind, weights, constant, bound in mess_grid8500.rows(coefficient):
                residual = constant + weights @ values[slot] - (1.0 if kind == 'line' else bound)
                if not np.isfinite(residual).all():
                    raise ValueError('RESTORATION_ENTRY_NONFINITE')
                count += len(residual)
                index = int(np.argmax(residual)); value = float(residual[index])
                if value > maximum:
                    maximum = value; witness = dict(slot=slot, kind=kind, row=index, residual=value)
        admitted = maximum <= 1e-6
        report = dict(status='NUMERICAL_RESIDUAL_ADMITTED_FOR_REPAIR' if admitted else 'REJECTED',
            strict_before=before, original_MILP_feasibility_tolerance=1e-6,
            final_acceptance_tolerance_unchanged=1e-9, full_rows_checked=count,
            maximum_residual=maximum, witness=witness, seed_accepted_as_final=False,
            seconds=time.perf_counter()-started)
        save(folder / f'NUMERICAL_ENTRY_{calls[0]:02d}.json', report)
        print('RESTORATION_NUMERICAL_ENTRY', report['status'], maximum, 'rows', count, flush=True)
        if not admitted:
            raise ValueError('MF_REQUIRES_FEASIBLE_A1_M1_STATE_MATERIAL_VIOLATION')

    def adapter(fn, replacements, extra=None):
        calls[0] += 1
        original_model = fn.__globals__['_configured_model']

        def strict_model(name):
            model = original_model(name)
            model.Params.FeasibilityTol = 1e-9
            model.Params.OptimalityTol = 1e-9
            model.Params.IntFeasTol = 1e-9
            model.Params.OutputFlag = 1
            model.Params.LogFile = str(folder / f'RESTORATION_SOLVER_{calls[0]:02d}.log')
            print('RESTORATION_MODEL_BUILD_START', time.time(), flush=True)
            return model

        guard = "if before['status']!='PASS':raise ValueError('MF_REQUIRES_FEASIBLE_A1_M1_STATE')"
        changed = "if before['status']!='PASS':_audit_numeric_entry(before,pcc,m1,context)"
        updates = dict(extra or {}, _configured_model=strict_model, _audit_numeric_entry=audit_entry)
        patches = list(replacements) + [(guard, changed),
            ('optimize_started=time.perf_counter();model.optimize()',
             "print('RESTORATION_OPTIMIZE_ENTER',time.time(),flush=True);optimize_started=time.perf_counter();model.optimize()")]
        if optimize is not None:
            patches.append(('model.optimize()', '_full_separation_optimize(model)'))
            updates['_full_separation_optimize']=optimize
        result = original_adapter(fn, patches, updates)
        save(folder / f'NUMERICAL_BINDING_{calls[0]:02d}.json', dict(
            source=record(inspect.getsourcefile(fn)), adapter=record(Path(__file__)),
            replacements=patches, numerical_parameters=dict(FeasibilityTol=1e-9,OptimalityTol=1e-9,IntFeasTol=1e-9),
            objective_and_all_constraints_unchanged=True, original_termination_unchanged=True,
            final_grid_evaluator_unchanged=True, exact_AC_limits_unchanged=True))
        return result

    return clone(restore, adapted=adapter)
