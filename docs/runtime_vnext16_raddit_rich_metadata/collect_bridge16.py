from common16 import *
sys.path.insert(0,str(V13))
import train13

def main():
    assert read(ROOT/'RADDIT_INFORMATION_VALUE_VERDICT.json')['deployable_bridge_authorized']
    rows=[];folds=[];tails=[]
    for arm in ['R0','R15','R16-A','R16-B','R16-C']:
        fs=[];parts=[]
        for fold in range(1,6):
            folder=V13/'.local'/f'fold{fold}' if arm=='R0' else V15/'.local'/f'runtime_fold{fold}' if arm=='R15' else LOCAL/f'runtime_fold{fold}'
            name='EXPANDING_S4' if arm=='R0' else 'R2' if arm=='R15' else arm
            s=read(folder/(name+'.json'));p=pd.read_parquet(folder/(name+'.parquet'));parts.append(p)
            s.update(arm=arm,fold=fold,status='FROZEN_REFERENCE_RECOMPUTED' if arm in ['R0','R15'] else 'COMPLETED');folds.append(s.copy())
            if arm=='R16-B':
                # summarize helper expects a distribution field: NA stays explicitly unassessed afterward.
                s['proper_interval_NLL']=np.nan;s['zero_support_count']=0;s['inference_seconds']=0
            fs.append(s)
            for h in [4,8,12,24]:
                ix=p.runtime_seconds>h*3600
                tails.append(dict(arm=arm,fold=fold,hours=h,N=int(ix.sum()),Q90_coverage=float((p.loc[ix,'runtime_seconds']<=p.loc[ix,'q90']).mean()),status='COMPLETED' if arm.startswith('R16') else 'FROZEN_REFERENCE'))
        m=train13.summarize(arm,fs,parts)
        if arm=='R16-B':
            m.update(proper_interval_NLL=None,zero_support_count=None,inference_seconds=None,gate_G=False,gate_H=False,eligible=False,
                required_distribution_score='NOT_DEFINED_QUANTILE_ONLY',quantile_support_violations=0,proper_pinball_finite=True)
        m.update(status='COMPLETED' if arm.startswith('R16') else 'FROZEN_REFERENCE_RECOMPUTED',new_fit=arm.startswith('R16'))
        # No new arm can pass causal/callability gate until the independent replay runs.
        if arm.startswith('R16'):
            replay=read(ROOT/'RUNTIME_BRIDGE_REPLAY_AUDIT.json');m['gate_I'] &= replay['PASS']
            m['eligible']=all(m['gate_'+c] for c in 'ABCDEFGHI')
        rows.append(m)
    frame=pd.DataFrame(rows);base=frame.iloc[0]
    frame['delta_min_fold_vs_R0']=frame.min_fold_coverage-base.min_fold_coverage
    frame['delta_gt4h_vs_R0']=frame.gt4h_coverage-base.gt4h_coverage
    frame['pinball_relative_vs_R0']=frame.Q90_pinball/base.Q90_pinball-1
    frame['material_benefit']=((frame.delta_min_fold_vs_R0>=.05)|(frame.delta_gt4h_vs_R0>=.05))&(frame.pinball_relative_vs_R0<=.05)
    frame.to_csv(ROOT/'RUNTIME_V16_MODEL_COMPARISON.csv',index=False)
    pd.DataFrame(folds).to_csv(ROOT/'RUNTIME_V16_FOLD_METRICS.csv',index=False);pd.DataFrame(tails).to_csv(ROOT/'RUNTIME_V16_TAIL_METRICS.csv',index=False)
    eligible=frame[frame.arm.str.startswith('R16')&frame.eligible].sort_values(read(V13/'EXPERIMENT_PROTOCOL.json')['ranking'])
    chosen='NONE' if eligible.empty else eligible.iloc[0].arm
    write('RUNTIME_V16_SELECTION_FREEZE.json',dict(time=now(),status='COMPLETED',selected=chosen,TOTAL_GATE_PASS=chosen!='NONE',
        new_deployable_arm_folds=15,H0='FROZEN_R0_REFERENCE',H1='R16-A',H2='NOT_RUN_MODULES_CONDA_NOT_DEPLOYABLE',
        native_strict_success=read(ROOT/'RADDIT_INFORMATION_VALUE_VERDICT.json')['native_information_success'],
        execution_routing_correction=rec(ROOT/'EXECUTION_ROUTING_CORRECTION.json'),safety_gates_changed=False,
        material_benefit_arms=frame.loc[frame.arm.str.startswith('R16')&frame.material_benefit,'arm'].tolist(),
        REMAINING_STAGE='NOT_RUN_TOTAL_GATE_FAILURE' if chosen=='NONE' else 'AUTHORIZED_PENDING_EXECUTION',
        STAGE_C='NOT_RUN_TOTAL_GATE_FAILURE' if chosen=='NONE' else 'AUTHORIZED_PENDING_EXECUTION',
        PROVIDER='NOT_RUN_TOTAL_GATE_FAILURE' if chosen=='NONE' else 'AUTHORIZED_PENDING_EXECUTION',
        APRIL='NOT_RUN_GATE_FAILED' if chosen=='NONE' else 'AUTHORIZED_AFTER_SELECTION_FREEZE',MAY='UNOPENED',April_selection=False))
    native=read(ROOT/'RADDIT_INFORMATION_VALUE_VERDICT.json')
    new=frame[frame.arm.str.startswith('R16')]
    narrow=(new.min_fold_coverage>=.80)&(new.gt4h_coverage>=.80)&(new.gt12h_coverage>=.75)&(new.gt24h_coverage>=.65)&new.gate_A&new.gate_G&new.gate_I
    authorized=bool(new.material_benefit.any() or (native['native_information_success'] and narrow.any()))
    write('CC4_RICH_AUTHORIZATION.json',dict(time=now(),authorized=authorized,Runtime_frozen=True,
        material_runtime_arms=new.loc[new.material_benefit,'arm'].tolist(),native_strict_success=native['native_information_success'],
        narrow_runtime_arms=new.loc[narrow,'arm'].tolist(),C0='Frozen T0/B0 hourly submitted-GPUh LightGBM',future_unsubmitted_semantics_allowed=False))
    if not authorized:
        pd.DataFrame([dict(arm='C0',status='FROZEN_T0_B0_RETAINED'),dict(arm='C3',status='NOT_RUN_CC4_INFORMATION_GATE'),dict(arm='C4',status='NOT_RUN_CC4_INFORMATION_GATE')]).to_csv(ROOT/'CC4_RICH_MODEL_COMPARISON.csv',index=False)
        write('CC4_RICH_SELECTION_FREEZE.json',dict(time=now(),stage_run=False,status='NOT_RUN_CC4_INFORMATION_GATE',selected='C0',
            baseline='T0/B0 hourly submitted-GPUh LightGBM',T2_F0_promoted=False,T3_F2_promoted=False,
            individual_future_unsubmitted_semantics_used=False,April_selection=False,May_opened=False))
    print(frame[['arm','min_fold_coverage','gt4h_coverage','Q90_pinball','eligible','material_benefit']].to_string(index=False),flush=True)
    print('RUNTIME_SELECTED',chosen,'CC4_AUTHORIZED',authorized,flush=True)

if __name__=='__main__':main()
