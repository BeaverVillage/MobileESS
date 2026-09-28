import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v42_reference_episode import (Observation,Capacity,ReferenceBuilder,reference_action,
    capacity_audit,validate_initial_placement,digest,frozen_day)

T=1710460800  # aligned test issue boundary; absolute date not an input to scoring
CAP=Capacity((('AIDC01',8),('AIDC02',8)),(('AIDC01_LP01','AIDC01',8),('AIDC02_LP01','AIDC02',8)),(('AIDC01',.5),('AIDC02',.5)))
def obs(uid='j',state='PENDING',gpu=4,duration=20,**kw):
    d=dict(uid=uid,source_record_hash=digest(uid),submit_seconds=T-900,state=state,gpu=gpu,
           duration_slots=duration,duration_seconds=duration*900,duration_authority='INHERITED_REQUEST',
           valid_request=True,qos='normal',known_start_seconds=T-900 if state=='RUNNING' else None)
    d.update(kw);return Observation(**d)
def row(day,uid):return next(r for r in day['rows'] if r['job_uid']==uid)
def pending_pair():
    b=ReferenceBuilder(CAP)
    jobs=[obs('block1','RUNNING',8,200),obs('block2','RUNNING',8,200),obs()]
    first=b.day('2024-03-15',T,jobs)
    jobs2=[replace(j,duration_slots=104,duration_seconds=104*900) if j.state=='RUNNING' else j for j in jobs]
    return b,first,jobs2

class ReferenceTests(unittest.TestCase):
    def test_pending_midnight_same_site_and_absolute_obligation(self):
        b,a,jobs=pending_pair();c=b.day('2024-03-16',T+86400,jobs)
        self.assertEqual(row(a,'j')['reference_AIDC_site'],row(c,'j')['reference_AIDC_site'])
        self.assertEqual(row(a,'j')['absolute_start_seconds'],row(c,'j')['absolute_start_seconds'])
        self.assertTrue(c['ready'])

    def test_pending_to_running_same_site(self):
        b,a,_=pending_pair();c=b.day('2024-03-16',T+86400,[obs(state='RUNNING',known_start_seconds=T+900)])
        self.assertEqual(row(a,'j')['reference_AIDC_site'],row(c,'j')['reference_AIDC_site'])
        self.assertTrue(row(c,'j')['continuation_from_previous_snapshot'])

    def test_running_midnight_same_site(self):
        b=ReferenceBuilder(CAP);a=b.day('2024-03-15',T,[obs(state='RUNNING')]);c=b.day('2024-03-16',T+86400,[obs(state='RUNNING')])
        self.assertEqual(a['rows'][0]['reference_AIDC_site'],c['rows'][0]['reference_AIDC_site'])

    def test_continuing_never_rehashed_or_first_fit(self):
        b,a,jobs=pending_pair()
        with patch.object(Capacity,'preference',side_effect=AssertionError('rehash')),patch('v42_reference_episode.reference_action',side_effect=AssertionError('first fit')):
            c=b.day('2024-03-16',T+86400,jobs)
        self.assertTrue(c['ready'])

    def test_new_explicit_attempt_new_identity_and_may_change_site(self):
        b=ReferenceBuilder(CAP);a=b.day('2024-03-15',T,[obs(state='RUNNING')]);old=a['rows'][0]
        # Only the former site has a rack for an 8-GPU blocker; reserve it with a
        # continuing episode, then a source-backed new attempt may choose elsewhere.
        b.history['block']=dict(old,job_uid='block',episode_id=digest('block'),source_record_hash=digest('block'),requested_GPU=8)
        new=obs(state='RUNNING',attempt_id='attempt2',attempt_authority_hash='a'*64,attempt_observed_seconds=T+1)
        c=b.day('2024-03-16',T+86400,[obs('block','RUNNING',8),new])
        self.assertTrue(row(c,'j')['new_episode']);self.assertNotEqual(old['episode_id'],row(c,'j')['episode_id'])
        self.assertNotEqual(old['reference_AIDC_site'],row(c,'j')['reference_AIDC_site'])

    def test_gap_is_not_permanent_uid_home_or_automatic_new_attempt(self):
        b=ReferenceBuilder(CAP);a=b.day('2024-03-15',T,[obs(state='RUNNING')]);b.day('2024-03-16',T+86400,[])
        c=b.day('2024-03-17',T+172800,[obs(state='RUNNING')])
        self.assertEqual(c['rows'][0]['status'],'EPISODE_BOUNDARY_UNRESOLVED')
        self.assertFalse(c['rows'][0]['new_episode']);self.assertFalse(c['ready'])
        self.assertEqual(a['rows'][0]['reference_AIDC_site'],c['rows'][0]['reference_AIDC_site'])

    def test_state_regression_and_changed_execution_start_fail_closed(self):
        for o in [obs(),obs(state='RUNNING',known_start_seconds=T+1)]:
            b=ReferenceBuilder(CAP);b.day('2024-03-15',T,[obs(state='RUNNING')])
            self.assertFalse(b.day('2024-03-16',T+86400,[o])['ready'])

    def test_still_pending_expired_plan_not_silently_rescheduled(self):
        b=ReferenceBuilder(CAP);a=b.day('2024-03-15',T,[obs()]);c=b.day('2024-03-16',T+86400,[obs()])
        self.assertEqual(c['rows'][0]['status'],'REFERENCE_START_STATE_CONFLICT')
        self.assertEqual(a['rows'][0]['reference_AIDC_site'],c['rows'][0]['reference_AIDC_site'])
        self.assertFalse(c['ready'])

    def test_running_initial_mutation_rejected_migration_separate(self):
        a=ReferenceBuilder(CAP).day('2024-03-15',T,[obs(state='RUNNING')]);r=a['rows'][0]
        other=next(s for s,_ in CAP.sites if s!=r['reference_AIDC_site'])
        with self.assertRaisesRegex(ValueError,'IMMUTABLE_INITIAL_SITE'):validate_initial_placement(r,other,0)
        optimized_migration=dict(initial_site=r['reference_AIDC_site'],destination=other,checkpoint=2)
        self.assertNotEqual(optimized_migration['destination'],r['reference_AIDC_site'])
        self.assertFalse(r['migration_selected_in_reference'])

    def test_policy_migration_or_returned_row_mutation_cannot_seed_next_reference(self):
        b=ReferenceBuilder(CAP);a=b.day('2024-03-15',T,[obs(state='RUNNING')]);r=a['rows'][0]
        reference=r['reference_AIDC_site'];other=next(s for s,_ in CAP.sites if s!=reference)
        # A counterfactual consumer's result/record cannot mutate builder history.
        r.update(reference_AIDC_site=other,migration_selected_in_reference=True)
        following=b.day('2024-03-16',T+86400,[obs(state='RUNNING')])['rows'][0]
        self.assertEqual(following['reference_AIDC_site'],reference)
        self.assertFalse(following['migration_selected_in_reference'])

    def test_spatial_only_allowed_temporal_unknown_not_erasing_spatial(self):
        b=ReferenceBuilder(CAP);d=b.day('2024-03-15',T,[obs('b1','RUNNING',8,30),obs('b2','RUNNING',8,30),obs()]);r=row(d,'j')
        self.assertTrue(r['spatial_eligible']);self.assertIsNone(r['temporal_eligible_if_authorized'])
        other=next(s for s,_ in CAP.sites if s!=r['reference_AIDC_site'])
        self.assertTrue(validate_initial_placement(r,other,r['reference_start_slot']))
        with self.assertRaisesRegex(ValueError,'TEMPORAL_AUTHORITY'):validate_initial_placement(r,other,r['reference_start_slot']+1)

    def test_forbidden_input_channels_absent(self):
        for field in ['grid_result','policy_label','May_outcome','future_runtime','MESS','objective']:
            with self.subTest(field=field),self.assertRaises(TypeError):reference_action(4,20,0,[],CAP,**{field:1})
            with self.assertRaises(TypeError):Observation(**dict(obs().__dict__,**{field:1}))

    def test_future_start_and_attempt_evidence_rejected(self):
        for o in [obs(known_start_seconds=T+100),obs(attempt_id='x'),obs(state='RUNNING',known_start_seconds=T+100)]:
            with self.assertRaises(ValueError):ReferenceBuilder(CAP).day('2024-03-15',T,[o])

    def test_archive_hash_is_provenance_not_placement_seed(self):
        a=ReferenceBuilder(CAP).day('2024-03-15',T,[obs(source_record_hash='a'*64)])['rows'][0]
        b=ReferenceBuilder(CAP).day('2024-03-15',T,[obs(source_record_hash='b'*64)])['rows'][0]
        self.assertEqual(a['episode_id'],b['episode_id'])
        self.assertEqual(a['reference_AIDC_site'],b['reference_AIDC_site'])

    def test_overlap_carry_obligations_retained_not_repaired(self):
        small=Capacity((('AIDC01',8),),(('LP','AIDC01',8),),(('AIDC01',1.),))
        b=ReferenceBuilder(small);a=b.day('2024-03-15',T,[obs('a',gpu=8),obs('b',gpu=8)])
        c=b.day('2024-03-16',T+86400,[obs('a','RUNNING',8,known_start_seconds=T+1),obs('b','RUNNING',8,known_start_seconds=T+2)])
        self.assertFalse(c['ready']);self.assertTrue(c['issues'])
        self.assertEqual([r['reference_AIDC_site'] for r in a['rows']],[r['reference_AIDC_site'] for r in c['rows']])
        self.assertEqual(set(c['issues'][0]['episodes']),{r['episode_id'] for r in c['rows']})

    def test_rack_compatibility_and_no_gang_splitting(self):
        cap=Capacity((('AIDC01',8),('AIDC02',8)),(('LP1','AIDC01',4),('LP2','AIDC02',4)),CAP.prior)
        self.assertIsNone(reference_action(8,20,0,[],cap))
        d=ReferenceBuilder(CAP).day('2024-03-15',T,[obs(gpu=16)])
        self.assertEqual(d['rows'][0]['requested_GPU'],16);self.assertIsNone(d['rows'][0]['reference_AIDC_site'])

    def test_site_capacity_whole_service_and_carry_out(self):
        intervals=[(90,200,8,'old','AIDC01'),(0,200,8,'other','AIDC02')]
        r=reference_action(4,30,80,intervals,CAP)
        self.assertEqual(r['start'],200) # prefix-only feasibility would wrongly admit at 80

    def test_reference_rule_depends_on_physical_state_only(self):
        a=reference_action(4,20,0,[],CAP)
        b=reference_action(4,20,0,[(0,20,8,'old','AIDC01')],CAP)
        self.assertEqual(a['site'],'AIDC01');self.assertEqual(b['site'],'AIDC02')

    def test_sweep_matches_exhaustive_resource_event_oracle(self):
        import random
        from v42_reference_episode import fits,Reservations
        rng=random.Random(741)
        for _ in range(120):
            intervals=[]
            for n in range(rng.randrange(30)):
                a=rng.randrange(60);b=a+rng.randrange(1,30);s=rng.choice(['AIDC01','AIDC02'])
                intervals.append((a,b,rng.choice([1,2,4,8]),str(n),s))
            release=rng.randrange(40);gpu=rng.choice([1,2,4,8]);duration=rng.randrange(1,40)
            expected=None
            for t in sorted({release}|{b for a,b,g,u,s in intervals if release<b<=80}):
                feasible=tuple(s for s,_ in CAP.sites if fits(intervals,s,t,t+duration,gpu,CAP))
                if feasible:expected=(t,feasible[0],feasible);break
            actual=reference_action(gpu,duration,release,intervals,CAP,max_start=80)
            self.assertEqual(expected,None if actual is None else (actual['start'],actual['site'],actual['feasible_sites']))
            indexed=Reservations()
            for interval in intervals:indexed.append(interval)
            self.assertEqual(actual,reference_action(gpu,duration,release,indexed,CAP,max_start=80))
            for site,_ in CAP.sites:self.assertEqual(fits(intervals,site,release,release+duration,gpu,CAP),fits(indexed,site,release,release+duration,gpu,CAP))

    def test_deterministic_build_input_order_and_worker_orders(self):
        from concurrent.futures import ThreadPoolExecutor
        def build():
            b=ReferenceBuilder(CAP)
            return [b.day('2024-03-15',T,[obs('b','RUNNING'),obs('a','RUNNING')]),
                    b.day('2024-03-16',T+86400,[obs('a','RUNNING'),obs('b','RUNNING')])]
        a=build();self.assertEqual(digest(a),digest(build()))
        with tempfile.TemporaryDirectory() as p:
            p=Path(p);(p/'days').mkdir();hashes={d['day']:digest(d) for d in a}
            (p/'REFERENCE_LEDGER_FREEZE.json').write_text(json.dumps(dict(ready=True,day_hashes=hashes)))
            for d in a:(p/'days'/(d['day']+'.json')).write_text(json.dumps(d))
            chronological={d:digest(frozen_day(p,d)) for d in hashes}
            reverse={d:digest(frozen_day(p,d)) for d in reversed(hashes)}
            with ThreadPoolExecutor(4) as pool:parallel=dict(zip(hashes,pool.map(lambda d:digest(frozen_day(p,d)),hashes)))
            self.assertEqual(chronological,reverse);self.assertEqual(reverse,parallel)
            (p/'days'/'2024-03-15.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):frozen_day(p,'2024-03-15')

    def test_not_ready_freeze_denies_consumer(self):
        d=ReferenceBuilder(CAP).day('2024-03-15',T,[obs('big','RUNNING',16)])
        with tempfile.TemporaryDirectory() as p:
            p=Path(p);(p/'days').mkdir();(p/'days'/(d['day']+'.json')).write_text(json.dumps(d))
            (p/'REFERENCE_LEDGER_FREEZE.json').write_text(json.dumps(dict(ready=False,day_hashes={d['day']:digest(d)})))
            with self.assertRaisesRegex(ValueError,'NOT_READY'):frozen_day(p,d['day'])
            self.assertFalse(frozen_day(p,d['day'],audit_only=True)['ready'])

if __name__=='__main__':unittest.main()
