"""Execute the patched frozen fleet loop over four depths with mock solvers."""
import tempfile,os,json,types
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
import numpy as np
import v41r4_per_mess_budget as m
from dayahead.v40h import beam_driver as b, candidate_cache, cache, identity
from dayahead.v33m.mess_trajectory import MessTrajectorySlot
from dayahead.v35r3e_r1.beam import BeamState
from test_per_mess_900 import Clock


def main():
    m.install(nodes=[],neutral=[])
    run=dict(zip(b._run_case.__code__.co_freevars,b._run_case.__closure__))['run'].cell_contents
    records=[]
    for policy in ('B2','B3'):
        for exhausted in (False,True):
            clock=Clock();clock.now=0.;started=[];calls=[];writes=[]
            def child(parent,mid,name,rho):
                slot=MessTrajectorySlot(mid,0,'CONNECTED','STA01',None,None,(),None,0.,0.,0.,0.,0,None,0.,0.,sum(map(ord,name))/1000.,0.,760.,760./1200)
                slots=tuple((*parent.trajectory_slots,slot.to_dict()))
                sha=b.canonical_sha256(dict(name=name,parent=parent.state_sha256,mid=mid))
                vehicle=dict(natural_MOVE_count=int(name!='STAY'),full_MILP_wallclock_seconds=0.)
                return BeamState('B3',sha,parent.beam_state_id,(*parent.completed_vehicles,mid),(*parent.vehicles,vehicle),slots,(),(),rho,rho,None,None,sha,b.trajectory_equivalence_sha(slots))
            def begin(day,case,index,mid,parents,*args):
                m.ACTIVE=m.DepthBudget(day,policy,index+1,clock=clock)
                started.append((index+1,m.ACTIVE.elapsed))
                m.ACTIVE.fallbacks=[child(p,mid,'STAY',.95) for p in parents]
            def local(**kw):
                m.ACTIVE.check('K200');m.ACTIVE.k=['K200','K400','K800','FULL']
                p=kw['parent'];mid=kw['mess_id']
                for name,rho in [('STAY',.95),('MOVE_A',.8),('MOVE_B',.7)]:
                    c=child(p,mid,name,rho);m.ACTIVE.pool[c.state_sha256]=c
                clock.now+=800 if exhausted else 100
                summary=dict(dynamic_feasible_candidates=201,static_candidates_fail_closed_evaluated=3,
                    restricted_unique_candidate_state_solves=3,restricted_solver_calls=3,distinct_seed_count=2,
                    cheap_screen_wallclock_seconds=0.,restricted_wallclock_seconds=100.)
                seeds=[dict(seed_index=i,candidate_id=f'SEED{i}',trajectory_signature=str(i)) for i in (1,2)]
                return seeds,summary
            def full(**kw):
                m.ACTIVE.check('FULL_MILP')
                calls.append((m.ACTIVE.depth,kw['seed']['seed_index'],m.ACTIVE.elapsed))
                clock.now+=220 if exhausted else 100
                return child(kw['parent'],kw['mess_id'],'FULL_MOVE'+str(kw['seed']['seed_index']),.6)
            execution=dict(identity_SHA='sha',identity=dict(inputs={k:dict(canonical_SHA='x') for k in ('traffic_forecast','route_table','road_graph')}))
            S=types.SimpleNamespace
            with tempfile.TemporaryDirectory(dir=Path(__file__).parent.parent/'manifests/per_mess_900s') as temp,ExitStack() as stack:
                temp=Path(temp)
                os.environ['IEEE123_MESS_POLICY']=policy
                values=dict(APR01='2025-05-01',CACHE_ROOT=temp,MESS_IDS=('MESS01','MESS02','MESS03','MESS04'),
                    EXECUTION_CACHE_CONTEXT={'execution_fingerprint_sha256':'sha'},
                    install_missing_directory_tolerant_lookup=lambda:None,
                    prepare_aidc_stages=lambda *a:(None,S(legacy_context=None,voltage=S(close=lambda:None),current=S(close=lambda:None)),{'B1':{'planning_pcc_power_kw':np.zeros((96,12))}}),
                    daily_traffic_authority=lambda *a:(S(canonical_sha256='x'),S(route_graph_sha='x'),S(canonical_sha256='x'),None),
                    slot_coefficients=lambda *a:None,_critical_states=lambda *a:(set(),{}),
                    _planning_grid=lambda *a:({},dict(rho=.6)),_local_search=local,_make_child=full,
                    _progress=lambda **v:None)
                # Voltage only needs control_names plus close in this loop fixture.
                class Voltage(dict):
                    def close(self):pass
                voltage=Voltage(control_names=['mess_p_kw[STA01]'])
                values['prepare_aidc_stages']=lambda *a:(None,S(legacy_context=None,voltage=voltage,current=S(close=lambda:None)),{'B1':{'planning_pcc_power_kw':np.zeros((96,12))}})
                for name,value in values.items():stack.enter_context(patch.object(b,name,value))
                stack.enter_context(patch.object(candidate_cache,'require_context',lambda c:execution))
                stack.enter_context(patch.object(candidate_cache,'verify_full_child',lambda c,p:c))
                stack.enter_context(patch.object(identity,'verify_bound_files',lambda e:None))
                stack.enter_context(patch.object(cache,'write_stage',lambda *a:None))
                class Load(dict):
                    def __enter__(self):return self
                    def __exit__(self,*a):pass
                stack.enter_context(patch.object(np,'load',lambda *a,**k:Load(branch_names=np.array(['x']),branch_phases=np.array(['A']),phase_current_loading_pu=np.zeros((96,1)))))
                stack.enter_context(patch.object(np,'savez_compressed',lambda *a,**k:None))
                run.__globals__['begin_depth']=begin
                result=b._run_case('B3',2,1)
            assert started==[(1,0.),(2,0.),(3,0.),(4,0.)],started
            assert [r['stage'] for r in result['trace']]==[1,2,3,4]
            assert all(r['retained_beam_count']==2 for r in result['trace'])
            if exhausted:
                assert len(calls)==4 and all(start==800 for _,_,start in calls),calls
                assert all(s['vehicles'][-1]['natural_MOVE_count'] for s in result['retained_final_states'])
            else:assert len(calls)==14,calls
            records.append(dict(policy=policy,expiry=exhausted,depths=started,full_calls=calls,retained_widths=[r['retained_beam_count'] for r in result['trace']]))
    target=Path(__file__).parent.parent/'manifests/per_mess_900s/FLEET_LOOP_INTEGRATION.json'
    target.write_text(json.dumps(dict(status='PASS',scenarios=records,runtime_budget_contract_SHA=m.CONTRACT_SHA),indent=2),encoding='utf-8')
    print('FOUR_DEPTH_FROZEN_LOOP_INTEGRATION_PASS')


if __name__=='__main__':main()
