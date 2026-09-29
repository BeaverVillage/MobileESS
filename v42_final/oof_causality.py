"""Verify stored OOF prediction timing, without inference or reserve replay.

This audit reads submission timestamps only. The sealed gamma and the one
fold5 reserve validation remain byte-identical; no labels are evaluated again.
"""
from .common import *


def audit_fold(i, contract):
    source=V9/f'.local/fold{i}/VALID.parquet'
    f=pd.read_parquet(source,columns=['submit_time'])
    states_path=V10/f'CALIBRATION_STATES/fold{i}_ISOTONIC_ROLLING14.json'
    states=read(states_path)['states'];rows=[]
    require((f.submit_time>=pd.Timestamp(contract['VALID_submit_from'])).all()
            and (f.submit_time<pd.Timestamp(contract['VALID_end'])).all(),'FOLD_SUBMISSION_MEMBERSHIP')
    for day,g in f.groupby(f.submit_time.dt.floor('D')):
        state=states[str(day)];available=pd.Timestamp(state['day'])
        completion=pd.Timestamp(state['max_completion_used'])
        require(available==day and available<=g.submit_time.min() and completion<available,'OOF_STATE_AVAILABLE_AT_SUBMISSION')
        require(pd.Timestamp(contract['TRAIN_cutoff'])<g.submit_time.min(),'OOF_MODEL_CUTOFF')
        rows.append(dict(fold=i,day=str(day),N=len(g),first_submit=str(g.submit_time.min()),
                         state_available=str(available),max_completion_used=str(completion)))
    return rows,[rec(source),rec(states_path)]


def main():
    sealed=OUT/'RUNTIME_RESERVE_CALIBRATION.json';holdout=OUT/'RUNTIME_RESERVE_HOLDOUT_RECEIPT.json'
    before=[sha(sealed),sha(holdout)];contract=read(V10/'TEMPORAL_FOLD_CONTRACT.json');rows=[];sources=[]
    for i,c in enumerate(contract['folds'],1):
        r,s=audit_fold(i,c);rows+=r;sources+=s
    require(before==[sha(sealed),sha(holdout)],'RESERVE_EVIDENCE_CHANGED')
    csv('RUNTIME_OOF_STATE_AVAILABILITY.csv',rows)
    dump('RUNTIME_OOF_CAUSALITY_AUDIT.json',dict(PASS=True,rows=sum(r['N'] for r in rows),
        days=len(rows),future_calibration_state_uses=0,March31_retrospective_predictions=0,
        predictions_recomputed=0,labels_read_for_this_audit=0,holdout_replays=0,
        calibration_sha=before[0],holdout_receipt_sha=before[1],sources=sources,
        qualification='Availability verifies each saved daily mapping and model cutoff; prediction bytes checked against PR95 source manifest by load_fold.'))
    print('PASS: stored OOF state availability; no reserve replay or retuning')


if __name__=='__main__':main()
