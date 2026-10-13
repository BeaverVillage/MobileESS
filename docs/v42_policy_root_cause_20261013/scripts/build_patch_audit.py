"""Package controlled before/after proof; never rewrite production evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

B = Path('D:/v42_policy_root_cause_20261013')
C = Path('D:/v42_policy_root_cause_fix_20261013')
OUT = B/'audit'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def record(path):
    path = Path(path)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def write(name, body):
    (OUT/name).write_text(json.dumps(body,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


before = read(OUT/'fixtures/BEFORE_REPLAY.json')
after = read(OUT/'fixtures/AFTER_REPLAY.json')
comparisons = []
for old, new in zip(before['cases'], after['cases']):
    assert old['name'] == new['name'] and old['public_input_sha'] == new['public_input_sha']
    comparisons.append(dict(name=old['name'], exact_same_public_input_sha=old['public_input_sha'], before=old, after=new))
snapshot = read(OUT/'SOURCE_SNAPSHOT.json')
mismatches = [r['relative'] for r in snapshot['files'] if hashlib.sha256(Path(r['path']).read_bytes()).hexdigest() != r['sha256']]
assert not mismatches
freeze_path = C/'docs/v42_policy_root_cause_20261013/SOURCE_FREEZE_POLICY_FIX_V6.json'
freeze = read(freeze_path)
head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=C,text=True).strip()
assert head == freeze['base_commit'] == '8f0ea6e8f97147bb425530e8d787ca89f4a05053'
diff = subprocess.check_output(['git','diff','--no-ext-diff','--','v42_integration/sensitivity_policy.py'],cwd=C,text=True)
subprocess.run(['git','diff','--check'],cwd=C,check=True,capture_output=True)
xml_path = OUT/'fixtures/PATCH_FOCUSED_TESTS.xml'
xml = ET.parse(xml_path).getroot()
cases = list(xml.iter('testcase'))
failed = list(xml.iter('failure')) + list(xml.iter('error'))
new_count = sum('test_v42_policy_root_cause_regressions' in case.attrib.get('classname','') for case in cases)
assert len(cases) == 40 and new_count == 16 and not failed
common = dict(base_commit=head, previous_executed_source_sha=snapshot['source_sha'],
              followup_source_sha=freeze['source_sha'], source_epoch_scope=freeze['purpose'],
              May01_V5_policy_status='POLICY_COMPILER_ONLY', May01_optimized_control_effect='NOT_ESTABLISHED',
              production_V6_A_M_Actual_Fresh='NOT_RUN', Native_Optimize_calls=0, AC_calls=0,
              campaign_HOLD=True, campaign_auto_restart_authorized=False)
write('CONTROL_POLICY_FIX_DIFF_AUDIT.json', dict(schema='CONTROL_POLICY_FIX_DIFF_AUDIT_V1',
      status='MINIMAL_MASKED_BUG_FIX_SOURCE_ONLY', **common,
      source_files=[dict(relative='v42_integration/sensitivity_policy.py', before=record(B/'v42_integration/sensitivity_policy.py'),
                         after=record(C/'v42_integration/sensitivity_policy.py')),
                    dict(relative='tests/test_v42_policy_root_cause_regressions.py', before=None,
                         after=record(C/'tests/test_v42_policy_root_cause_regressions.py'))],
      exact_tracked_source_diff=diff,
      changed_conditions=['PENDING batch authority moves from universal lookup to positive intentional delay candidate',
                          'Explicit PREPLACE requires can_prestart_place=True even source_site=None',
                          'Capacity upper/lower feasibility uses total[slot:] matching remaining grid horizon'],
      preserved=['confirmed nonprotected policy scope','RUNNING/migration protection and batch rights',
                 'immutable QoS budget/allowed starts','GPU/Rack/WAN/checkpoint/1migration',
                 'all current/future grid and capacity constraints','CC4/Q50/Q90/kernel/model values',
                 'source private durations','common Actual engine and power materializer'],
      difference_check_PASS=True, source_snapshot_1779_files_unchanged=True))
write('CONTROL_POLICY_BEFORE_AFTER_REPLAY.json', dict(schema='CONTROL_POLICY_BEFORE_AFTER_REPLAY_V1',
      status='PASS_SAME_CONTROLLED_PUBLIC_INPUTS', **common, named_synthetic_only=True,
      real_May01_failure_read_only_load=dict(policy_sha=before['frozen_real_V5_policy_load_identical_sha'],
          after_policy_sha=after['frozen_real_V5_policy_load_identical_sha'],
          before_ordered=before['frozen_real_V5_ordered_actions'], after_ordered=after['frozen_real_V5_ordered_actions'],
          note='V5 file load/read-only reproduction only. No V6 May recompilation or Actual execution.'),
      comparisons=comparisons, input_receipts=[record(OUT/'fixtures/BEFORE_REPLAY.json'),record(OUT/'fixtures/AFTER_REPLAY.json')],
      before_after_runner=record(OUT/'scripts/replay_patch_conditions.py')))
write('CONTROL_POLICY_PATCH_VALIDATION.json', dict(schema='CONTROL_POLICY_PATCH_VALIDATION_V1',
      status='PASS_CONTROLLED_REGRESSION_ONLY', **common, focused_tests_passed=40,
      new_parametrized_cases=16, unchanged_existing_cases=24, failures=0,
      baseline_existing_focused_tests_passed=24,
      baseline_note='Baseline24 proves existing regression tests. Novel bug failure proof uses direct identical-input before/after JSON, not a claim that all16 new cases failed before.',
      checks=dict(same_input_before_after=True, immutable_B_snapshot_hashes=True,
                  action_specific_zero_delay_placement_rights=True, positive_delay_batch_rights=True,
                  source_none_no_placement_permission_rejected=True, protection_scope_preserved=True,
                  running_rights_preserved=True, current_future_Q90_overload_rejected=True,
                  whole_gang_reservation_reload=True, online_global_optimizer_calls_zero=True,
                  source_budget_ledger_untouched=True, source_model_forecast_values_untouched=True),
      source_freeze=record(freeze_path), focused_tests=record(xml_path),
      small_fixture_results=record(OUT/'CONTROL_POLICY_SMALL_FIXTURE_RESULTS.json'),
      snapshot_rechecked_files=len(snapshot['files']), snapshot_mismatches=mismatches))
print(json.dumps({'status':'PASS','tests':40,'new_cases':16,'V6_source':freeze['source_sha'],
                  'snapshot_rechecked':len(snapshot['files']),'same_input_comparisons':len(comparisons)}))
