"""Exercise supervisor handover with three live jobs and one added day; no solver."""
import contextlib, io, tempfile, threading, types, unittest
from pathlib import Path
from unittest.mock import patch
import v41r4_900_campaign as c


class AdoptionTest(unittest.TestCase):
    def test_four_slots_preserve_three_running_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); out=root/'audit'; logs=root/'logs'
            released=threading.Event(); launched=[]; waited=[]
            phases=['B1_DA','B2_DA','B3_DA','B0_AC','B1_AC','B2_AC','B3_AC']
            def receipt(day,phase):
                c.write_json(out/day/f'PHASE_{phase}.json',dict(status='PASS',runtime_budget_contract_SHA=c.CONTRACT_SHA))
            for n in range(1,32):
                for phase in phases:
                    if (n<=3 and phase=='B3_DA') or (n==4 and phase=='B2_DA'):continue
                    receipt(f'2025-05-{n:02}',phase)
            class Existing:
                def __init__(self,day):self.day=day
                def wait(self):
                    assert released.wait(5),'Fourth slot was never launched'
                    waited.append(self.day);receipt(self.day,'B3_DA');return 0
            adopted={f'2025-05-{n:02}':dict(day=f'2025-05-{n:02}',phase='B3_DA',worker_pid=n,
                started_at=1,log='existing',adopted=True,process=Existing(f'2025-05-{n:02}')) for n in range(1,4)}
            class New:
                pid=4
                def __init__(self,args,**kwargs):
                    self.day,self.phase=args[-2:];launched.append((self.day,self.phase));released.set()
                def wait(self):receipt(self.day,self.phase);return 0
            report=types.ModuleType('v41r4_report');report.finalize=lambda **kw:{'status':'PASS'}
            loop=types.ModuleType('v41r4_loop_runtime');loop.install_reports=lambda:None
            campaign=types.ModuleType('dayahead.v41.campaign');campaign.campaign_lock=lambda root:contextlib.nullcontext()
            with patch.multiple(c,RUN=root,OUT=out,LOGS=logs), \
                 patch.object(c,'verify_release'),patch.object(c,'bind'), \
                 patch.object(c,'discover_workers',return_value=adopted), \
                 patch.object(c.subprocess,'Popen',New), \
                 patch.dict('sys.modules',{'v41r4_report':report,'v41r4_loop_runtime':loop,'dayahead.v41.campaign':campaign}), \
                 contextlib.redirect_stdout(io.StringIO()):
                c.main()
            self.assertEqual(launched,[('2025-05-04','B2_DA')])
            self.assertEqual(sorted(waited),['2025-05-01','2025-05-02','2025-05-03'])
            status=c.read(out/'MAY_CAMPAIGN_STATUS.json')
            self.assertEqual(status['day_workers'],4)
            self.assertEqual(len(status['completed_phases']),217)
            self.assertEqual(status['errors'],[])


if __name__=='__main__':unittest.main()
