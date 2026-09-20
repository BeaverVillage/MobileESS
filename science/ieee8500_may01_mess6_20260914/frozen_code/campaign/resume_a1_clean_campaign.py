"""Fresh pre-search outputs after preserving the failed A1 attempt."""
import sys,time,traceback
import resume_a1_alias_campaign as campaign
campaign.R=campaign.H/'a1_clean_recovery_20260914'
if __name__=='__main__':
    sys.stdout=open(campaign.R/'supervisor.log','a',encoding='utf-8',buffering=1)
    sys.stderr=open(campaign.R/'supervisor.stderr.log','a',encoding='utf-8',buffering=1)
    try:
        for name in ['B3_A1','B3_A1_electrical_rows','B3_A1_seed_exact']:
            assert not(campaign.H/name).exists(),('STALE_PRESEARCH_OUTPUT',name)
        campaign.main()
    except BaseException as error:
        campaign.c.save('B3_CONTINUATION_FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc()))
        campaign.c.save('SUPERVISOR_STATUS.json',dict(status='FAILED',error=repr(error),updated_unix=time.time()))
        raise
