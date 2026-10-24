import random, unittest, copy, tempfile
from types import SimpleNamespace as NS
from pathlib import Path
from v44_iteration2 import config as c,performance
from v44_iteration2.migration_keys import StateIntervals,represented_migration_keys,Census
from v44_iteration2.io import read
from unittest.mock import patch


class MigrationKeys(unittest.TestCase):
    def test_interval_index_matches_every_slot_even_with_holes_and_empty_ranges(self):
        for mask in range(256):
            states={(site,slot) for site in ('a','b') for slot in range(-3,5)
                    if mask & (1 << (slot+3)) and (site=='a' or slot%2)}
            index=StateIntervals(states)
            for site in ('a','b','absent'):
                for start in range(-5,7):
                    for stop in range(-5,7):
                        self.assertEqual(index.contains(site,start,stop),
                                         all((site,t) in states for t in range(start,stop)))

    def fixture(self,rng):
        events={k:set() for k in ('y','q','w','f1','f0')}
        states={k:set() for k in ('r0','h','r1')}
        compatible={};physical={};transfers={};blocks=[]
        duration=rng.randrange(1,12)
        for source,dest in (('a','b'),('b','a')):
            for start in range(-2,4):
                if rng.random()<.8:events['y'].add((source,start))
                for cp in range(start,start+4):
                    if rng.random()<.8:events['q'].add((source,cp))
                    compatible.setdefault((source,cp),[]).append(start)
                    physical[source,cp,start]=cp*900
                    taus=tuple(t for t in range(cp,cp+5) if rng.random()<.85)
                    blocks.append((start,source,cp,cp*900,dest,1,taus))
                    for tau in taus:
                        if rng.random()<.8:events['w'].add((source,dest,tau))
                        transfers[source,dest,tau]=NS(restart=tau+2)
                        end=tau+2+duration-(cp-start)
                        if rng.random()<.8:events['f1'].add((dest,end))
            for name in states:
                states[name].update((source,t) for t in range(-2,23) if rng.random()<.95)
        return NS(events=events,states=states,compatible=compatible,physical=physical,
                  transfers=transfers,sha='UNTRUSTED_UNCHANGED_LABEL'),NS(blocks=tuple(blocks),duration=duration)

    def test_exact_key_sets_match_original_with_mutations_and_missing_support(self):
        from v42_a_stage_domain_v2.active import represented_migration_keys as original
        rng=random.Random(20261024)
        nonempty=0
        for _ in range(120):
            graph,domain=self.fixture(rng)
            for mutation in range(6):
                if mutation==1:graph.states['r0'].discard(('a',0))
                if mutation==2:graph.events['f1'].discard(('b',10))
                if mutation==3:domain.duration+=1
                if mutation==4:graph.physical['a',0,0]=-1
                if mutation==5:graph.events['w'].clear()
                expected=original(graph,domain);nonempty+=bool(expected)
                self.assertEqual(represented_migration_keys(graph,domain),expected)
        self.assertGreater(nonempty,100)

    def test_real_ledger_alias_uses_the_scoped_index_and_restores_original(self):
        from v42_a_stage_domain_v2 import active
        from v42_may12_rescue import activation
        original=active.represented_migration_keys
        graph,domain=self.fixture(random.Random(7));expected=original(graph,domain)
        for day,stage in ((c.DAYS[0],'A3'),(c.DAYS[-1],'A4')):
            with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
                from v44_iteration2.adapters import ACTIVE
                token=ACTIVE.set(dict(day=day,iteration_stage=stage,output=d))
                try:
                    with performance.scope():
                        self.assertIsInstance(active.represented_migration_keys,Census)
                        self.assertIs(activation._ledger.__globals__['represented_migration_keys'],active.represented_migration_keys)
                        self.assertEqual(active.represented_migration_keys(graph,domain),expected)
                        receipt=read(Path(d)/'ITERATION2_MIGRATION_CENSUS.json')
                        self.assertTrue(receipt['exact_state_interval_index'])
                        self.assertFalse(receipt['graph_results_cached'])
                        self.assertEqual(receipt['calls'],1)
                    self.assertIs(active.represented_migration_keys,original)
                finally:ACTIVE.reset(token)

    def test_same_shared_worker_binding_is_used_for_all31_dates_and_both_A_stages(self):
        from v44_iteration2 import worker
        import inspect
        self.assertIn('stack.enter_context(performance_scope())',inspect.getsource(worker.run))
        graph,domain=self.fixture(random.Random(3))
        from v44_iteration2.adapters import ACTIVE
        with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
            census=Census()
            for day in c.DAYS:
                for stage in ('A3','A4'):
                    token=ACTIVE.set(dict(day=day,iteration_stage=stage,output=d))
                    try:self.assertEqual(census(graph,domain),represented_migration_keys(graph,domain))
                    finally:ACTIVE.reset(token)
            self.assertEqual(census.calls,62)


if __name__=='__main__':unittest.main()
