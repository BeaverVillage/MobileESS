"""Read-only verification of the completed May campaign; write one audit receipt."""
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dayahead.v40a.invariants import validate_joint
from dayahead.v40b.common import CASES, DAYS, REPO, ROOT, now_utc, read, sha, write
from dayahead.v40b.recovery import certified_day, completed_case
from dayahead.v40b.reuse import validate_case_files
from dayahead.v40b.supervision import verify_freeze
from dayahead.v40d.policy import load_policy


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit():
    method, execution = verify_freeze()
    policy = load_policy(REPO)
    completion = read(ROOT / 'CAMPAIGN_COMPLETION.json')
    require(completion['status'] == 'PASS' and completion['completed_days'] == list(DAYS)
            and not completion['failed_days'] and completion['case_count'] == 124
            and completion['new_B3_count'] == 31, 'CAMPAIGN_NOT_COMPLETE')
    matrix = read(ROOT / 'V40B_MAY_EXECUTION_MATRIX.json')['rows']
    require(len(matrix) == 124 and {(r['day'], r['case']) for r in matrix}
            == {(d, c) for d in DAYS for c in CASES}, 'MATRIX_INCOMPLETE')
    by_case = {(r['day'], r['case']): r for r in matrix}
    counters, evidence = Counter(), []
    for day in DAYS:
        cert = certified_day(day, method['method_SHA'])
        require(cert is not None, 'MISSING_DAY:' + day)
        for case, item in cert['cases'].items():
            require(by_case[day, case]['status'] == item['status'], 'MATRIX_STATUS_DRIFT')
            path = Path(item['certificate'])
            child = read(path)
            counters[case + ':' + item['status']] += 1
            if item['status'] == 'REUSE_CERTIFIED':
                cp = Path(child['historical_checkpoint'])
                require(sha(cp) == child['historical_checkpoint_SHA'], 'REUSED_CHECKPOINT_DRIFT')
                validate_case_files(day, case, cp, Path(child['historical_case_root']))
            else:
                require(completed_case(day, case, method['method_SHA']) is not None,
                        'MISSING_COMPLETED_CASE')
            entry = {'day': day, 'case': case, 'status': 'PASS',
                     'origin': item['status'], 'certificate_SHA': sha(path)}
            if case == 'B3':
                base = path.parent
                joint = validate_joint(read(base / 'FINAL_JOINT_DECISION.json'))
                fresh = read(base / 'FRESH_AC_RESULT.json')
                actual = read(base / 'ACTUAL_FIXED_REPLAY.json')
                post = read(base / 'postfreeze/POSTFREEZE_VERIFICATION.json')
                planning = read(base / 'PLANNING_PHYSICAL_GATES.json')
                mobility = read(base / 'COOPT_MOBILITY_IDENTITY.json')
                terminal = read(base / 'COOPT_TERMINAL_AUDIT.json')
                runtime = read(base / 'COOPT_RUNTIME_PROFILE.json')
                firewall = read(base / 'COOPT_DATA_FIREWALL.json')
                require(joint == child['FINAL_JOINT_DECISION_SHA']
                        == fresh['FINAL_JOINT_DECISION_SHA'] == fresh['Fresh_schedule_sha256']
                        == actual['FINAL_JOINT_DECISION_SHA'] == actual['Fresh_FINAL_JOINT_DECISION_SHA']
                        == post['FINAL_JOINT_DECISION_SHA'] == planning['FINAL_JOINT_DECISION_SHA'],
                        'FINAL_DECISION_BINDING:' + day)
                require(all(x['status'] == 'PASS' for x in (actual, post, planning, mobility, terminal)),
                        'B3_AUDIT_FAILURE:' + day)
                require(mobility['M1_route_SHA'] == mobility['MF_route_SHA'] == mobility['final_route_SHA'],
                        'ROUTE_CHANGED:' + day)
                expected = {'MESS_FULL_DISCRETE_ROUTE_SEARCH_CALLS': 1,
                            'SECOND_MESS_FULL_ROUTE_SEARCH_CALLS': 0, 'AIDC_FEEDBACK_PASSES': 1,
                            'FINAL_FIXED_ROUTE_PQ_RECOURSE_CALLS': 1, 'FRESH_CALLS_INSIDE_COOPT_LOOP': 0}
                require(all(runtime[k] == v for k, v in expected.items()), 'COOPT_BOUND:' + day)
                require(firewall['active'] and all(firewall[k] == 0 for k in
                        ('Actual_reads_allowed_inside_loop', 'Fresh_reads_allowed_inside_loop',
                         'FRESH_CALLS_INSIDE_COOPT_LOOP')), 'FIREWALL:' + day)
                require(actual['DA_decision_SHA_expected'] == actual['DA_decision_SHA_verified']
                        and all(v == 0 for k, v in actual.items() if k.startswith('Actual_')),
                        'ACTUAL_REOPTIMIZATION:' + day)
                summary = fresh['summary']
                require(summary['convergence_count'] == 96 and not summary['physical_violation']
                        and all(summary[k] == 0 for k in ('voltage_violation_count',
                            'line_current_violation_count', 'transformer_current_violation_count',
                            'transformer_kva_violation_count')), 'FRESH_PHYSICAL_GATE:' + day)
                cap = 10 if child.get('AC_restoration_policy_sha256') == policy['policy_sha256'] else 5
                require(post['restoration_rounds'] <= cap and all(post[k] == 0 for k in
                        ('AIDC_changes_from_Fresh', 'mobility_changes_from_Fresh', 'route_search_calls')),
                        'POSTFREEZE_BOUND:' + day)
                entry.update(FINAL_JOINT_DECISION_SHA=joint, restoration_rounds=post['restoration_rounds'],
                             restoration_limit=cap, Fresh_coverage=96)
            evidence.append(entry)
        print('Verified', day, flush=True)
    require([counters[c + ':REUSE_CERTIFIED'] for c in CASES] == [18, 18, 17, 0], 'REUSE_COUNT')
    return {'status': 'PASS', 'checked_at_utc': now_utc(), 'days_passed': 31, 'cases_passed': 124,
            'new_B3_count': 31, 'counts': dict(counters), 'method_SHA': method['method_SHA'],
            'execution_SHA': execution['execution_SHA'], 'AC_restoration_policy_SHA': policy['policy_sha256'],
            'scientific_stop_rule_revision': 'USER_AUTHORIZED_MAX_RESTORATION_ROUNDS_5_TO_10',
            'May_failure_informed_revision': True,
            'Actual_scope': 'EXISTING_FIXED_DECISION_REPLAY_IDENTITY_GATE',
            'validation_scope': 'Stored result, source/input hashes, schema, physical gates and decision identity; no solver rerun',
            'cases': evidence}


if __name__ == '__main__':
    result = audit()
    output = REPO / 'dayahead/artifacts/v40d_ac_restoration/V40D_MAY_COMPLETION_AUDIT.json'
    write(output, result)
    print(result['status'], result['days_passed'], result['cases_passed'])
