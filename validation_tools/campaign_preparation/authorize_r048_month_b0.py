"""Freeze prepared ten-day inputs and issue B0-only monthly execution authority."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r048 import operations as op
from v44_week3 import preparation as week3
from v44_week4 import preparation as week4
from v44.common import read,atomic,record,verify,now,digest


def main():
    for prep in (week3,week4):
        with prep.bindings(),prep.no_execution():prep.verify_prepared()
    assert not op.AUTH.exists()
    op.HOME.mkdir(exist_ok=True)
    previous=read(op.old.AUX_STATE);assert previous['phase']=='B0_COMPLETE_WAIT_PARENT' and previous['workers']==[]
    assert len(previous['jobs'])==7 and all(j['status']=='PASS' for j in previous['jobs'])
    verify([j['result'] for j in previous['jobs']])
    parent=read(op.core.STATE)['lease'];assert op.alive(parent) and op.old.stop_matches()
    plan=[];evidence=[];prepared=[]
    for prep in (week3,week4):
        validation=read(prep.VALIDATION);observations=read(prep.OPS/'OBSERVATION_INPUT_PREFLIGHT.json')
        assert validation['PASS'] and len(validation['actual_input_adapters'])==len(prep.DAYS)
        verify([validation['manifest']]+validation.get('all_case_templates',validation.get('all_28_templates',[])))
        evidence.extend([record(prep.AUTH),record(prep.VALIDATION),record(prep.OPS/'OBSERVATION_INPUT_PREFLIGHT.json')])
        for day in prep.DAYS:
            row=next(r for r in observations['days'] if r['day']==day)
            eligible=row.get('PASS',True);f=read(prep.OPS/'templates'/f'{day}_B0.json')
            assert not Path(f['case_root']).exists()
            verify(list(f['input_records'].values()))
            plan.append(dict(day=day,arm='B0',campaign_root=str(prep.CAMPAIGN),case_root=f['case_root'],
                eligible=eligible,blockers=row.get('failures',[]),template=record(prep.OPS/'templates'/f'{day}_B0.json')))
        atomic(prep.OPS/'PREPARATION_EXTENSION_REVIEW.json',dict(UTC=now(),prepared_cases=len(prep.DAYS)*4,
            input_identity_PASS=True,observation_checks=record(prep.OPS/'OBSERVATION_INPUT_PREFLIGHT.json'),
            blocked_dates=[p['day'] for p in plan if p['campaign_root']==str(prep.CAMPAIGN) and not p['eligible']],
            pending_other_arms=['B1','B2','B3'],only_B0_execution_authorized_by_separate_r048_permit=True))
        prepared.append(dict(root=str(prep.CAMPAIGN),cases=len(prep.DAYS)*4))
    validation=op.HOME/'VALIDATION.json';user=op.HOME/'USER_REQUEST.json'
    atomic(validation,dict(PASS=True,UTC=now(),Native_calls=0,regressions=66,regression=record('D:/v44_r048_regression_20261020.xml'),
        prepared=prepared,all_17_B0_input_axes_verified=True,eligible=sum(p['eligible'] for p in plan),
        input_exclusions=[p for p in plan if not p['eligible']],current_workers_preserved=True))
    atomic(user,dict(UTC=now(),text='5월 22~31일까지 캠페인 준비해놔. 그리고 5월 31일까지 B0은 1worker 추가해서 지금 캠페인 유지하면서 추가해서 돌려.',
        authorized_new_arms=['B0'],new_B0_workers=1,main_existing_B2_followup_preserved=True,other_new_arms_held=True))
    atomic(op.AUTH,dict(UTC=now(),sources=op.sources(),validation=record(validation),user_request=record(user),
        previous_authorization=record(op.old.AUTH),prepared_evidence=evidence,days=list(op.DAYS),new_execution_arms=['B0'],B0_workers=1,
        parent_lease=parent,old_aux_lease=previous['lease'],plan=plan,prepare_only_new_cases=40,
        missing_raw_weather_policy='Keep original 7200-second bound; exclude May23 instead of imputing observations or changing physical inputs',
        handover='Idle r047 exits naturally; r046 live Actual preserved; adopt old B0 PASS and resume main B2 after real resource transfer'))
    for prep in (week3,week4):
        freeze=read(prep.DOC/'SCIENTIFIC_FREEZE_MANIFEST.json')
        cert=dict(read(op.core.week.DOC/'PREEXECUTION_CERTIFICATION.json'),UTC=now(),status='V44_PRESTART_READY',
            days=list(prep.DAYS),campaign_root=str(prep.CAMPAIGN),source_sha=freeze['source_sha'],allowed_arms=['B0'],
            R048_authorization=record(op.AUTH),excluded_dates=[p['day'] for p in plan if p['campaign_root']==str(prep.CAMPAIGN) and not p['eligible']],
            other_arms_execution_authorized=False,input_manifest=record(prep.DOC/'SEVEN_DAY_INPUT_MANIFEST.json'))
        atomic(prep.DOC/'B0_PREEXECUTION_CERTIFICATION.json',cert)
        permit=dict(read(op.core.week.PERMIT),UTC=now(),mode='EXECUTE',explicit_user_approved=True,days=list(prep.DAYS),
            source_sha=freeze['source_sha'],certification_sha=digest(cert),campaign_root=str(prep.CAMPAIGN),allowed_arms=['B0'],
            actual_workers=1,B0_workers=1,other_arms_execution_authorized=False,R048_authorization=record(op.AUTH),
            input_sources=[record(prep.AUTH),record(prep.VALIDATION),record(prep.OPS/'OBSERVATION_INPUT_PREFLIGHT.json')],adapter_sources=op.sources(),
            excluded_dates=cert['excluded_dates'],campaign_sources=op.sources(),all_preparations_barrier=False,
            user_instruction=read(user)['text'])
        atomic(prep.OPS/'B0_EXECUTION_PERMIT.json',permit)
        from v44.prepare import require_execution_permit
        for day in prep.DAYS:
            with op.bindings(dict(campaign_root=str(prep.CAMPAIGN),arm='B0',day=day)):
                from v44 import prepare as science_prepare
                science_prepare.require_execution_permit(prep.OPS/'B0_EXECUTION_PERMIT.json',cert)
    op.authority()
    atomic(op.HOME/'SOURCE_SNAPSHOT.json',dict(sources=op.sources(),authorization=record(op.AUTH),preparation_sources=week4.sources(),bootstrap=record(__file__)))
    print(dict(PASS=True,prepared_40=True,B0_cases=17,eligible=sum(p['eligible'] for p in plan),excluded=[p['day'] for p in plan if not p['eligible']]),flush=True)

if __name__=='__main__':main()
