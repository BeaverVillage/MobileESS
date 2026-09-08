"""Close the explicitly reduced gate without claiming untested search identity."""
from pathlib import Path
import sys,json,time,traceback
HERE=Path(__file__).resolve().parent;PROD=HERE.parent
sys.path.insert(0,str(PROD));from binding import *
from report_candidate import metric
import numpy as np
CLASS='PERFORMANCE_ONLY_EXACT_EQUIVALENT_ACCELERATION_PASS'
def main():
    verify_method();root=HERE/'selected_q_gate/2025-05-12/B3';r=read(root/'RESULT.json')
    assert r['status']=='COMPLETE' and r['audit_status']=='PASS' and r['slots']==96 and r['old_selected_Q_evaluations']==96
    assert r['old_full_day_search_selection_equivalence_not_claimed'] and not r['full_prefix_fallback']
    assert r['performance_engine_SHA']==sha(HERE/'cached_engine.py') and r['scientific_method_SHA']==sha(PROD/'METHOD_FREEZE.json')
    previous=read(HERE/'FULL_EQUIVALENCE_RESULT.json');assert previous['audit_status']=='PASS' and previous['all_Q_trials_identical_order_and_bit_identical_outputs'] and previous['accepted_Q_bit_identical']
    a=arrays(root/'OLD_SELECTED_Q_ONLY/OPENDSS_PHASE_ARRAYS.npz');b=arrays(root/'LIGHTWEIGHT/OPENDSS_PHASE_ARRAYS.npz')
    assert all(np.array_equal(a[k],b[k],equal_nan=True) if a[k].dtype.kind not in 'US' else np.array_equal(a[k],b[k]) for k in a)
    assert metric(a)==metric(b)
    old=read(root/'OLD_SELECTED_Q_ONLY/SELECTED_TRIALS.json');assert len(old)==96
    for t,e in enumerate(old):
        chosen=read(root/'LIGHTWEIGHT'/f'SLOT_{t:02}.json')
        assert e['Q']==chosen['selected_Q'] and e['start_taps']==chosen['start_taps'] and e['final_taps']==chosen['final_taps']
    assert all(sha(p)==h for p,h in read(root/'INPUT_HASHES.json').items())
    files={str(p):sha(p) for p in root.rglob('*') if p.is_file()}
    files.update({str(HERE/n):sha(HERE/n) for n in ['RESULT.json','TRIAL_COMPARISONS.json','FULL_EQUIVALENCE_RESULT.json','cached_engine.py','SELECTED_Q_GATE_AUTHORITY.json','selected_q_gate.py']})
    checks={name:True for name in ['selected_96_Q_exact_engine_acceptance','voltage_arrays','line_currents_loadings','transformer_current_kVA','start_final_taps','final_violation_counts','P_EXEC_SoC_energy_identity','scientific_search_unchanged','no_heavy_fallback']}
    g=dict(status='PASS',classification=CLASS,at=time.time(),day='2025-05-12',policy='B3',slots=96,checks=checks,validation_scope=r['gate_scope'],old_full_day_search_selection_equivalence_not_claimed=True,performance_engine_SHA=r['performance_engine_SHA'],scientific_method_SHA=r['scientific_method_SHA'],runtime=r,final_metrics=metric(b),files=files,prior_full_search_evidence=previous)
    save(HERE/'MAY12_FINAL_EQUIVALENCE_GATE.json',g)
    report=f'''# May12 B3 reduced acceleration acceptance gate

{CLASS}

Validation scope authorized by the user: one complete lightweight robust-Q search over 96 sequential slots, followed by 96 clean-engine full-prefix evaluations at the selected Q vectors. All selected-point voltage, line-current/loading, transformer-current/kVA, start/final tap arrays and final violation counts match bit-for-bit. P_EXEC and SoC/energy remain identical to the common eta=0.95 baseline.

This gate does **not** prove that an independently executed old full-day search would choose the same Q at every slot. No such search was completed or claimed. Prior 55-point/reverse-order evidence and the separately completed 4,558-candidate May12 slot30 exact search comparison remain supporting evidence. Scientific Q search rules are unchanged.

- Lightweight complete search: {r['lightweight_robust_search_seconds']:.3f} seconds.
- Lightweight mean candidate: {r['lightweight_seconds_per_candidate']:.6f} seconds.
- Lightweight mean intervention slot: {r['lightweight_seconds_per_intervention_slot']:.3f} seconds.
- Old exact selected-96-point validation: {r['old_selected_Q_validation_seconds']:.3f} seconds.
- Lightweight peak working set: {r['lightweight_peak_working_set_GB']:.3f} GB.
- Intervention slots: {len(r['intervention_slots'])}; unresolved slots: {len(r['unresolved_slots'])}.

No full-day search speedup is claimed because the old full-day search was cancelled. The previously measured slot30 search speedup was {previous['intervention_speedup']:.2f}x.
'''
    (HERE/'MAY12_FINAL_EQUIVALENCE_REPORT.md').write_text(report,encoding='utf-8')
    from adopt_lightweight import adopt
    adopted=adopt()
    save(HERE/'SELECTED_Q_GATE_AND_ADOPTION_COMPLETE.json',dict(status='COMPLETE',audit_status='PASS',classification=CLASS,gate_SHA=sha(HERE/'MAY12_FINAL_EQUIVALENCE_GATE.json'),adoption=adopted))
if __name__=='__main__':
    try:main()
    except BaseException as exc:
        save(HERE/'SELECTED_Q_CLOSURE_FAILURE.json',dict(status='FAIL_CLOSED',error=repr(exc),traceback=traceback.format_exc()));raise
