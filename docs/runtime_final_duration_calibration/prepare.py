"""Freeze duration-only contract before any operational VALID comparison."""
from common import *
import shutil
def main():
    assert not (ROOT/'PREREGISTRATION.json').exists(), 'Existing experiment is frozen; do not overwrite its prepared inputs.'
    old=LOCAL/'superseded_shared_reserve'
    for name in ['BASE_PRESERVATION_RECEIPT.json','COMMON_RUNTIME_POPULATION_AUDIT.json','COMMON_RUNTIME_MEMBERSHIP.csv']:
        shutil.copyfile(old/name,ROOT/name)
    shutil.copyfile(r'C:\Users\kjw39\.codex\attachments\a37bfd4c-79ba-4615-8dde-81f0659c7c62\붙여넣은 텍스트.txt',ROOT/'USER_REQUEST.txt')
    for arm in ARMS:
        for i in range(1,6):
            f=pd.read_parquet(old/'.local'/f'{arm}_fold{i}_VALID.parquet')
            # Remove GPU/node columns from the primary computational interface entirely.
            f=f[['fold','job_id','submit_time','runtime_seconds','q50','q90']]
            f.to_parquet(LOCAL/f'{arm}_fold{i}_VALID.parquet',index=False)
    audit=read(old/'CANDIDATE_SOURCE_AUDIT.json');audit['optional_references']='NOT_RUN: VALID alignment trivial, but CAL frozen output absent and would require additional semantic/neighbor pipelines; primary six candidates retained.'
    audit['new_contract']='Duration seconds only. Prior GPU-based audit preserved locally; no shared reserve calibration or scheduler replay was run.'
    write('CANDIDATE_SOURCE_AUDIT.json',audit)
    assert not (ROOT/'PREREGISTRATION.json').exists()
    folds=read(V9/'TEMPORAL_FOLD_CONTRACT.json')['folds']
    for f in folds:f.pop('maps',None)
    write('PREREGISTRATION.json',dict(time=now(),base=BASE,stage='Before CAL alpha search and any operational-duration VALID evaluation',
        prior_exposure='Raw VALID outcomes, historical published raw metrics and prior GPU-ratio audit already known. No VALID alpha grid was evaluated; frozen raw outputs are existing research evidence, not a pristine blind holdout.',
        candidates=ARMS,primary_candidates=PRIMARY,diagnostic_only=list(ARMS)[-1],optional_references='NOT_RUN',folds=folds,
        units='seconds',GPU_weighted_selection=False,formula='T_op=Q50+alpha*(Q90-Q50)',interface_name='CALIBRATED_OPERATIONAL_RUNTIME',
        alpha_grid=[j/20 for j in range(21)],nominal_reference=.90,
        alpha_selection='Among CAL coverage >=.90 choose smallest TIME_RATIO_OP, then smallest alpha. If none, maximize CAL coverage, then minimize TIME_RATIO_OP, then alpha; mark CAL_90PCT_UNATTAINABLE.',
        CAL_population='Same fold original CAL membership; exact outcomes observed by CAL boundary. All candidates use identical event rows and timestamps. No validation labels used for alpha.',
        CAL_forecasts='V9 cached raw quantiles. ROLLING14 uses original frozen causal completion-residual rule within CAL only; empty prior pool ->0, support>=200, signed additive shift then clip at zero. V13 CAL quantiles generated from frozen weights/preprocessing/current-state feature ledger, never fitted. VALID quantiles are original published frozen bytes.',
        raw_metrics=['Q50 MAE seconds/hours','Q90 coverage pooled/min-fold/GT4H/GT12H/GT24H','sum Q50/sum actual','sum Q90/sum actual'],
        zero_runtime='Retain exact-zero rows in MAE and coverage and aggregate sums; exclude from per-job division; count separately.',
        rounding='None. Continuous seconds, no scheduler-slot or GPU weighting.',
        model_selection=dict(eligibility='Primary A-E only. Pooled AND every fold operational coverage >=.90. This conservative nominal-reference rule prevents pooled success hiding a temporal collapse; it is a new duration-interface rule, not historical provider gates.',
            pareto=['min Q50_MAE_hours','max OP_coverage','max min_fold_OP_coverage','max GT12H_OP_coverage','min TIME_RATIO_OP'],
            preference=['minimum TIME_RATIO_OP','minimum Q50_MAE_hours','maximum GT12H_OP_coverage','candidate name'],none_allowed=True,
            alpha_reporting='Report five fold-specific CAL-frozen alphas, never average and misrepresent as tested fixed alpha. If NONE, selected alpha and all selected metrics null; no final deployment calibration.',
            descriptive_bands='BELOW_1P2 / BELOW_1P5 / BELOW_2P0 / ABOVE_2P0 (exact 2: AT_2P0). Bands are measured sharpness, not proof of acceptable reliability.',
            feasibility='TIME_RATIO_Q50 is exact nonnegative interpolation floor. Floor>threshold proves impossible, otherwise not ruled out, not proven. Supported deployment requires the reliability rule too.'),
        submission_assumption='Archived scheduler/request metadata treated as historical submit-observable proxy by user authorization. No immutable initial-submit receipt claim; issue predates RADDiT.',
        full_distribution='V9 zero-support defect remains; only frozen Q50/Q90 and derived durations evaluated, no full distribution promotion.',
        forbidden=['new ML training','April/May selection','May payload','RADDiT retraining','external telemetry search','CC4 changes','V42 execution','OpenDSS'],
        superseded_task='GPU-weighted shared-reserve task explicitly replaced by user correction; preliminary files preserved locally, no scheduler experiment executed.'))
    write('PREREGISTRATION_HASH.json',rec(ROOT/'PREREGISTRATION.json'))
    print('DURATION_PREREGISTERED',now(),flush=True)
if __name__=='__main__':main()
