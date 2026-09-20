"""Resume B2 Actual with nonconvergent trial rejection; frozen Q search unchanged."""
import sys,os,time,json,traceback,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
sys.argv.append('--b012')
import actual_campaign as a
from types import MethodType
BaseElectrical=a.Electrical

class TrialElectrical(BaseElectrical):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        def solve(engine):
            engine.d.Solution.SolveSnap()
            error=engine.d.Error.Number()
            assert error==0, ('OPENDSS_API_ERROR',error)
            # The inherited feasible(r) requires convergence. Return measured
            # arrays and converged=False so this trial cannot be accepted.
        self.e.solve=MethodType(solve,self.e)
    def apply(self,t,q):
        r=super().apply(t,q)
        assert all(a.np.all(a.np.isfinite(r[k])) for k in ('v','line','tx','kva'))
        if not r['converged']:
            with (a.H/'B2/NONCONVERGENT_TRIALS.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(dict(slot=t,Q=list(map(float,q)),converged=False,
                    controls_settled=r['controls_settled'],Vmin=float(r['v'].min()),
                    Vmax=float(r['v'].max()),max_line=float(r['line'].max()),unix=time.time()))+'\n')
        return r

def main():
    a.verify()
    assert a.read(a.BASE/'ACTUAL_B012_PRIORITY_AUTHORIZATION.json')['authorized']
    for p in ('B0','B1'):
        assert a.read(a.H/p/'COMPLETE.json')['independent_replay_PASS']
    supplement=a.H/'TRIAL_ERROR_HANDLING_FREEZE.json'
    payload=dict(status='FROZEN_BEFORE_RETRY',original_rule=a.rec(a.H/'RULE_FREEZE.json'),
        adapter=a.rec(Path(__file__)),original_engine=a.rec(a.BASE/'electrical_engine.py'),
        exact_change='Nonconvergent trial returns native arrays with converged=False; inherited feasible rejects it.',
        original_QSAFE_search_unchanged=True,solver_settings_unchanged=True,
        hard_limits_and_final_exact_unchanged=True,B0_B1_reused=True,unix=time.time())
    if supplement.exists():
        old=a.read(supplement);assert old['adapter']['sha256']==payload['adapter']['sha256']
    else:a.save(supplement,payload)
    a.bootstrap.protect();a.Electrical=TrialElectrical
    ns=a.kernel();ns['independent_audit']=a.binding.independent_audit
    # Verify that a nonconvergent otherwise feasible state is always rejected.
    assert not ns['feasible'](dict(converged=False,v=a.np.ones(2),ipu=a.np.zeros(2),kva=a.np.zeros(1)))
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    da=MessElectricalAuthority.from_repository();da.validate()
    import gurobipy as gp
    gp.Model.optimize=lambda *x,**k:(_ for _ in ()).throw(RuntimeError('DA_OPTIMIZATION_FORBIDDEN_IN_ACTUAL'))
    a.run_policy('B2',ns,da);a.verify()
    assert a.sha(__file__)==a.read(supplement)['adapter']['sha256']
    results={p:a.read(a.H/p/'COMPLETE.json') for p in ('B0','B1','B2')}
    a.save(a.H/'CAMPAIGN_COMPLETE.json',dict(status='COMPLETE',policies=results,
        all_AC_feasible=all(r['AC_feasible'] for r in results.values()),completed_unix=time.time(),
        supplemental_runtime_freeze=a.rec(supplement)))
    a.state(status='COMPLETE',stage='ACTUAL_CAMPAIGN_FINISHED')

if __name__=='__main__':
    try:main()
    except BaseException as e:
        a.save(a.H/'TECHNICAL_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()))
        a.state(status='FAILED',stage='ACTUAL_B2_FAILURE',error=repr(e));raise
