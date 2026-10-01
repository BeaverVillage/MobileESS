"""Recover saved A1 export on identical structure, with optimize forbidden."""
import numpy as np
import gurobipy as gp
from v42_root.common import *
from v42_root.data import prepare
from v42_root.certify import dense_value
from v42_two.contract import aidc_groups,passes
from .a1 import certificate,check_sources
from .handoff import materialize

def run():
    check_sources();folder=LOCAL/'export_recovery_numeric';folder.mkdir(exist_ok=True)
    assert not (folder/'STARTED.json').exists()
    atomic(folder/'STARTED.json',dict(export_only=True,optimize_forbidden=True))
    expected=read(OUT/'PHYSICAL_DOMAIN_REGRESSION.json')['before'];receipt=read(OUT/'A1_BOOTSTRAP_OPTIMIZATION.json')
    saved=read(LOCAL/'replay/SELECTED_PHYSICAL.json');ctrl=read(LOCAL/'replay/CONTROLS.json');cert=read(OUT/'A1_BOOTSTRAP_PHYSICAL_VALIDATION.json')
    assert receipt['complete'] and cert['PASS']
    dense=np.load(LOCAL/'replay/FINAL_X.npy');xsha=sha(LOCAL/'replay/FINAL_X.npy')
    def prohibited(*args,**kwargs):raise AssertionError('EXPORT_RECOVERY_OPTIMIZE_FORBIDDEN')
    gp.Model.optimize=prohibited
    import v42_root.native as native
    native.dump=lambda name,obj:atomic(folder/name,obj)
    class RecoveryContext(Context):
        def __init__(self):self.folder=folder
    data=prepare();m,units,legacy,handles,bindings=native.build(RecoveryContext(),data,'F2-CRA');m.update()
    actual=dict(columns=m.NumVars,rows=m.NumConstrs,nonzeros=m.NumNZs,binaries=m.NumBinVars,integers=m.NumIntVars-m.NumBinVars,fingerprint=hex(m.Fingerprint))
    assert actual==expected and len(dense)==m.NumVars
    renewed,selected,control_values,_=certificate(m,units,data,handles,bindings,legacy,dense,cert['solver_max_violation'])
    assert renewed['PASS'] and digest(selected)==digest(saved) and digest(control_values)==digest(ctrl)
    groups=aidc_groups(legacy,units,data)
    objectives={component:dense_value(expr,dense) for _,component,expr in passes(groups)}
    for r in receipt['passes']:assert abs(objectives[r['component']]-r['incumbent'])<1e-5+(1e-7 if r['component']=='rho' else 0)
    materialize(m,data,bindings,handles,saved,cert,receipt,dense=dense)
    recovery=dict(PASS=True,reason='Export numeric conversion of LinExpr failed after all four A1 solves and independent validation completed',
                  optimize_calls=0,scientific_rerun=False,structural_rebuild_only=True,model_before=expected,model_rebuilt=actual,
                  dense_sha256=xsha,selected_plan_unchanged=True,electrical_controls_unchanged=True,independent_validation=renewed,
                  changed_executed_source='v42_bootstrap/handoff.py',change_scope='Numeric export evaluation only; no objective, candidate, model, solver or physical authority change')
    recovery['prior_export_build_interruption']=read(LOCAL/'EXPORT_INTERRUPTED_BEFORE_COMPLETION.json')
    dump('A1_EXPORT_RECOVERY_RECEIPT.json',recovery)
    atomic(LOCAL/'replay/FINISHED.json',dict(complete=True,spent_seconds=receipt['total_optimize_seconds'],export_recovered=True))
    m.dispose();check_sources();print('A1 EXPORT RECOVERED, ZERO OPTIMIZE CALLS',flush=True)

if __name__=='__main__':run()
