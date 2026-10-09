"""Preservation audit must not hide actual changes to an original task."""
import unittest
from ieee8500_v42.isolation import scheduler_registration_diff


class CampaignRegistrationAudit(unittest.TestCase):
    def row(self,name='original',args='run existing',state='Ready'):
        return dict(TaskName=name,TaskPath='\\',State=state,Actions=dict(Execute='pythonw',Arguments=args),
                    Triggers=dict(Enabled=True,StartBoundary=None))

    def test_new_concurrent_task_is_reported_separately(self):
        diff=scheduler_registration_diff([self.row()],[self.row('new'),self.row(state='Running')])
        self.assertEqual(diff,dict(added=['\\new'],removed=[],modified=[]))

    def test_original_command_change_or_removal_is_a_real_drift(self):
        self.assertEqual(scheduler_registration_diff([self.row()],[self.row(args='run other')])['modified'],['\\original'])
        self.assertEqual(scheduler_registration_diff([self.row()],[])['removed'],['\\original'])

    def test_runtime_state_and_enumeration_order_are_not_authority(self):
        diff=scheduler_registration_diff([self.row(),self.row('second')],
            [self.row('second',state='Running'),self.row(state='Running')])
        self.assertEqual(diff,dict(added=[],removed=[],modified=[]))
