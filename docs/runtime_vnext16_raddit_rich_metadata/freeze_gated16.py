"""Explicit unexecuted artifacts after the preregistered native information decision."""
from common16 import *

def main():
    v=read(ROOT/'RADDIT_INFORMATION_VALUE_VERDICT.json')
    assert not v['deployable_bridge_authorized'],'An authorized bridge must be executed, not marked NOT_RUN'
    assert v['program_stop_triggered'],'Only the user-defined all-conditions STOP permits this template'
    reason='NOT_RUN_NATIVE_INFORMATION_STOP' if v['program_stop_triggered'] else 'NOT_RUN_NATIVE_STRICT_SUCCESS_NOT_MET'
    baseline=read(ROOT/'R0_PR89_BASELINE_REPRODUCTION.json')['independently_recomputed_arms']
    rows=[];folds=[];tails=[]
    for name,source_arm in [('R0','R0'),('R15','R2')]:
        r=next(r for r in baseline if r['arm']==source_arm).copy();r.update(arm=name,status='FROZEN_REFERENCE_RECOMPUTED',new_fit=False,production_selected=False);rows.append(r)
        source=V13 if name=='R0' else V15
        for i in range(1,6):
            folder=source/'.local'/('fold'+str(i) if name=='R0' else 'runtime_fold'+str(i));original='EXPANDING_S4' if name=='R0' else 'R2'
            f=read(folder/(original+'.json'));f.update(arm=name,fold=i,status='FROZEN_REFERENCE_RECOMPUTED');folds.append(f)
            for h in [4,8,12,24]:tails.append(dict(arm=name,fold=i,hours=h,N=f[f'gt{h}h_N'],Q90_coverage=f[f'gt{h}h_coverage'],status='FROZEN_REFERENCE'))
    for arm in ['R16-A','R16-B','R16-C']:
        rows.append(dict(arm=arm,status=reason,new_fit=False,production_selected=False))
        for fold in range(1,6):
            folds.append(dict(arm=arm,fold=fold,status=reason))
            for h in [4,8,12,24]:tails.append(dict(arm=arm,fold=fold,hours=h,status=reason))
    pd.DataFrame(rows).to_csv(ROOT/'RUNTIME_V16_MODEL_COMPARISON.csv',index=False)
    pd.DataFrame(folds).to_csv(ROOT/'RUNTIME_V16_FOLD_METRICS.csv',index=False)
    pd.DataFrame(tails).to_csv(ROOT/'RUNTIME_V16_TAIL_METRICS.csv',index=False)
    write('RUNTIME_V16_SELECTION_FREEZE.json',dict(time=now(),status=reason,selected='NONE',TOTAL_GATE_PASS=False,
        new_deployable_fits=0,baseline='Exact V13 EXPANDING_S4',H0='FROZEN_R0_REFERENCE',H1=reason,H2='NOT_RUN_MODULES_CONDA_NOT_DEPLOYABLE',
        CatBoost_superiority_tested=False,REMAINING_STAGE='NOT_RUN_TOTAL_GATE_FAILURE',STAGE_C='NOT_RUN_TOTAL_GATE_FAILURE',
        PROVIDER='NOT_RUN_TOTAL_GATE_FAILURE',APRIL='NOT_RUN_GATE_FAILED',MAY='UNOPENED',April_selection=False,
        safety_gates_changed=False,execution_routing_corrected=True,reason='User-defined all-conditions native STOP fired; unexecuted challenger metrics stay missing.'))
    bridge=[]
    a=pd.read_csv(ROOT/'RADDIT_FIELD_AUTHORITY_AUDIT.csv')
    for _,r in a.loc[a.source.eq('Kestrel original archive')].iterrows():
        bridge.append(dict(field=r.field,information_class=r.information_class,status=reason,
            concept_source_supported=r.field in ['user','submit_line'],new_deployable_model_trained=False,
            future_receipt_required=True,namespace_parity_required=True,
            note='Inherited source concept only; no new production promotion. Mutable requests remain frozen R0 research proxies.'))
    pd.DataFrame(bridge).to_csv(ROOT/'V42_DEPLOYABLE_FIELD_BRIDGE.csv',index=False)
    pd.DataFrame([dict(arm='C0',status='FROZEN_T0_B0_RETAINED',new_fit=False),dict(arm='C3',status=reason,new_fit=False),dict(arm='C4',status=reason,new_fit=False)]).to_csv(ROOT/'CC4_RICH_MODEL_COMPARISON.csv',index=False)
    write('CC4_RICH_SELECTION_FREEZE.json',dict(time=now(),status=reason,stage_run=False,selected='C0',baseline='T0/B0 hourly submitted-GPUh LightGBM',
        T2_F0_promoted=False,T3_F2_promoted=False,individual_future_unsubmitted_semantics_used=False,
        reason='No qualifying native-to-Runtime bridge and no Runtime material benefit; exact old R0 is not a narrow miss under preregistration.',April_selection=False,May_opened=False))
    print('GATED_STAGES',reason,flush=True)

if __name__=='__main__':main()
