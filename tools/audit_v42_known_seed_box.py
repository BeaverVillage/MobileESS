"""Source descriptor and original electrical outer-box audit; no native model."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v42_integration.unified_contract import REPORT,load_contracts
from v42_integration.m_engine import _write


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=REPORT/'KNOWN_SEED_BOX_AUDIT01')
    args=parser.parse_args()
    raise SystemExit('KNOWN_SEED_DIAGNOSTICS_HOLD: current scope is Unknown site-only allocation.')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    from v42_integration.unified_resource import UnifiedResearchBudget
    from v42_integration.aidc_sensitivity_runtime import (build_new_unified_case,
        select_cc4_headroom_seed_choices,audit_seed_grid_outer_box)
    budget=UnifiedResearchBudget();_write(out/'RESOURCE_ADMISSION.json',budget.preflight())
    case=build_new_unified_case(out/'PREPARATION',shared_manifest=load_contracts())
    a=case.make_a_case('B1','A1',case.initial_mess,out/'DESCRIPTOR_ONLY')
    selected=select_cc4_headroom_seed_choices(a,issue_seconds=case.planning_slot_zero_seconds,
        pairs=21,output=out/'CURRENT_CHOICES.json')
    result=audit_seed_grid_outer_box(a,selected['override_plans'],
        output=out/'ORIGINAL_GRID_OUTER_BOX_RESULT.json')
    _write(REPORT/'KNOWN_SEED_GRID_OUTER_BOX_AUDIT.json',dict(result,output_path=str(out)))
    print(result['status'])


if __name__=='__main__':main()
