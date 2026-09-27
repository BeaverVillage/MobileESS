import unittest
import numpy as np
from study import bounds, capacity_options

def row(**changes):
    r=dict(state_at_issue='PENDING',AIDC_site='A',start_slot=24,safe_duration_slots=4,
           requested_GPU=2,RSP_start_slot=24,RW_completion_slot=36,eligible_standby=False,
           protected=False,qos='normal')
    return {**r,**changes}

class ContractTests(unittest.TestCase):
    def test_normal_requires_mature_tolerant_cohort(self):
        self.assertEqual(bounds(row(),'R1',{}),(24,24))
        self.assertEqual(bounds(row(),'R1',{'latency_tolerant':True}),(24,32))

    def test_protection_and_carryin(self):
        for r in [row(protected=True),row(state_at_issue='RUNNING'),row(AIDC_site='UNASSIGNED'),row(start_slot=23)]:
            self.assertEqual(bounds(r,'R1',{'latency_tolerant':True}),(r['start_slot'],r['start_slot']))

    def test_terminal_tail_never_increases(self):
        self.assertEqual(bounds(row(start_slot=116,RSP_start_slot=116,safe_duration_slots=20,RW_completion_slot=180,eligible_standby=True,qos='standby'),'R0',{}),(116,116))

    def test_zero_slack_gate_is_not_motion(self):
        self.assertEqual(bounds(row(RW_completion_slot=28,eligible_standby=True,qos='standby'),'R0',{}),(24,24))

    def test_budget_is_job_specific(self):
        self.assertEqual(bounds(row(),'R2',{'latency_tolerant':True,'budget_slots':2}),(24,26))
        self.assertEqual(bounds(row(qos='standby',eligible_standby=True),'R2',{}),(24,24))

    def test_capacity_conflict_fails_closed(self):
        r=row();load={'A':np.zeros(150,dtype=int)};load['A'][24:28]=2;load['A'][28:40]=2
        self.assertEqual(capacity_options(r,24,32,load,{'A':2}),[])

    def test_capacity_witness_full_duration(self):
        r=row();load={'A':np.zeros(150,dtype=int)};load['A'][24:28]=2
        self.assertEqual(capacity_options(r,24,26,load,{'A':2}),[('A',25),('A',26)])

    def test_source_load_not_mutated(self):
        load={'A':np.zeros(150,dtype=int)};load['A'][24:28]=2;before=load['A'].copy()
        capacity_options(row(),24,30,load,{'A':2});np.testing.assert_array_equal(load['A'],before)

if __name__=='__main__':unittest.main()
