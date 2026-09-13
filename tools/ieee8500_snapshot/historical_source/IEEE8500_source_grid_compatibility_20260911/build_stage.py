"""Construct reviewed stage code before the pre-execution freeze; never edit inputs."""
import sys,ast,json
from pathlib import Path
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parent;PREV=R/'IEEE8500_production_compatibility_20260911'
def main():
    rule=json.loads((PREV/'COMPATIBILITY_RULE.json').read_text(encoding='utf-8'))
    del rule['fixed_source_pu']
    rule.update(authority_type='USER_FIXED_SOURCE_GRID_COMPATIBILITY_ADAPTATION',source_grid_descending=[1.050,1.045,1.040,1.035,1.030],additional_allowed_parameter='Vsource pu only',screen_rule='All 105 source-alpha pairs are evaluated. Select lexicographic max(source_pu,alpha) among feasible pairs; require a separate clean 96-slot independent replay before final authority. No feasible pair: stop with null authority. No tuning or grid refinement.',source_execution='Five isolated worker processes, one per source. Each scans descending alpha; every pair has a fresh engine, and its 96 snapshots run sequentially with accepted control-state carry-forward. Completion order is never a selection input.',verification_rule='A separate clean Python process replays the selected pair for 96 chronological snapshots, using scalar bus/element APIs to independently reconstruct all hard-limit measurements. Require all hard limits and convergence/settling, phase-array differences <=1e-10 pu, and identical accepted regulator tap/cap states; otherwise stop without authority or tuning.',production_tuning_after_results_allowed=False,B1_B2_B3_execution_in_this_task=False)
    (H/'SOURCE_GRID_RULE.json').write_text(json.dumps(rule,indent=2),encoding='utf-8')
    # Keep a readable local control-state collector; change only the expected source check.
    source=(PREV/'screen_compatible_b0.py').read_text(encoding='utf-8');tree=ast.parse(source)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='control_state')
    code=ast.get_source_segment(source,node).replace('def control_state(d,t):','def control_state(d,t,expected_source):').replace('assert source==1.05','assert source==expected_source')
    (H/'control_telemetry.py').write_text('import numpy as np\n\n'+code+'\n',encoding='utf-8')
    # Retain the previous four authorized edits verbatim by reference.
    for source_pu in rule['source_grid_descending']:
        (H/f'Source_{source_pu:.3f}_Compatibility.dss').write_text(f'! Reduced-load compatibility adaptation, not canonical reproduction.\nRedirect "{PREV / "IEEE8500_Compatibility_Adaptation.dss"}"\nEdit Vsource.source pu={source_pu:.3f}\n',encoding='utf-8')
    print('Stage rule, control collector and five overlays constructed; no simulations run.')
if __name__=='__main__':main()
