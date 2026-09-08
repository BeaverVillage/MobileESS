"""Data-free checks for the archived Actual source and PCS authority.

Does not import campaign launchers, access live results, or invoke OpenDSS.
"""
from pathlib import Path
import ast, hashlib, json, math
from types import SimpleNamespace
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
DOC=ROOT/'docs/v41r4_actual'
SNAP=Path(__file__).resolve().parent/'robust_v2'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    manifest=read(DOC/'SOURCE_SNAPSHOT.json')
    for row in manifest['files']:
        path=(ROOT/row['path']).resolve()
        assert path.is_relative_to(ROOT.resolve())
        assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],row['path']
    overlay=SNAP.parent/'perf1_overlay'
    sources=list(SNAP.rglob('*.py'))+list(overlay.rglob('*.py'))
    for path in sources:ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
    method=read(SNAP/'METHOD_FREEZE.json')
    for name,h in read(SNAP/'METHOD_CODE_BINDING.json')['files'].items():assert sha(SNAP/name)==h
    for row in method['numerical_method_files']:assert sha(SNAP/'frozen_code'/row['name'])==row['sha256']
    assert sha(SNAP/'BATTERY_EFFICIENCY_AUTHORITY.json')==method['efficiency_authority_SHA']
    eta=read(SNAP/'BATTERY_EFFICIENCY_AUTHORITY.json')
    assert eta['eta_charge']==eta['eta_discharge']==.95
    assert method['alpha_BG']==1.15 and method['P_fallback'] is False
    state=read(DOC/'evidence/RESULT.json')['regression']
    assert state['B_TAPS_ONLY']['all_bit_identical'] is False
    for name in ['B_VISIBLE_STATE_WITH_WARMSTART','C_REUSED_ENGINE_WITH_WARMSTART','C_REVERSE_ORDER']:
        assert state[name]['comparisons']==55 and state[name]['all_bit_identical']
    search=read(DOC/'evidence/FULL_EQUIVALENCE_RESULT.json')
    assert search['all_Q_trials_identical_order_and_bit_identical_outputs'] and search['accepted_Q_bit_identical']
    assert search['performance_engine_SHA']==sha(SNAP/'acceleration_audit/cached_engine.py')
    gate=read(DOC/'evidence/SELECTED_Q_GATE_AUTHORITY.json')
    assert gate['old_full_day_search_selection_equivalence_not_claimed']
    final=read(DOC/'evidence/MAY12_FINAL_EQUIVALENCE_GATE.json')
    assert final['status']=='PASS' and final['slots']==96 and all(final['checks'].values())
    assert final['old_full_day_search_selection_equivalence_not_claimed']
    perf=read(overlay/'PERFORMANCE_FREEZE.json')
    assert perf['gate_SHA']==sha(DOC/'evidence/MAY12_FINAL_EQUIVALENCE_GATE.json')
    assert perf['validation_scope']==final['validation_scope']
    for name,h in perf['implementation_files'].items():
        path=overlay/name if (overlay/name).exists() else SNAP/name
        if name=='cached_engine.py':path=SNAP/'acceleration_audit/cached_engine.py'
        assert sha(path)==h,('DEPLOYED_IMPLEMENTATION_DRIFT',name)
    # Exercise the actual frozen Q-bound function without importing its host runtime.
    tree=ast.parse((SNAP/'frozen_code/qsafe.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='q_bounds')
    namespace={'np':np};exec(compile(ast.Module(body=[node],type_ignores=[]),'<frozen q_bounds>','exec'),namespace)
    bound=namespace['q_bounds'];authority=SimpleNamespace(pcs_kva=400.,pcs_polygon_faces=16,active_power_limit_kw=300.)
    faces=2*np.pi*np.arange(16)/16;ap=400*np.cos(np.pi/16)
    p=np.array([-300.,-150.,0.,85.42516203702252,300.]);lo,hi=bound(p,np.ones(len(p),dtype=bool),authority)
    for active,lower,upper in zip(p,lo,hi):
        for q in [lower,upper]:
            assert math.hypot(active,q)<=400+1e-9
            assert np.max(active*np.cos(faces)+q*np.sin(faces))<=ap+1e-9
        # The interval must also be maximal, not merely conservative.
        for q in [lower-1e-5,upper+1e-5]:
            assert math.hypot(active,q)>400 or np.max(active*np.cos(faces)+q*np.sin(faces))>ap
    dl,dh=bound(p,np.zeros(len(p),dtype=bool),authority)
    assert np.array_equal(dl,np.zeros(len(p))) and np.array_equal(dh,np.zeros(len(p)))
    rejected=False
    try:bound(np.array([300.01]),np.array([True]),authority)
    except AssertionError:rejected=True
    assert rejected,'ACTIVE_RATING_NOT_ENFORCED'
    result=dict(status='PASS',snapshot_files=len(manifest['files']),parsed_Python_sources=len(sources),source_hashes_preserved=True,scientific_bindings_preserved=True,deployed_performance_seal_verified=True,PCS_endpoint_and_maximality_cases=len(p),disconnected_Q_zero=True,active_rating_rejection=True,evidence_scope_checked=True,campaign_or_AC_calls=0)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
