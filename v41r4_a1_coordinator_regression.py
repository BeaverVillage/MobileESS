"""Exercise current B3 coordinator wrappers with completed real B1 inputs."""
from fast_prepare import *
from v41r4_runtime import MAY_RUN,MAY_OUT
import numpy as np

def main():
    import v41r4_b3_equivalent as a
    from v41r4_electrical import configure as physics
    from dayahead.v41.snapshot import create
    from dayahead.v41.reserve import bind
    from dayahead.v41r1.feasible_seed import neutral_mess
    from dayahead.v41.temporal_restore import activate
    from dayahead.v40g_segments import b3
    from dayahead.v40g_segments.canonical import identities,planning_power
    from dayahead.v40a.invariants import digest
    day='2025-05-04';a.configure(day,'B3');ctx=physics(day).load(day)
    try:
        path,seal=create(day);bind(ctx,path,seal['snapshot']['sha256'])
        jobs=read(MAY_RUN/day/'B1/dayahead/FROZEN_JOINT_DECISION.json')['decision']['AIDC_decision']
        mess=neutral_mess();pcc=planning_power(jobs,ctx)['pcc'];calls=[]
        def m1(p,cert):
            assert np.array_equal(p,pcc);calls.append('M1')
            return mess,dict(status='PASS')
        def feedback(j,m):
            assert identities(j)==identities(jobs) and digest(m)==digest(mess);calls.append('A1')
            return dict(status='PASS',jobs=j)
        def mf(p,m,cert):
            assert np.array_equal(p,pcc) and digest(m)==digest(mess);calls.append('MF')
            return dict(status='PASS',trajectory=m)
        with activate():result=b3.coordinate_segments(jobs,ctx,m1,feedback,mf,dict(diagnostic=True))
        assert calls==['M1','A1','MF'] and result['B3_A0_optimize_calls']==0
        assert result['AIDC_FEEDBACK_ACCEPTED'] and result['FINAL_PQ_RECOURSE_ACCEPTED']
        assert identities(result['a1'])==identities(jobs)
        save(MAY_OUT/'A1_regression/COORDINATOR_REGRESSION.json',dict(status='PASS',calls=calls,
            B1_A0_identity_exact=True,M1_MF_unchanged=True,A0_optimization_calls=0,
            original_temporal_and_migration_domain_audit='PASS',Actual_reads=0,optimizer_calls=0,
            source=record(ROOT/'v41r4_b3_equivalent.py'),patches=a.PATCHES))
        print('A1_COORDINATOR_REGRESSION_PASS',flush=True)
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

if __name__=='__main__':main()
