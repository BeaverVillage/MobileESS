"""Audit arithmetic and launch protection only; never run optimization."""
import ast
import csv
import json
from pathlib import Path
import tempfile
import unittest

from dayahead.tools import audit_v39h_terminal_state as audit
from dayahead.tools.v39h_terminal_launch_gate import admission, GATE


class TerminalAuditTests(unittest.TestCase):
    def test_half_open_boundary(self):
        self.assertEqual(audit.occupancy_parts(110,120,4),{"pre":0,"in":40,"post":0})
        self.assertEqual(audit.occupancy_parts(120,125,4),{"pre":0,"in":0,"post":20})

    def test_tail_escape_without_new_start_or_completion(self):
        before=audit.occupancy_parts(112,136,1)
        after=audit.occupancy_parts(118,142,1)
        self.assertEqual((after["post"]-before["post"])*.25,1.5)
        self.assertFalse(112<120<=118)
        self.assertFalse(136<=120<142)

    def test_in_out_work_conservation(self):
        for start,end,gpu in ((0,10,4),(12,130,32),(120,500,8),(90,200,1)):
            self.assertEqual(sum(audit.occupancy_parts(start,end,gpu).values()),(end-start)*gpu)

    def test_gate_live_hold_and_unaffected(self):
        for day in ("2025-05-24","2025-05-25","2025-05-26"):
            self.assertFalse(admission(audit.REPO,day)["release"])
        for day in ("2025-05-17","2025-05-23","2025-05-27","2025-05-31"):
            self.assertTrue(admission(audit.REPO,day)["release"])

    def test_gate_missing_invalid_and_incomplete_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="terminal_gate_test_") as directory:
            root=Path(directory)
            self.assertFalse(admission(root,"2025-05-24")["release"])
            self.assertFalse(admission(root,"2025-05-25")["release"])
            target=root/GATE
            target.parent.mkdir(parents=True)
            target.write_text("invalid",encoding="utf-8")
            self.assertFalse(admission(root,"2025-05-25")["release"])
            target.write_text(json.dumps({"audit_complete":False,"dates":{"2025-05-25":{"release":True}}}),encoding="utf-8")
            self.assertFalse(admission(root,"2025-05-25")["release"])
            target.write_text(json.dumps({"audit_complete":True,"dates":{"2025-05-25":{"release":True}}}),encoding="utf-8")
            self.assertTrue(admission(root,"2025-05-25")["release"])

    def test_guard_precedes_actual_and_runtime_initialization(self):
        source=(audit.REPO/"dayahead/tools/run_v39e_may_day.py").read_text()
        main=source[source.index("def main()") :]
        self.assertLess(main.index("wait_for_admission(args"),main.index("_install_windows_safe_k_archive()"))
        self.assertLess(main.index("wait_for_admission(args"),main.index("result = run_day_with_unavailable_da"))

    def test_audit_does_not_call_solvers_or_actual(self):
        tree=ast.parse(Path(audit.__file__).read_text())
        forbidden={"optimize","run_day","run_case","run_fresh_opendss","run_campaign","materialize_day","full_preflight"}
        calls={getattr(n.func,"attr",getattr(n.func,"id","")) for n in ast.walk(tree) if isinstance(n,ast.Call)}
        self.assertFalse(calls & forbidden)

    def test_all_95_changed_jobs_and_independent_arithmetic(self):
        with (audit.ROOT/"CHANGED_STANDBY_JOB_BOUNDARY_AUDIT.csv").open(encoding="utf-8-sig",newline="") as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),95)
        expected={"17":0.,"23":0.,"24":4.5,"25":1392.,"26":392.}
        for suffix,value in expected.items():
            selected=[r for r in rows if r["day"].endswith(suffix)]
            total=0
            for row in selected:
                gpu=int(row["GPU_request"])
                before=gpu*max(0,int(row["RSP_completion_slot"])-max(120,int(row["RSP_start_slot"])))
                after=gpu*max(0,int(row["repair_completion_slot"])-max(120,int(row["repair_start_slot"])))
                self.assertEqual(after-before,int(row["incremental_post_midnight_GPU_slots"]))
                total+=after-before
            self.assertEqual(total*.25,value)
        self.assertEqual(sum(r["newly_post_midnight_completion"]=="True" for r in rows),2)

    def test_result_and_physical_scope(self):
        result=json.loads((audit.ROOT/"TERMINAL_AUDIT_FINAL_STATUS.json").read_text())
        self.assertEqual(result["FINAL_CLASSIFICATION"],"TERMINAL_STATE_INCONSISTENCY_FOUND")
        self.assertEqual(result["NEXT_DAY_CARRY_CONSISTENT"],"NO")
        self.assertEqual(result["OUT_OF_DOMAIN_GRID_CERTIFICATION"],"NO")
        self.assertEqual(result["DOUBLE_COUNT"],"NO")
        for suffix in ("24","25","26"):
            self.assertEqual(result["MAY"+suffix+"_RELEASE"],"NO")
        gate=json.loads((audit.REPO/GATE).read_text())
        self.assertEqual(gate["audit_result_SHA256"],audit.sha(audit.ROOT/"TERMINAL_AUDIT_FINAL_STATUS.json"))
        for key in ("primary_optimization_calls","migration_MILP_calls","physical_grid_solver_calls","Actual_execution_calls"):
            self.assertEqual(result[key],0)
        self.assertTrue(all(r["loader_PCC_exact_match"] for r in result["loader_checks"]))


if __name__=="__main__":
    unittest.main(verbosity=2)
