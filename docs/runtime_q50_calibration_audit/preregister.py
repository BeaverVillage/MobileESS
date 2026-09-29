from common import *
import shutil,subprocess
def main():
    assert not (ROOT/'PREREGISTRATION.json').exists()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO).decode().strip()==BASE
    LOCAL.mkdir(exist_ok=True)
    shutil.copyfile(r'C:\Users\kjw39\.codex\attachments\1304061e-18e7-42ef-afc9-5050e82884b7\붙여넣은 텍스트.txt',ROOT/'USER_REQUEST.txt')
    write('PREREGISTRATION.json',dict(time=now(),base=BASE,candidates=ARMS,primary_question=PRIMARY,
        phase='Before computing new Q50 coverage. PR94 raw MAE/time/Q90 and ratio medians already known.',
        population='Exactly PR94 230237 VALID jobs; all six frozen Q50/Q90 arrays; no CAL or inference, no training.',
        primary_metrics=['Q50 MAE hours','P(actual<=Q50)','sum(Q50 seconds)/sum(actual seconds)'],
        coverage_target=.50,calibration_error='abs(coverage-.50), descriptive only; no numerical PASS threshold',
        temporal='Five original chronological folds; population standard deviation ddof=0. Worst median calibration is largest abs(C50-.50), not automatically smallest coverage. Report min and max too.',
        bucket_intervals='(0,900],(900,3600],(3600,14400],(14400,43200],(43200,86400],(86400,infinity); cumulative actual>4h,>12h,>24h. Exact-zero rows separately.',
        bucket_interpretation='Actual-runtime strata are outcome-conditioned diagnostics, not predictor inputs or conditional-median calibration tests. Do not require each outcome stratum to have 50% coverage.',
        zero_handling='1290 zero-runtime rows included in global/fold MAE, coverage and aggregate sums. Excluded from per-job division. Zero-only aggregate ratio undefined/null.',
        ratios='T>0 only; Q10/Q25/median/Q75/Q90/Q95 linear empirical quantiles. Mean diagnostic only, not primary.',
        pareto_views=dict(core=['min Q50 MAE','min abs(pooled C50-.50)','min abs(time ratio-1)'],stability_additions=['min maximum fold abs(C50-.50)','min std fold C50'],
            reason='Distance from time ratio1 characterizes balanced time totals, not a scaling target; low ratios are not automatically preferred.'),
        decision='Qualitative comparative review of error, median calibration, time burden, temporal behavior and tail underprediction. Only primary candidate or NONE; no automatic Pareto promotion, no post-hoc numerical PASS threshold. Reserve feasibility is untested.',
        architecture='Planning: total-Q50 nominal plus separately designed reserve. Actual: observed RUNNING gang stays occupied until completion; capacity check before PENDING start; no duplicate reserve. Same provider after known or D-day job submits; no individual predictor before unknown submission.',
        boundaries=['PR94 NONE/alpha-null remains unchanged','no reserve/headroom design','no new model or conditional remaining','no GPU weighting','no pinball decision','no April/May','no CC4/V42/canary/OpenDSS execution']))
    write('PREREGISTRATION_HASH.json',rec(ROOT/'PREREGISTRATION.json'))
    write('IMPLEMENTATION_FREEZE.json',dict(time=now(),stage='Before new Q50 metrics',files=[rec(ROOT/p) for p in ['common.py','audit.py']]))
    print('PREREGISTERED',now(),flush=True)
if __name__=='__main__':main()
