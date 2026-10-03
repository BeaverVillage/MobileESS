"""Checkpoint resume after approved transport correction; no repeated solves."""
from .common import *
from . import worker

def completed(label,kind,method,seconds,mip=False,variant=None,crossover=None):
    p=OUT/(label+'.json')
    if not p.exists():return worker.one(label,kind,method,seconds,mip=mip,variant=variant,crossover=crossover)
    r=read(p.name)
    expected=dict(MIP_POLICY if mip else LP_POLICY,Method=method,TimeLimit=seconds)
    if not mip and method==2:expected.update(Crossover=0 if crossover is None else crossover,PreDual=0,BarConvTol=1e-11)
    assert r['settings']==expected and r['formulation']==kind and r['variant']==variant
    assert r['initial_scientific_model_signature']==SCIENTIFIC_SIGNATURES[kind]
    assert r['status'] in [gp.GRB.OPTIMAL,gp.GRB.TIME_LIMIT]
    assert (OUT/(label+'_TIMELINE.json')).exists() and (OUT/(label+'_TRAJECTORY.csv')).exists()
    assert sha(OUT/(label+'.log'))==r['log_sha256']
    print('REUSE_COMPLETED_NO_RERUN',label,r['status'],flush=True);return r

def run():
    freeze_check();phase='root_methods'
    try:
        roots=[]
        for kind in ['original','compact']:
            for method in [0,1,2]:roots.append(completed(f'ROOT_LP_METHOD{method}_{kind.upper()}',kind,method,600))
        optimal=[r['objective'] for r in roots if r['terminal_optimal']];delta=max(optimal)-min(optimal) if optimal else None
        gate=delta is not None and delta<=1e-8 and all(any(r['formulation']==k and r['terminal_optimal'] for r in roots) for k in ['original','compact'])
        dump('ROOT_METHOD_COMPARISON.json',dict(objective_equivalence_PASS=gate,maximum_optimal_objective_difference=delta,results=roots,inherited_certificate=dict(UB=UB,LB=LB,gap=(UB-LB)/UB),certificate_update=False))
        assert gate,'ROOT_OBJECTIVE_EQUIVALENCE_NOT_ESTABLISHED_STOP'
        phase='MIP_confirmation'
        for kind in ['original','compact']:completed('MIP_ROOT_METHOD2_'+kind.upper()+'_300S',kind,2,300,mip=True)
        phase='basis_scaling_projection'
        if not any(r['basis_available'] for r in roots if r['method'] in [0,1]):completed('BASIS_ACQUISITION_ORIGINAL','original',2,600,crossover=1)
        elif not (OUT/'BASIS_ACQUISITION_ORIGINAL.json').exists():dump('BASIS_ACQUISITION_ORIGINAL.json',dict(status='NOT_RUN',reason='At least one terminal optimal M0/M1 basis already available'))
        completed('ROW_SCALED_METHOD1_DIAGNOSTIC','original',1,300,variant='row_scaled')
        proof=read('AUXILIARY_ELIMINATION_PROOF.json')
        if proof['solver_prototype_PASS']:
            completed('AUX_REFERENCE_METHOD1_300S','original',1,300)
            completed('AUX_ELIMINATED_METHOD1_300S','original',1,300,variant='aux_eliminated')
            completed('AUX_ELIMINATED_METHOD2_600S','original',2,600,variant='aux_eliminated')
        else:dump('AUX_ELIMINATION_DIAGNOSTIC.json',dict(status='NOT_RUN',reason='Exact numeric prototype proof failed; no approximate substitution authorized'))
        phase='conditional_nonscientific_isolation'
        uncertain=not proof['complete_flattened_binary64_transport_PASS']
        if uncertain:
            completed('ISOLATION_FULL_REFERENCE_120S','original',1,120)
            for label,variant in [('VOLTAGE_LOWER','remove_voltage'),('LINE_THERMAL_FACE','remove_line'),('CORRECTION_BINDING','remove_bindings'),('SOC_DYNAMICS','remove_SOC')]:
                completed('NON_SCIENTIFIC_REMOVE_'+label+'_120S','original',1,120,variant=variant)
        dump('ROW_FAMILY_ISOLATION_ACTIVATION.json',dict(executed=uncertain,reason='Complete flattening lacks exact binary64 transport; partial injection projection cannot settle full response burden.',physics_invalid_results_can_never_update_certificate=True,one_source_family_removed_per_copy=True))
        print('ALL_REGISTERED_DIAGNOSTICS_COMPLETED',flush=True)
    except BaseException as exc:
        dump('STOP_POST_TRANSPORT_DIAGNOSTIC.json',dict(utc=stamp(),phase=phase,error=repr(exc),remaining_heavy_solves_stopped=True,certificate_unchanged=True));raise

if __name__=='__main__':run()
