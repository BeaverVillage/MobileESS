"""Evidence admission and physical measurements for the Vmax diagnostic report."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from v42_vmax1048 import report
from v42_common_reporting import report as common


class VmaxReportTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix="vmax_report_",dir=r"D:\v42_common_report_repair_20261010\test_temp")
        self.root=Path(self.directory.name)
        self.authority=self.root/"LINE_CURRENT_AUTHORITY_UNCHANGED.csv"
        with self.authority.open("w",newline="",encoding="utf8") as stream:
            writer=csv.DictWriter(stream,["branch_phase","NormalAmps","EmergAmps"]);writer.writeheader()
            writer.writerows(dict(branch_phase=f"line.l{i}::A",NormalAmps=100,EmergAmps=150) for i in range(263))
        self.authority_patch=patch.object(common,"AUTHORITY",self.root);self.authority_patch.start()
        self.addCleanup(self.authority_patch.stop);self.addCleanup(self.directory.cleanup)
        self.old=self.make_result(self.root/"original")
        self.attempt=self.root/"dates/B2/2025-05-01/attempts"/report.ATTEMPT
        self.new=self.make_result(self.attempt)
        self.manifest=dict(execution_SHA="epoch-source",planning_policy=report.POLICY,planning_voltage_min_pu=.95,
            planning_voltage_max_pu=1.048,planning_voltage_max_squared_pu=1.098304,
            actual_voltage_min_pu=.95,actual_voltage_max_pu=1.05,original_May01_result=common.record(self.old),
            line_current_authority_csv=str(self.authority),diagnostic_only=True)
        common.write_json(self.root/"VMAX1048_DIAGNOSTIC_MANIFEST.json",self.manifest)
        self.audit=self.root/"audit";self.audit.mkdir()
        common.write_csv(self.audit/"B2_MAY01_VOLTAGE_VIOLATIONS.csv",[dict(node_phase="mess_sta08_pcc.1",node_axis_0based=0,slot_0based=0)])

    def plan(self):
        values={}
        for slot in range(96):
            values.update({f"Pch[MESS01,STA08,{slot}]":2.,f"Pdis[MESS01,STA08,{slot}]":1.,f"Q[MESS01,STA08,{slot}]":3.})
        return dict(values=values,unit_ids=["MESS01"],P_kw=[[-1.]]*96,Q_kvar=[[3.]]*96,
            routes=[dict(unit="MESS01",source="STA08",destination="IDC01",depart=4,arrive=6,connect=6,energy_kwh=7),
                dict(unit="MESS01",source="IDC01",destination="STA08",depart=8,arrive=10,connect=10,energy_kwh=5)])

    def make_result(self,folder):
        output=folder/"output";fresh=output/"OPERATIONS/FRESH/fresh";fresh.mkdir(parents=True,exist_ok=True)
        raw=fresh/"OPENDSS_PHASE_ARRAYS.npz"
        np.savez(raw,node_names=np.array(["mess_sta08_pcc.1"]+[f"bus{i}.1" for i in range(385)]),node_phases=np.array(["A"]*386),
            branch_names=np.array([f"line.l{i}" for i in range(263)]+[f"transformer.tx{i}" for i in range(120)]),
            branch_phases=np.array(["A"]*383),branch_kinds=np.array(["line"]*263+["transformer"]*120),
            voltage_pu=np.ones((96,386)),convergence=np.ones(96,bool),phase_current_a=np.full((96,383),60.),
            phase_current_loading_pu=np.full((96,383),.6),transformer_total_kva_loading_pu=np.full((96,383),.5),
            regulator_taps=np.ones((96,7)),capacitor_states=np.ones((96,4),int))
        stage=output/"M_STAGE_RESULT.json";common.write_json(stage,dict(feasible_accepted=True,PASS=True,verified_UB=.5,source_SHA="epoch-source",
            scientific_case_sha="case",matrix_sha="matrix",domain_sha="domain",C3A_matrix_sha="selected-matrix",C3A_domain_sha="selected-domain"))
        plan=output/"OPTIMIZED_MESS_PLAN.json";common.write_json(plan,self.plan())
        ledger=folder/"NATIVE_RUNTIME_LEDGER.json";common.write_json(ledger,dict(measured_Native_Runtime=21.,inflight=None,calls=[dict(status="FINISHED")]))
        observer=output/"ACTUAL_FRESH_CONTROL_OBSERVER.json"
        slots=output/"ACTUAL_FRESH_CONTROL_SLOTS.json"
        common.write_json(slots,[dict(slot=i,taps=[1.]*7,control_actions_done=True,control_iterations=3,converged=True,
            seven_RegControls_enabled=True,capacitor_states=[1,1,1,1],CapControl_count=0,
            source_parameters_equal_to_original=True,Planning_tap_cap_replay=False,
            Solution_Iterations_total=9,Solution_MostIterationsDone_per_control_pass=3,
            regulator_settings_SHA="3e4aaaabc10429aa2e95f810573337bdbdbb4d6ca4aeda41ae51d0325cf322cf") for i in range(96)])
        common.write_json(observer,dict(PASS=True,slots=96,control_actions_done_slots=96,converged_slots=96,
            execution_source_SHA="epoch-source",regulator_settings_SHA="3e4aaaabc10429aa2e95f810573337bdbdbb4d6ca4aeda41ae51d0325cf322cf",
            Actual_voltage_limits_pu=[.95,1.05],control_settings_changed=False,tap_or_cap_setters_added=False,
            original_Fresh_and_96_slot_body_unchanged=True,original_source_SHA_before_after_equal=True,slots_receipt=common.record(slots)))
        policy=output/"VMAX1048_MODEL_POLICY_AUDIT.json"
        common.write_json(policy,dict(PASS=True,audit=dict(PASS=True),scientific_case_sha="case",original_matrix_sha="matrix",
            original_domain_sha="domain",selected_matrix_sha="selected-matrix",selected_domain_sha="selected-domain",policy=dict(version=report.POLICY,
            Planning_upper_squared=1.098304,Planning_lower_squared=.9025,Actual_upper_pu=1.05)))
        result=folder/"RESULT.json"
        common.write_json(result,dict(status="COMPLETED",PASS=True,actual_ac_physical_pass=True,planning_policy=report.POLICY,
            source_SHA="epoch-source",source_sha="inner-seal",files=[common.record(stage),common.record(plan),common.record(raw)],
            native_ledger=common.record(ledger),Native_Runtime=999,actual_control_observer=common.record(observer),
            planning_model_policy_audit=common.record(policy),evaluation=dict(Fresh=dict(PASS=True,folder=str(fresh.parent),raw_arrays=common.record(raw)),
                summary=dict(voltage_violation_count=0,line_current_violation_count=0,transformer_current_violation_count=0,transformer_kva_violation_count=0))))
        return result

    def case(self):
        errors=[];case,_,_=report._case(self.new,self.manifest,"VMAX1048_DIAGNOSTIC",{},errors)
        return case,errors

    def change_result(self,**updates):
        value=common.read(self.new);value.update(updates);common.write_json(self.new,value)

    def replace_raw(self,**updates):
        value=common.read(self.new);raw=Path(value["evaluation"]["Fresh"]["raw_arrays"]["path"])
        with np.load(raw) as archive:arrays={k:archive[k] for k in archive.files}
        arrays.update(updates);np.savez(raw,**arrays)
        value["files"]=[common.record(raw) if r["path"]==str(raw.resolve()) else r for r in value["files"]]
        value["evaluation"]["Fresh"]["raw_arrays"]=common.record(raw)
        common.write_json(self.new,value)

    def test_measured_pass_requires_all_declared_evidence(self):
        case,errors=self.case();self.assertEqual(errors,[]);self.assertTrue(case["Full_AC_Physical_PASS"])
        self.assertEqual(case["actual"]["metric"]["actual_maximum_line_loading_percent"],60.)
        self.assertEqual(case["Native_Runtime_seconds"],21.)
        self.assertTrue(case["source_match"])

    def test_wrong_execution_source_cannot_pass_even_inner_seal_matches(self):
        self.change_result(source_SHA="wrong",source_sha="epoch-source")
        case,errors=self.case();self.assertFalse(case["source_match"]);self.assertFalse(case["Full_AC_Physical_PASS"])

    def test_physical_violation_overrules_fresh_completion(self):
        voltage=np.ones((96,386));voltage[:19,0]=1.06;self.replace_raw(voltage_pu=voltage)
        value=common.read(self.new);value["evaluation"]["summary"]["voltage_violation_count"]=19;common.write_json(self.new,value)
        case,errors=self.case();self.assertEqual(errors,[]);self.assertEqual(case["actual"]["voltage_violation_count"],19)
        self.assertFalse(case["Full_AC_Physical_PASS"])

    def test_summary_zero_cannot_hide_raw_voltage_failure(self):
        self.replace_raw(voltage_pu=np.full((96,386),1.06))
        case,errors=self.case();self.assertIsNone(case["actual"]["physical_pass"])
        self.assertIn("RAW_VIOLATION_COUNT_SUMMARY_MISMATCH",errors[-1]["error"])

    def test_changed_raw_receipt_is_rejected_even_ratio_consistent(self):
        value=common.read(self.new);raw=Path(value["evaluation"]["Fresh"]["raw_arrays"]["path"])
        with np.load(raw) as archive:arrays={k:archive[k] for k in archive.files}
        arrays["phase_current_a"]=np.full((96,383),50.);arrays["phase_current_loading_pu"]=np.full((96,383),.5)
        np.savez(raw,**arrays)
        case,errors=self.case();self.assertIsNone(case["Full_AC_Physical_PASS"])
        self.assertTrue(any("DECLARED_FILE_SHA" in e["error"] for e in errors))

    def test_missing_control_completion_receipt_prevents_pass(self):
        value=common.read(self.new);path=Path(value.pop("actual_control_observer")["path"]);path.unlink();common.write_json(self.new,value)
        case,_=self.case();self.assertFalse(case["Full_AC_Physical_PASS"])

    def test_wrong_squared_voltage_identity_prevents_pass(self):
        self.manifest["planning_voltage_max_squared_pu"]=1.048
        case,_=self.case();self.assertFalse(case["planning_policy_identity_validated"]);self.assertFalse(case["Full_AC_Physical_PASS"])

    def test_inflight_native_cost_is_unknown_not_envelope_or_zero(self):
        value=common.read(self.new);path=Path(value["native_ledger"]["path"]);ledger=common.read(path);ledger["inflight"]={"label":"running"}
        common.write_json(path,ledger);value["native_ledger"]=common.record(path);common.write_json(self.new,value)
        case,_=self.case();self.assertIsNone(case["Native_Runtime_seconds"])

    def test_fresh_95_of_96_cannot_pass(self):
        convergence=np.ones(96,bool);convergence[95]=False;self.replace_raw(convergence=convergence)
        case,_=self.case();self.assertFalse(case["Full_AC_Physical_PASS"])

    def test_missing_original_voltage_axis_is_not_physical_pass(self):
        self.replace_raw(voltage_pu=np.ones((96,385)),node_names=np.array([f"bus{i}.1" for i in range(385)]))
        case,errors=self.case();self.assertIsNone(case["Full_AC_Physical_PASS"])
        self.assertIn("ALL_96_SLOT_FINITE_RAW_VOLTAGES_REQUIRED",errors[-1]["error"])

    def test_charge_discharge_literal_coordinates_and_routes(self):
        statistics=report.dispatch_statistics(self.plan())
        self.assertEqual(statistics["charge_energy_kwh"],48.);self.assertEqual(statistics["discharge_energy_kwh"],24.)
        self.assertEqual(statistics["reactive_absolute_energy_kvarh"],72.)
        self.assertEqual(statistics["movement_count"],2);self.assertEqual(statistics["movement_energy_kwh"],12.)

    def test_missing_coordinate_is_not_assumed_zero(self):
        plan=self.plan();del plan["values"]["Pch[MESS01,STA08,95]"]
        with self.assertRaisesRegex(ValueError,"ALL_96_UNIT"):report.dispatch_statistics(plan)

    def test_not_run_writes_all_eight_outputs_and_blank_comparison(self):
        self.new.unlink()
        summary=report.write_reports(self.root,audit_root=self.audit)
        self.assertEqual(summary["status"],"NOT_RUN");self.assertEqual(len(summary["files"]),8)
        self.assertIsNone(summary["Planning_UB"]);self.assertIsNone(summary["Full_AC_Physical_PASS"])
        with (self.root/report.FILENAMES[1]).open(encoding="utf-8-sig") as stream:rows=list(csv.DictReader(stream))
        self.assertTrue(all(r["VMAX1048_diagnostic"]=="" for r in rows))
        self.assertIn("NOT_RUN",(self.root/report.FILENAMES[0]).read_text(encoding="utf8"))

    def test_new_measured_taps_are_separate_from_original(self):
        summary=report.write_reports(self.root,audit_root=self.audit)
        self.assertTrue(summary["Full_AC_Physical_PASS"])
        with (self.root/report.FILENAMES[3]).open(encoding="utf-8-sig") as stream:rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),672);self.assertEqual(rows[0]["new_Solution_MostIterationsDone"],"3")

    def test_nested_slot_receipt_or_model_mismatch_never_leaves_pass(self):
        value=common.read(self.new);observer=common.read(value["actual_control_observer"]["path"])
        slots_path=Path(observer["slots_receipt"]["path"]);slots=common.read(slots_path)
        slots[0]["control_actions_done"]=False;common.write_json(slots_path,slots)
        summary=report.write_reports(self.root,audit_root=self.audit)
        self.assertFalse(summary["Full_AC_Physical_PASS"])
        self.assertTrue(any("SHA" in r["error"] for r in summary["errors"]))
        validation=common.read(self.root/report.FILENAMES[7]);self.assertFalse(validation["new_Full_AC_Physical_PASS"])
        with (self.root/report.FILENAMES[1]).open(encoding="utf-8-sig") as stream:rows=list(csv.DictReader(stream))
        self.assertEqual(next(r for r in rows if r["metric"]=="Full AC Physical PASS")["VMAX1048_diagnostic"],"False")
        # A separately re-declared model audit still cannot disagree with the
        # stage's literal matrix/domain identity, even if its PASS flag is true.
        self.new=self.make_result(self.attempt)
        value=common.read(self.new);policy_path=Path(value["planning_model_policy_audit"]["path"])
        policy=common.read(policy_path);policy["original_matrix_sha"]="wrong-matrix";common.write_json(policy_path,policy)
        value["planning_model_policy_audit"]=common.record(policy_path);common.write_json(self.new,value)
        case,errors=self.case();self.assertFalse(case["Full_AC_Physical_PASS"])
        self.assertTrue(any("STAGE_MODEL_MATRIX_DOMAIN" in r["error"] for r in errors))
        self.new=self.make_result(self.attempt)
        (self.audit/"B2_MAY01_VOLTAGE_VIOLATIONS.csv").unlink()
        summary=report.write_reports(self.root,audit_root=self.audit)
        self.assertFalse(summary["Full_AC_Physical_PASS"])
        self.assertTrue(summary["errors"])


if __name__=="__main__":unittest.main()
