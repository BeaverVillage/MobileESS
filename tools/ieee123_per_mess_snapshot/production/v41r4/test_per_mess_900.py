"""Deterministic mock-clock regression of the actual runtime control hooks."""
import dataclasses
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import v41r4_per_mess_budget as m
from dayahead.v35r3e_r1.beam import BeamState, deduplicate_children, prune_beam


class Clock:
    now = 0.
    def __call__(self):return self.now


def state(name, objective, move=True):
    return BeamState('B3', name, 'parent', ('MESS01',), ({'natural_MOVE_count':int(move)},), (), (), (),
        objective, objective, None, None, name, name)


class Tests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(); self.clock.now = 0.
        m.ACTIVE = m.DepthBudget('2025-05-01', 'B2', 1, clock=self.clock)

    def test_A_normal_600_seconds_identical_beam(self):
        children=[state('A',.8),state('B',.7),state('stay',.9,False)]
        self.clock.now=600
        self.assertIs(m.select_pool(children,2), children)
        expected=prune_beam(deduplicate_children(children)[0],2)[0]
        actual=prune_beam(deduplicate_children(m.select_pool(children,2))[0],2)[0]
        self.assertEqual(expected,actual)
        m.finish_depth(actual)
        self.assertFalse(m.ACTIVE.snapshot()['budget_exhausted'])

    def test_B_full_atomic_completes_no_next_candidate(self):
        calls=[]
        class Future:
            def __init__(self, result):self.value=result
            def result(self):return self.value
        class Base:
            def submit(inner, fn, item):
                calls.append(item);return Future(fn(item))
        Pool=m.budget_pool(Base)
        m.ACTIVE.k=['K200','K400','K800','FULL']
        self.clock.now=899
        def atomic(item):
            self.clock.now+=121
            m.ACTIVE.pool[item]=state(item,.6)
            return 'completed'
        iterator=Pool().map(atomic,['MOVE_B','NEXT'])
        self.assertEqual(next(iterator),'completed')
        with self.assertRaises(m.BudgetExpired):next(iterator)
        self.assertEqual(calls,['MOVE_B'])
        selected=prune_beam(deduplicate_children(m.select_pool([],2))[0],2)[0]
        self.assertEqual(selected[0].beam_state_id,'MOVE_B')
        self.assertEqual(m.ACTIVE.snapshot()['soft_budget_overrun_seconds'],120)

    def test_C_certified_moves_beat_stay_width_two(self):
        m.ACTIVE.pool={x.beam_state_id:x for x in [state('stay',.9,False),state('A',.8),state('B',.7)]}
        self.clock.now=900
        selected=prune_beam(deduplicate_children(m.select_pool([],2))[0],2)[0]
        self.assertEqual([s.beam_state_id for s in selected],['B','A'])

    def test_D_no_move_certified_stay(self):
        stay=state('stay',.9,False);m.ACTIVE.fallbacks=[stay]
        self.clock.now=900
        self.assertEqual(m.select_pool([],2),[stay])

    def test_E_depths_independent_including_overrun(self):
        starts=[]
        for depth in range(1,5):
            m.ACTIVE=m.DepthBudget('2025-05-01','B2',depth,clock=self.clock)
            starts.append(m.ACTIVE.elapsed)
            m.ACTIVE.check('FIRST_ACTION')
            self.clock.now+=1020 if depth==2 else 910
            self.assertFalse(m.ACTIVE.available())
        self.assertEqual(starts,[0.,0.,0.,0.])

    def test_F_B2_B3_same_boundary_and_contract(self):
        records=[]
        for policy in ('B2','B3'):
            self.clock.now=0;budget=m.DepthBudget('2025-05-01',policy,3,clock=self.clock)
            self.clock.now=899.999;budget.check('START_ALLOWED')
            self.clock.now=900
            with self.assertRaises(m.BudgetExpired):budget.check('START_FORBIDDEN')
            result=budget.snapshot();result.pop('policy');result.pop('started_at')
            records.append(result)
        self.assertEqual(*records)

    def test_no_reset_between_parents_or_K(self):
        self.clock.now=600;m.ACTIVE.check('PARENT_1_K200')
        self.clock.now=899;m.ACTIVE.check('PARENT_2_FULL')
        self.clock.now=901
        with self.assertRaises(m.BudgetExpired):m.ACTIVE.check('PARENT_3')
        self.assertEqual(m.ACTIVE.start,0)

    def test_uncertified_candidate_never_enters_pool(self):
        row={'exact_optimality_certificate':'V37_FAIL_CLOSED:CERTIFICATE_STALLED'}
        m.observe((row,None,{}, {}, {}))
        self.assertEqual(m.ACTIVE.pool,{})
        self.assertEqual(m.ACTIVE.stalled,1)

    def test_full_call_boundary_finishes_running_call(self):
        from dayahead.v41 import solver_observer as o
        before=o.observed;calls=[]
        def optimize(model):calls.append('finished');self.clock.now=1001;return 7
        o.observed=optimize
        try:
            m.install_solver_boundary();m.ACTIVE.full_active=1
            self.clock.now=899
            self.assertEqual(o.observed(object()),7)
            with self.assertRaises(m.BudgetExpired):o.observed(object())
            self.assertEqual(calls,['finished'])
        finally:o.observed=before

    def test_actual_source_adapter_binds_without_scientific_edits(self):
        from dayahead.v40h import beam_driver as b
        from dayahead.v41 import solver_observer as o
        paths=[Path(b.__file__),Path(o.__file__)]
        before=[p.read_bytes() for p in paths]
        m.install(nodes=[],neutral=[])
        self.assertEqual(before,[p.read_bytes() for p in paths])
        self.assertEqual(len(m.PATCHES),2)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    target=Path(__file__).parent.parent/'manifests/per_mess_900s/REGRESSION.json'
    target.write_text(json.dumps(dict(status='PASS' if result.wasSuccessful() else 'FAIL',
        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        runtime_budget_contract_SHA=m.CONTRACT_SHA),indent=2),encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
