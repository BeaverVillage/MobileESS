from core import *
def main():
    z=np.load(ROOT/'TARGETS.npz');m={t:pd.Series(pd.to_datetime(z['maturity_'+t].max(1),utc=True)) for t in ['T0','T1','T2','T3']}
    np.testing.assert_array_equal(m['T2'],m['T3']);rows=[]
    for i in OOS:
        base=set(member(i,m['T0']))
        for t in m:
            tr=set(member(i,m[t]));rows.append(dict(day=DAYS[i],role=L.split.iloc[i],target=t,training_days=len(tr),T0_training_days=len(base),extra_vs_T0=len(tr-base),deferred_vs_T0=len(base-tr),latest_training_maturity=str(m[t].iloc[sorted(tr)].max())))
    csv('TARGET_MATURITY_MEMBERSHIP_DIFFERENCES.csv',rows)
    write('TARGET_MATURITY_AUDIT.json',dict(T2_T3_identical_maturity=True,TRAIN_threshold_labels_available_before_first_DEV={t:bool((m[t].iloc[TRAIN]<ISS.iloc[DEV[0]]).all()) for t in m},CAL_final_offset_labels_available_before_first_evaluation={t:int((m[t].iloc[CAL]<ISS.iloc[role_ids('EXPOSED_EVALUATION')[0]]).sum()) for t in m},note='Target comparison keeps all original roles, but target-specific outcome maturity can defer historical labels. T2/T3 use identical training-day membership; resolution comparison is not confounded by maturity membership.'))
    print(pd.DataFrame(rows).groupby('target').deferred_vs_T0.agg(['mean','max']).to_string())
if __name__=='__main__':main()
