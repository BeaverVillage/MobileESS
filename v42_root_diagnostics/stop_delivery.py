"""Record the user stop without inventing terminal solver telemetry."""
from .common import *
from .analytics import parse_simplex

def run():
    label='BASIS_ACQUISITION_ORIGINAL'
    marker=json.loads((LOCAL/(label+'_OPTIMIZE_STARTED.json')).read_text())
    live=read('LIVE_'+label+'.json')
    points=parse_simplex((OUT/(label+'.log')).read_text(encoding='utf8'))
    assert not (LOCAL/(label+'_SOLUTION.npz')).exists()
    dump(label+'.json',dict(label=label,formulation='original',variant=None,method=2,
        status='USER_INTERRUPTED_PROCESS_TERMINATED',reason='User requested stop and PR delivery; worker PID 88568 was terminated after its command line was verified.',
        settings=marker['policy'],diagnostic_only=True,certificate_update=False,no_Start=True,
        terminal_optimal=False,objective=None,solver_runtime=None,raw_solver_BestBd=None,
        Gurobi_terminal_status=None,basis_available=False,Kappa=None,KappaExact=None,
        KappaExact_reason='No terminal optimal basis; process terminated, no final Gurobi attributes queried.',
        events=live['events'],last_sampled_callback_time=max(x['t'] for x in live['trace']),
        last_simplex_log_observation=points[-1],log_sha256=sha(OUT/(label+'.log')),
        initial_scientific_model_signature=SCIENTIFIC_SIGNATURES['original'],
        terminal_telemetry_not_available=True,solution_saved=False))
    dump(label+'_TIMELINE.json',dict(events=live['events'],status='USER_INTERRUPTED',exact_stop_runtime=None,certificate_update=False))
    table(label+'_TRAJECTORY.csv',points,['iterations','phase_objective','primal_infeasibility','dual_infeasibility','t'])
    missing=[('ROW_SCALED_METHOD1_DIAGNOSTIC',1,300,'row_scaled'),
        ('AUX_REFERENCE_METHOD1_300S',1,300,None),('AUX_ELIMINATED_METHOD1_300S',1,300,'aux_eliminated'),
        ('AUX_ELIMINATED_METHOD2_600S',2,600,'aux_eliminated'),('ISOLATION_FULL_REFERENCE_120S',1,120,None),
        ('NON_SCIENTIFIC_REMOVE_VOLTAGE_LOWER_120S',1,120,'remove_voltage'),
        ('NON_SCIENTIFIC_REMOVE_LINE_THERMAL_FACE_120S',1,120,'remove_line'),
        ('NON_SCIENTIFIC_REMOVE_CORRECTION_BINDING_120S',1,120,'remove_bindings'),
        ('NON_SCIENTIFIC_REMOVE_SOC_DYNAMICS_120S',1,120,'remove_SOC')]
    for name,method,seconds,variant in missing:
        assert not (LOCAL/(name+'_OPTIMIZE_STARTED.json')).exists()
        settings=dict(LP_POLICY,Method=method,TimeLimit=seconds)
        if method==2:settings.update(Crossover=0,PreDual=0,BarConvTol=1e-11)
        dump(name+'.json',dict(label=name,status='NOT_RUN',reason='USER_STOP',
            formulation='original',variant=variant,settings=settings,diagnostic_only=True,certificate_update=False,
            terminal_optimal=False,objective=None,solver_runtime=None,optimize_calls=0,
            NON_SCIENTIFIC_DIAGNOSTIC_ONLY=name.startswith('NON_SCIENTIFIC_')))
    completed=[f'ROOT_LP_METHOD{j}_{k}' for k in ['ORIGINAL','COMPACT'] for j in [0,1,2]]+[f'MIP_ROOT_METHOD2_{k}_300S' for k in ['ORIGINAL','COMPACT']]
    dump('USER_STOP_RECEIPT.json',dict(recorded_utc=stamp(),instruction='작업 중단하고 PR하고 정리한거 나한테줘.',
        worker_PID=88568,worker_command_verified='python -u -m v42_root_diagnostics.resume_lane',worker_terminated=True,
        exact_process_termination_time_not_captured=True,completed_arms=sorted(completed),completed_arm_count=8,
        interrupted_arm=label,never_started_arms=[x[0] for x in missing],never_started_arm_count=9,
        further_diagnostic_optimize_authorized=False,remaining_work='Post-hoc evidence organization, required regression suite, integrity checks, commit/push/Draft PR.',
        interrupted_log_sha256=sha(OUT/(label+'.log')),certificate_unchanged=True))
    dump('ROW_FAMILY_ISOLATION_ACTIVATION.json',dict(executed=False,status='NOT_RUN',reason='USER_STOP',physics_invalid_results_can_never_update_certificate=True))

if __name__=='__main__':run()
