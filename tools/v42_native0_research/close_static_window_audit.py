"""Close the single-window static research record without changing any source."""
from fractions import Fraction as F
import json
from select_current_thermal_window import OUT,read,rec

def main():
 packet=read(OUT/'CURRENT_THERMAL_LINE_WINDOW_STATIC_AUDIT.json')
 u4=read(OUT/'CURRENT_SELECTED_LINE_WINDOW_FRESH_U4_CONFIRMATION.json')
 proof=read(OUT/'CURRENT_PATH_SUPPORT_INDEPENDENT_REVIEW.json')
 history=read(OUT/'SOURCE19_MULTITIME_HISTORY_RECEIPT.json')
 generic=read(OUT/'GENERIC_EXACT_PATH_SUPPORT_INDEPENDENT_REVIEW.json')
 assert packet['PASS'] and u4['PASS'] and proof['PASS'] and history['PASS'] and generic['PASS']
 assert rec(proof['current_packet']['path'])==proof['current_packet']
 assert rec(proof['history']['path'])==proof['history'] and rec(proof['generic_theorem_and_fixture']['path'])==proof['generic_theorem_and_fixture']
 assert proof['source_SHA']==u4['source_SHA']==packet['current_validation_source_SHA']
 assert proof['case_SHA']==u4['case_SHA']==packet['current_case_SHA']
 assert proof['adoption']=='REJECTED_AS_ALREADY_IMPLIED_BY_EXISTING_FRACTIONAL_LP'
 assert proof['new_rows']==proof['new_columns']==proof['new_binary']==proof['new_NNZ']==proof['Native_calls']==0
 report=dict(PASS=True,schema='ONE_CURRENT_THERMAL_WINDOW_STATIC_RESEARCH_CLOSED_V1',
  verdict='MULTITIME_TIGHTENING_LB_UNPROVEN',parent_short_verdict='MULTITIME_LB_UNPROVEN',
  source19_base_git_head=history['base_git_head'],baseline_source_SHA=proof['source_SHA'],case_SHA=proof['case_SHA'],
  selected_branch=packet['selection']['branch_name'],branch_index=packet['selection']['branch_index'],
  window_start=72,window_end_exclusive=80,window_hours=2,
  current_fixed_only_peak_pressure=packet['selection']['fixed_only_peak'],
  authorized_fresh_U4_peak_pressure=u4['selected_window_peak_pressure'],
  authorized_fresh_U4_mean_slot_peak_pressure=u4['selected_window_mean_slot_peak_pressure'],
  authorized_fresh_U4_rho=u4['fresh_U4_rho'],
  candidate=proof['candidate'],integer_set_preservation=True,independent_valid_inequality_proof_PASS=True,
  candidate_already_implied_by_existing_fractional_LP=True,full96_DP_run=False,
  completed_current_unrestricted_Root_LP_point_available=False,actual_LP_violation=None,measured_LB_gain=None,
  adoption=False,new_rows=0,new_columns=0,new_binary=0,new_NNZ=0,
  mathematical_reason=proof['proof'],
  budget=packet['sparse_support_and_budget'],
  earlier_651_route_SOC_constraints_repeated=False,current_SVR11_fixed_controls_reaudited=True,
  prior_Source_LB_or_LP_points_reused=False,Native_calls=0,Native_Runtime=0,model_builds=0,source_edits=0,
  existing_C3A_Dense_and_physical_constraints_preserved=True,campaign_HOLD=True,Root180_gate_unchanged=True,
  receipts=[rec(OUT/n) for n in ('SOURCE19_MULTITIME_HISTORY_RECEIPT.json','CURRENT_THERMAL_LINE_WINDOW_STATIC_AUDIT.json',
   'CURRENT_SELECTED_LINE_WINDOW_FRESH_U4_CONFIRMATION.json','CURRENT_PATH_SUPPORT_INDEPENDENT_REVIEW.json','GENERIC_EXACT_PATH_SUPPORT_INDEPENDENT_REVIEW.json')])
 (OUT/'CURRENT_SINGLE_WINDOW_STATIC_CLOSURE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 lines=['# Current one-line/window static audit — closed','',
  '`MULTITIME_TIGHTENING_LB_UNPROVEN`. The priced all-horizon path-support direction is valid but already implied by the existing fractional LP. It is rejected; no new constraint is installed.','',
  'The current focus is `line.sw1::A` (branch3), slots72–79, a contiguous two-hour interval. It was chosen from current saved thermal coefficients and conservative reachable-site P/Q relief, rather than a historical slot. The authorized fresh U4 directly confirms high load on the selected80 retained Dense faces: peak0.650839453452 at slot76 and mean slot peak0.637805597992; fresh U4 rho is0.676053450465. Its raw vector and strict original FULL/96-slot physical replay are hash-bound. This integer feasible U4 point supplies no unrestricted Root LP violation witness.','',
  'FULL has128 selected-window thermal faces/480NNZ; current C3A and Dense each retain80faces/296NNZ with exactly unchanged stored coefficients. The eight active fixed-control face expressions project to2304 raw Pch/Pdis/Q terms. Selected32 SOC balance rows contain19264NNZ, including17664 travel occurrences. All-horizon travel energy alone has198986 coefficient occurrences, above the39556 additional-NNZ budget. These are support costs, not added rows.','',
  'Every finite IEEE value in the selected algebra is represented as an exact binary rational. The actual charge debit coefficient is4278419646001971/18014398509481984 and discharge debit is4740631186705785/18014398509481984. Initial and terminal SOC both equal760kWh; a path may terminate at any site at slot96. No return to the initial site is imposed. Outside-window charging, travel debits and terminal SOC recovery remain in the mathematical support bound.','',
  'For a nonnegative energy price, cancelling common charge and discharge preserves net P and Q and increases priced reward because discharge debit exceeds charge credit. The homogeneous stored PCS/connected inequalities then bound a fractional stay by its flow times the corresponding integer-mode support. Fractional unit DAG flow obeys the same maximum-path support bound by Bellman potentials. Summing all96 actual SOC equalities cancels the energy-price term since initial and terminal SOC match. Thus this direction holds at every point of the existing LP; it cannot supply the requested tightening. Independent current checks cover768 exact C=−D pairs and stored thermal, PCS and SOC algebra, supported by the current complete Native0 transport proof.','',
  'The primary audit of PR109–111,137,167,169,182 and185–187 completed before candidate review. Current SVR11 sensitivities and fixed controls differ from those historical problems, but the decisive net-power/PCS/fractional-flow structure persists. The651 earlier route–SOC rows were not repeated, and no large path formulation or complete pattern enumeration was built.','',
  'Completed current unrestricted Root LP point: unavailable (`ROOT_INCOMPLETE`). Actual LP violation and measured LB gain: unproven. Added rows/columns/binaries/NNZ:0/0/0/0. New Native calls/runtime:0/0seconds. Existing source and matrices remain unchanged, the May campaign remains HOLD and Root180 remains unmet.','',
  'Current baseline source SHA: '+proof['source_SHA']+'. Case SHA: '+proof['case_SHA']+'.']
 (OUT/'CURRENT_SINGLE_WINDOW_STATIC_CLOSURE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps(dict(PASS=True,verdict=report['verdict'],files=[str(OUT/'CURRENT_SINGLE_WINDOW_STATIC_CLOSURE.json'),str(OUT/'CURRENT_SINGLE_WINDOW_STATIC_CLOSURE.md')])))
if __name__=='__main__':main()
