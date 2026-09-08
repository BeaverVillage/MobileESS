"""One isolated phase. All four DayAhead freezes precede any Actual input."""
from fast_prepare import *
import os,sys,time,traceback
from v41r4_runtime import MAY_RUN,MAY_OUT,physics,configure,prepare_ranking,restoration

def main(day,phase):
    from dayahead.v40h.identity import verify_manifest
    from v41r4_report import accept_dayahead,accept_actual
    release=read(MAY_OUT/'MAY_CAMPAIGN_RELEASE.json')
    assert release['status']=='FROZEN' and release['alpha_BG']==1.15 and day in release['days']
    verify_manifest(release['source'])
    receipt=MAY_OUT/day/f'PHASE_{phase}.json';assert not receipt.exists(),'PRESERVE_EXISTING_PHASE'
    start=time.time()
    try:
        if phase=='electrical':
            ctx=physics(day).generate(day);ctx.electrical.voltage.close();ctx.electrical.current.close()
            result=dict(certificate=record(MAY_RUN/'e'/day.replace('-','')/'V41_ELECTRICAL_CERTIFICATE.json'))
        elif phase=='domain':
            from v41r4_domain import generate
            result=generate(day);restoration(day)
            if day==DAY:
                assert result['total_count']==4889827 and result['candidate_set_SHA']=='02201bbbf601599bf16a7a5684a9d5ec53d5e796842bdde3b276e10a85fcb9d2'
        else:
            policy,stage=phase.split('_');assert policy in ('B0','B1','B2','B3') and stage in ('DA','AC')
            if stage=='DA':
                assert not any((MAY_RUN/day/p/'actual/ACTUAL_BOUNDARY_RECEIPT.json').exists() for p in release['policies']),'ACTUAL_OPENED_BEFORE_ALL_DAYAHEAD'
                for parent in (('B0','B1') if policy=='B3' else ('B0',) if policy!='B0' else ()):
                    assert read(MAY_OUT/day/f'PHASE_{parent}_DA.json')['status']=='PASS'
            else:
                for p in release['policies']:
                    assert read(MAY_RUN/day/p/'dayahead/DAYAHEAD_RECEIPT.json')['status']=='COMPLETE'
            prep=time.perf_counter();execution=configure(day,policy)
            from dayahead.v41.temporal_restore import activate
            if stage=='DA':
                if policy=='B1':prepare_ranking(day,prep)
                with activate():execution.dayahead(day,policy)
                from dayahead.v41r3 import candidates
                if candidates._store is not None and not candidates._store.complete:candidates._store.finish()
                result=accept_dayahead(day,policy)
            else:
                with activate():execution.actual(day,policy)
                result=accept_actual(day,policy)
        save(receipt,dict(status='PASS',day=day,phase=phase,started_at=start,completed_at=time.time(),elapsed_seconds=time.time()-start,result=result))
        print('V41R4_PHASE_PASS',day,phase,time.time()-start,flush=True)
    except BaseException as e:
        save(receipt,dict(status='FAIL_CLOSED',failure_class='TECHNICAL_CONTRACT_FAILURE',day=day,phase=phase,
            started_at=start,completed_at=time.time(),error=repr(e),traceback=traceback.format_exc()))
        raise

if __name__=='__main__':main(sys.argv[1],sys.argv[2])

