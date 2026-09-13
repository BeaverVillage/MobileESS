"""Build an isolated coordinator with the user's final terminal A1 boundary."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
source=(ROOT/'dayahead/v40g_segments/coordination.py').read_text()
source=source.replace('from .canonical import terminal_audit, identities','from dayahead.v40g_segments.canonical import terminal_audit, identities')
start=source.index("    started=time.perf_counter();counts['FINAL_FIXED_ROUTE_PQ_RECOURSE_CALLS']+=1")
end=source.index("    objectives['J_FINAL']",start)
source=source[:start]+'''    # Final mission boundary: A1 is terminal; the original M1 is the final MESS.
    # mf keys are retained only as serializer aliases; no recourse is called.
    runtime['MF']=0.0
    mf_result={'status':'NOT_APPLICABLE_TERMINAL_A1','trajectory':deepcopy(m1),'optimizer_calls':0}
    mf_accepted=False
    final=deepcopy(m1);final_grid=grid_a1
    assert digest(final)==original_trajectory, 'TERMINAL_A1_MESS_DRIFT'
    if final_grid['status']!='PASS':raise RuntimeError('NO_FEASIBLE_FIXED_M1_A1_STATE')
'''+source[end:]
target=ROOT/'mission_coordination.py'
assert not target.exists()
target.write_text(source,encoding='utf-8')
