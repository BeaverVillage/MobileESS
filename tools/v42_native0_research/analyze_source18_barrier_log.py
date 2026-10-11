"""Read the frozen Source18r log; never import Gurobi or build an LP/MILP."""
from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, json, re, time

ROOT = Path(r'D:\v42_multitime_audit_20261011\root_barrier')
LOG = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output\FULL_ROOT_ONCE\NATIVE_GUROBI.log')
RESULT = LOG.with_name('RESULT.json')
EXPECTED_LOG_SHA = 'ae2dc49ed51950186f58bf3487d76134543881fe00ad9ff279dd5cbba83d78ed'

def receipt(path):
    b = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)}

def main():
    started = time.perf_counter()
    assert receipt(LOG)['sha256'] == EXPECTED_LOG_SHA
    log = LOG.read_text(encoding='utf-8-sig')
    result = json.loads(RESULT.read_text(encoding='utf-8-sig'))
    number = r'([-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)'
    pattern = re.compile(r'^\s*(\d+)\s+' + r'\s+'.join([number] * 5) + r'\s+(\d+)s\s*$', re.I | re.M)
    rows = []
    for m in pattern.finditer(log):
        values = m.groups()
        row = dict(zip(['iteration', 'primal_objective', 'dual_objective', 'primal_residual', 'dual_residual', 'complementarity', 'native_clock_seconds_rounded'],
                       [int(values[0]), *[float(v) for v in values[1:6]], int(values[6])]))
        row['primal_minus_dual_display'] = row['primal_objective'] - row['dual_objective']
        row['clock_delta_from_previous_printed_iteration'] = None if not rows else row['native_clock_seconds_rounded'] - rows[-1]['native_clock_seconds_rounded']
        rows.append(row)
    assert [r['iteration'] for r in rows] == list(range(57))
    assert all(r['clock_delta_from_previous_printed_iteration'] > 0 for r in rows[1:])
    assert rows[0]['native_clock_seconds_rounded'] == 117 and rows[-1]['native_clock_seconds_rounded'] == 602
    perf = re.search(r'Barrier performed (\d+) iterations in ([\d.]+) seconds \(([\d.]+) work units\)', log)
    assert perf and int(perf[1]) == 56
    assert 'Root relaxation: time limit, 0 iterations, 528.89 seconds' in log
    assert result['native_receipt']['root_completed'] is False and result['Native_status'] == 9
    assert result['native_log']['sha256'] == EXPECTED_LOG_SHA
    assert result['effective_TimeLimit'] == 600
    stats = {}
    for name, pat in {
        'ordering_seconds': r'Ordering time: ([\d.]+)s',
        'AA_prime_NZ_rounded': r"AA' NZ\s*:\s*([\d.e+]+)",
        'Factor_NZ_rounded': r'Factor NZ\s*:\s*([\d.e+]+)',
        'Factor_Ops_rounded': r'Factor Ops\s*:\s*([\d.e+]+)',
        'Dense_columns_count': r'Dense cols\s*:\s*(\d+)',
        'Threads': r'Threads\s*:\s*(\d+)',
    }.items():
        found = re.search(pat, log)
        assert found, name
        stats[name] = float(found[1])
    assert stats['Threads'] == 1
    segments = []
    for lo, hi in [(0,24),(24,47),(47,56),(51,56)]:
        a,b = rows[lo],rows[hi]
        segments.append({'first_iteration':lo,'last_iteration':hi,
                         'rounded_native_clock_delta':b['native_clock_seconds_rounded']-a['native_clock_seconds_rounded'],
                         'mean_printed_transition_clock_seconds':(b['native_clock_seconds_rounded']-a['native_clock_seconds_rounded'])/(hi-lo),
                         'start':a,'end':b,
                         'clock_is_not_factorization_profile':True})
    ROOT.mkdir(parents=True, exist_ok=True)
    out_csv = ROOT / 'SOURCE18R_BARRIER_ALL_ITERATIONS.csv'
    with out_csv.open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    mem = result['memory_after_native']
    out = {'schema':'SOURCE18R_CLOSED_LOG_NATIVE0_BARRIER_ANALYSIS_V1','PASS':True,
           'UTC':datetime.now(timezone.utc).isoformat(),
           'Model_Source_SHA':'146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8',
           'case_SHA':result['case_sha'],'log':receipt(LOG),'result':receipt(RESULT),
           'printed_iteration_rows':len(rows),'completed_iteration_steps':56,
           'iterations_csv':receipt(out_csv),'barrier_statistics':stats,
           'logged_factor_memory_estimate_MB':800,'measured_factor_allocation_bytes':'UNKNOWN',
           'logged_factor_iteration_seconds_estimate':2,'measured_exclusive_factor_seconds':'UNKNOWN',
           'barrier_summary_native_elapsed_seconds':float(perf[2]),
           'barrier_summary_work_units':float(perf[3]),
           'exclusive_Barrier_wall_seconds':'UNKNOWN',
           'root_relaxation_interrupted_seconds':528.89,
           'API_Native_Runtime':result['Native_Runtime'],'presolve_seconds':result['Presolve_seconds'],
           'inner_Root_presolved':{'rows':555551,'columns':397098,'NNZ':7903205},
           'MIP_presolved':{'rows':610100,'columns':354177,'NNZ':7998268},
           'root_completion':'ROOT_INCOMPLETE','root_completion_seconds':None,
           'Crossover_entered':False,'Crossover_seconds':None,
           'solver_ObjBound':result['Solver_ObjBound'],'solver_gap':result['Solver_MIPGap'],
           'completed_Root_LP_optimal_value':'UNKNOWN',
           'display_dual_exceeds_primal_iterations':[r['iteration'] for r in rows if r['dual_objective'] > r['primal_objective']],
           'display_objective_is_not_original_domain_primal_or_dual_certificate':True,
           'time_segments':segments,'milestones':[rows[i] for i in [0,13,24,30,40,47,51,52,53,54,55,56]],
           'memory_after_native':mem,
           'memory_scope':'process-lifetime peaks and post-native system snapshot; not concurrent phase peaks or Factor allocation',
           'numeric_warning_large_matrix_coefficient_range':'Warning: Model contains large matrix coefficient range' in log,
           'condition_number_pivot_counts_refinement_time':'UNKNOWN',
           'Native_optimize_calls':0,'Native_Runtime':0,'model_builds':0,'fullsize_LP_calls':0,
           'fullsize_MILP_calls':0,'Gurobi_presolve_calls':0,'parameter_sweeps':0,
           'analysis_script':receipt(Path(__file__)), 'analysis_wall_seconds_before_plot':time.perf_counter()-started}
    dest=ROOT/'SOURCE18R_BARRIER_CLOSED_LOG_ANALYSIS.json'
    dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    out['figure']='NOT_GENERATED_matplotlib_unavailable; full CSV and report milestones provided'
    out['total_analysis_wall_seconds']=time.perf_counter()-started
    dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'PASS':True,'rows':len(rows),'Native_calls':0,'wall_seconds':out['total_analysis_wall_seconds'],'receipt':receipt(dest)}))

if __name__=='__main__':main()
