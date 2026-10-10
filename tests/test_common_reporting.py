"""Scientific reporting checks, independent of any optimizer implementation."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from v42_common_reporting.report import (current_metric, execution_source, load_receipt,
    metric_from_result, record, stage_documents, stage_row, summarize)


class ReportingTests(unittest.TestCase):
    def raw(self, folder, amps=40.):
        p = Path(folder) / "OPENDSS_PHASE_ARRAYS.npz"
        p.parent.mkdir(parents=True, exist_ok=True)
        np.savez(p, branch_names=np.array(["transformer.t", "line.l"]),
            branch_phases=np.array(["A", "A"]), branch_kinds=np.array(["transformer", "line"]),
            phase_current_a=np.tile([90., amps], (96, 1)),
            phase_current_loading_pu=np.tile([9., amps / 50.], (96, 1)),
            convergence=np.ones(96, bool))
        return p

    def setup_campaign(self, root):
        line = root / "limits.csv"
        line.write_text("branch_phase,NormalAmps\nline.l::A,50\n")
        b0 = root / "B0.json"
        b0.write_text(json.dumps({"source_files": []}))
        baseline = root / "BASELINE.json"
        baseline.write_text(json.dumps({"B1_results": {}}))
        return {"algorithm_version": "V42_COMMON_MESS_PRIMAL_ANYTIME_U4_V1",
            "execution_SHA": "common-epoch", "line_current_authority_csv": str(line),
            "b0_reclassification": str(b0), "baseline_manifest": str(baseline), "B1_results": {}, "date_results": {}}

    def put_result(self, root, manifest, arm, day, *, passed=True, source="common-epoch", voltage=0):
        path = root / "dates" / arm / day / "attempts" / "fixture" / "RESULT.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = self.raw(path.parent / "output/OPERATIONS/FRESH/fresh")
        receipt = record(raw)
        result = dict(PASS=passed, status="COMPLETED_PHYSICAL_PASS" if passed else "IMPLEMENTATION_FAILURE",
            source_SHA=source, source_sha="inner-scientific-seal", worker_wall_seconds=42.75,
            Native_Runtime=12.5, files=[receipt], evaluation=dict(PASS=True,
                Fresh=dict(PASS=True, folder=str(raw.parent.parent), raw_arrays=receipt),
                summary=dict(voltage_violation_count=voltage, line_current_violation_count=0,
                    transformer_current_violation_count=0, transformer_kva_violation_count=0,
                    physical_violation=bool(voltage))))
        if arm == "B2":
            result["scientific"] = dict(feasible_accepted=True, verified_UB=.52, global_gap_certified=False)
        elif arm == "B3":
            result["stage_outputs"] = {name: dict(source_result=dict(feasible_accepted=True,
                verified_UB=upper, global_gap_certified=False), model_sha="typed-model")
                for name, upper in (("M1", .7), ("M2", .6))}
        else:
            result["fields"] = {"planning_rho_max": .5}
        path.write_text(json.dumps(result))
        refs = manifest["B1_results" if arm == "B1" else "date_results"]
        refs[arm + "/" + day] = record(path)
        return path, result, raw

    def test_current_metric_excludes_transformer_and_uses_amperes(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"raw.npz"
            amps=np.tile([90.,40.],(96,1))
            np.savez(p,branch_names=np.array(["transformer.t","line.l"]),branch_phases=np.array(["A","A"]),
                branch_kinds=np.array(["transformer","line"]),phase_current_a=amps,
                phase_current_loading_pu=np.tile([9.,.8],(96,1)),convergence=np.ones(96,bool))
            metric=current_metric(p,{"line.l::a":50.},{})
            self.assertEqual(metric["actual_maximum_line_loading_percent"],80.)
            self.assertEqual(metric["line_phase_count"],1)
            with self.assertRaisesRegex(ValueError,"DENOMINATOR_DRIFT"):
                current_metric(p,{"line.l::a":100.},{})

    def test_tampered_result_cannot_enter_comparison(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"RESULT.json";p.write_text('{"PASS":true}')
            receipt=record(p);p.write_text('{"PASS":false}')
            errors=[];value,_=load_receipt(receipt,{},errors)
            self.assertIsNone(value);self.assertEqual(len(errors),1)

    def test_declared_fresh_raw_receipt_rejects_changed_currents_without_summary_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = self.raw(root)
            expected = record(raw)
            evaluation = {"Fresh": {"raw_arrays": expected}}
            metric = metric_from_result({}, None, evaluation, {"line.l::a": 50.}, {}, [])
            self.assertEqual(metric["actual_maximum_line_loading_percent"], 80.)
            self.assertTrue(metric["raw_current_declared_sha_verified"])
            # The replacement is internally consistent with the same denominator,
            # so only the declared SHA catches this silent change in Fresh current.
            self.raw(root, amps=30.)
            errors = []
            metric = metric_from_result({}, None, evaluation, {"line.l::a": 50.}, {}, errors)
            self.assertEqual(metric, {})
            self.assertIn("SHA_OR_SIZE_MISMATCH", errors[0]["error"])

    def test_conflicting_result_and_fresh_raw_receipts_cannot_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = self.raw(folder)
            receipt = record(raw)
            stale = dict(receipt, sha256="0" * 64)
            errors = []
            metric = metric_from_result({"files": [stale]}, None,
                {"Fresh": {"raw_arrays": receipt}}, {"line.l::a": 50.}, {}, errors)
            self.assertEqual(metric, {})
            self.assertEqual(len(errors), 1)

    def test_b2_stage_result_is_bound_to_envelope_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            result_path = Path(folder) / "RESULT.json"
            stage = Path(folder) / "output/M_STAGE_RESULT.json"
            stage.parent.mkdir()
            stage.write_text(json.dumps({"feasible_accepted": True, "verified_UB": .5}))
            result = {"files": [record(stage)]}
            stage.write_text(json.dumps({"feasible_accepted": True, "verified_UB": .4}))
            errors = []
            stages = stage_documents(result, result_path, "B2", {}, errors)
            self.assertEqual(stages["M"], {})
            self.assertEqual(len(errors), 1)

    def test_feasible_without_global_bound_never_certified(self):
        r=stage_row("B2","2025-05-01","M",dict(feasible_accepted=True,verified_UB=.6,
            global_gap_certified=True,native_best_bound_diagnostic=.59),None)
        self.assertTrue(r["feasible_accepted"])
        self.assertFalse(r["global_gap_certified"])
        self.assertIsNone(r["certified_Global_LB"])

    def test_exact_zero_gap_is_preserved(self):
        r=stage_row("B2","2025-05-01","M",dict(feasible_accepted=True,verified_UB=.6,
            certified_Global_LB=.6,certified_gap=0.,global_gap_certified=True),None)
        self.assertEqual(r["certified_gap"],0.)
        self.assertTrue(r["global_gap_certified"])

    def test_b3_source_wrapper_keeps_failed_native_cost_and_fixed_identity(self):
        document={"source_result":{"feasible_accepted":True,"verified_UB":.6,"global_gap_certified":False,
                      "certified_Global_LB":None,"stage_wall_seconds":1850},
                  "model_sha":"model", "ledger_receipt":json.dumps({"measured_native_runtime":1800.3,
                      "fixed_input_sha":"fixed","source_sha":"source"}),
                  "global_evidence":{"exact_UB":"3/5","exact_LB":None,"global_gap_certified":False}}
        r=stage_row("B3","2025-05-01","M2",document,None)
        self.assertEqual(r["native_runtime_seconds"],1800.3)
        self.assertAlmostEqual(r["native_budget_overrun_seconds"],.3)
        self.assertEqual(r["fixed_input_sha"],"fixed")
        self.assertFalse(r["global_gap_certified"])
        self.assertIsNone(r["certified_Global_LB"])

    def test_execution_epoch_and_inner_scientific_seal_are_distinct(self):
        manifest = {"execution_SHA": "common-epoch", "source_sha": "old-source"}
        source, expected, matches, scientific = execution_source(
            {"source_SHA": "common-epoch", "source_sha": "inner-scientific-seal"}, manifest, "B3")
        self.assertEqual((source, expected, matches, scientific),
            ("common-epoch", "common-epoch", True, "inner-scientific-seal"))
        self.assertFalse(execution_source(
            {"source_SHA": "wrong-epoch", "source_sha": "common-epoch"}, manifest, "B3")[2])

    def test_aggregate_model_and_complete_domain_are_not_matrix_or_case_hashes(self):
        r = stage_row("B3", "2025-05-01", "A1", dict(source_result={}, model_sha="typed-model",
            global_evidence={"original_model_sha": "typed-model", "global_domain_sha": "complete-domain"}), None)
        self.assertEqual(r["model_sha"], "typed-model")
        self.assertEqual(r["complete_scientific_domain_sha"], "complete-domain")
        for key in ("matrix_sha", "domain_sha", "scientific_case_sha"):
            self.assertIsNone(r[key])
        m = stage_row("B3", "2025-05-01", "M2", dict(source_result=dict(
            scientific_case_sha="case", matrix_sha="full-matrix", domain_sha="full-domain",
            C3A_matrix_sha="c3a-matrix", C3A_domain_sha="c3a-domain",
            source_SHA="common-epoch", source_sha="inner-scientific-seal"), model_sha="typed-model"), None)
        self.assertEqual([m[key] for key in ("scientific_case_sha", "matrix_sha", "domain_sha", "C3A_matrix_sha", "C3A_domain_sha")],
            ["case", "full-matrix", "full-domain", "c3a-matrix", "c3a-domain"])
        self.assertEqual(m["source_sha"], "common-epoch")

    def test_current_stage_ledger_precedes_historical_source_native_runtime(self):
        r = stage_row("B3", "2025-05-01", "A1", dict(
            source_result={"Native_Runtime": 999., "native_seconds": 0.},
            ledger_receipt=json.dumps({"measured_native_runtime": 0.})), None)
        self.assertEqual(r["native_runtime_seconds"], 0.)

    def test_common_nested_final_m_upper_bound_and_source_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);manifest = self.setup_campaign(root)
            for arm in ("B1", "B2", "B3"):
                self.put_result(root, manifest, arm, "2025-05-01")
            path = root / "CAMPAIGN_MANIFEST.json";path.write_text(json.dumps(manifest))
            status = summarize(root)
            with (root / "reports/B2_B3_ACTUAL_COMPARISON.csv").open(encoding="utf-8-sig") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(float(row["B2_planning_rho_max"]), .52)
            self.assertEqual(float(row["B3_planning_rho_max"]), .6)
            self.assertEqual(float(row["B2_planning_to_actual_line_difference_pp"]), 28.)
            self.assertEqual(float(row["B3_planning_to_actual_line_difference_pp"]), 20.)
            completed = [r for r in status["dates"] if r["day"] == "2025-05-01"]
            self.assertTrue(all(r["source_match"] and r["official_pair_eligible"] for r in completed))
            self.assertTrue(all(r["scientific_source_SHA"] == "inner-scientific-seal" for r in completed))
            self.assertEqual(status["audit_errors"], [])

    def test_failed_or_wrong_source_envelope_is_excluded_but_diagnostic_and_cost_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);manifest = self.setup_campaign(root)
            for day in ("2025-05-01", "2025-05-02", "2025-05-28"):
                self.put_result(root, manifest, "B1", day, voltage=2 if day.endswith("28") else 0)
                self.put_result(root, manifest, "B3", day)
            self.put_result(root, manifest, "B2", "2025-05-01", passed=False)
            self.put_result(root, manifest, "B2", "2025-05-02", source="wrong-epoch")
            self.put_result(root, manifest, "B2", "2025-05-28")
            (root / "CAMPAIGN_MANIFEST.json").write_text(json.dumps(manifest))
            status = summarize(root)
            with (root / "reports/B2_B3_ACTUAL_COMPARISON.csv").open(encoding="utf-8-sig") as stream:
                rows = {r["day"]: r for r in csv.DictReader(stream)}
            for day in ("2025-05-01", "2025-05-02"):
                row = rows[day]
                self.assertEqual(row["B2_actual_line_loading_percent"], "")
                self.assertEqual(float(row["B2_diagnostic_actual_line_loading_percent"]), 80.)
                for key in ("B2_minus_B1_pp", "B3_minus_B2_pp"):
                    self.assertEqual(row[key], "")
                self.assertEqual(row["B2_B1_paired_physical_valid"], "False")
            self.assertEqual(rows["2025-05-28"]["B2_B1_paired_physical_valid"], "False")
            self.assertEqual(status["summary"]["B2"]["paired_B1_physical_valid_dates"], 0)
            failed_attempt = next(r for r in status["attempts"] if r["arm"] == "B2" and r["day"] == "2025-05-01")
            self.assertEqual(failed_attempt["native_runtime_seconds"], 12.5)
            self.assertEqual(failed_attempt["wall_seconds"], 42.75)
            wrong_source = next(r for r in status["dates"] if r["arm"] == "B2" and r["day"] == "2025-05-02")
            self.assertEqual(wrong_source["status"], "SOURCE_MISMATCH")

    def test_b3_failed_source_envelope_retains_only_diagnostic_fresh_currents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);manifest = self.setup_campaign(root)
            for day, passed, source, publish_ref in (
                    ("2025-05-01", False, "common-epoch", True),
                    ("2025-05-02", True, "wrong-epoch", True),
                    ("2025-05-03", False, "common-epoch", False)):
                self.put_result(root, manifest, "B1", day)
                path, result, _ = self.put_result(root, manifest, "B3", day, passed=passed, source=source)
                operations = path.parent / "output/PIPELINE/M2/OPERATIONS"
                raw = self.raw(operations / "FRESH/fresh")
                raw_receipt = record(raw)
                partial = {"folder": str(operations / "FRESH"), "files": [raw_receipt]}
                ac = dict(PASS=True, folder=partial["folder"], summary=result["evaluation"]["summary"])
                actual = path.parent / "output/PIPELINE/B3_SOURCE_ACTUAL_RESULT.json"
                actual.parent.mkdir(parents=True, exist_ok=True)
                actual.write_text(json.dumps({"evidence_kind": "SOURCE", "result": {"PASS": True, "fresh_ac": ac}}))
                result["files"] = []
                result["evaluation"] = {"Fresh": partial}
                if publish_ref:
                    result["actual"] = record(actual)
                path.write_text(json.dumps(result))
                manifest["date_results"]["B3/" + day] = record(path)
            (root / "CAMPAIGN_MANIFEST.json").write_text(json.dumps(manifest))
            status = summarize(root)
            dates = {r["day"]: r for r in status["dates"] if r["arm"] == "B3"}
            for day in ("2025-05-01", "2025-05-02", "2025-05-03"):
                row = dates[day]
                self.assertTrue(row["actual_fresh_physical_pass"])
                self.assertTrue(row["raw_current_declared_sha_verified"])
                self.assertEqual(row["diagnostic_actual_maximum_line_loading_percent"], 80.)
                self.assertIsNone(row["actual_maximum_line_loading_percent"])
                self.assertFalse(row["official_pair_eligible"])
            self.assertEqual(dates["2025-05-02"]["status"], "SOURCE_MISMATCH")
            self.assertTrue(dates["2025-05-01"]["source_match"])
            self.assertEqual(status["summary"]["B3"]["paired_B1_physical_valid_dates"], 0)
            self.assertEqual(status["audit_errors"], [])

    def test_prior_epoch_pass_never_completes_current_date_and_costs_remain_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);manifest = self.setup_campaign(root)
            path, current, _ = self.put_result(root, manifest, "B2", "2025-05-01", passed=False)
            current["scientific"]["native_runtime_seconds"] = 12.5
            path.write_text(json.dumps(current))
            manifest["date_results"]["B2/2025-05-01"] = record(path)
            prior = root / "previous_epoch/attempt_one/RESULT.json"
            prior.parent.mkdir(parents=True)
            prior.write_text(json.dumps(dict(PASS=True, status="COMPLETED_PHYSICAL_PASS",
                source_SHA="old-epoch", source_commit="old-commit", Native_Runtime=999.,
                worker_wall_seconds=33., scientific={"feasible_accepted": True, "verified_UB": .1})))
            ledger = prior.parent / "NATIVE_RUNTIME_LEDGER.json"
            ledger.write_text(json.dumps({"measured_Native_Runtime": 27.5, "calls": [], "inflight": None}))
            entry = dict(result=record(prior), native_ledger=record(ledger),
                source_SHA="old-epoch", source_commit="old-commit")
            # Referencing the same immutable attempt twice must not double cost.
            manifest["prior_attempts"] = {"B2/2025-05-01": [entry, entry]}
            second = root / "previous_epoch/attempt_two/RESULT.json"
            second.parent.mkdir(parents=True)
            second.write_bytes(prior.read_bytes())
            second_ledger = second.parent / "NATIVE_RUNTIME_LEDGER.json"
            second_ledger.write_bytes(ledger.read_bytes())
            manifest["prior_attempts"]["B2/2025-05-02"] = [dict(entry, result=record(second), native_ledger=record(second_ledger))]
            (root / "CAMPAIGN_MANIFEST.json").write_text(json.dumps(manifest))
            status = summarize(root)
            summary = status["summary"]["B2"]
            self.assertEqual(summary["current_epoch_native_runtime_known_seconds"], 12.5)
            self.assertEqual(summary["historical_native_runtime_known_seconds"], 55.)
            self.assertEqual(summary["historical_attempt_count"], 2)
            historical = [a for a in status["attempts"] if a["epoch"] == "HISTORICAL"]
            self.assertTrue(all(a["scientific_PASS_diagnostic"] is True for a in historical))
            self.assertTrue(all(a["current_success_eligible"] is False for a in historical))
            self.assertTrue(all(a["native_runtime_seconds"] == 27.5 for a in historical))
            self.assertTrue(all(a["native_runtime_basis"] == "DECLARED_NATIVE_LEDGER" for a in historical))
            pending = next(r for r in status["dates"] if r["arm"] == "B2" and r["day"] == "2025-05-02")
            self.assertEqual(pending["status"], "PENDING")
            self.assertIsNone(pending["diagnostic_actual_maximum_line_loading_percent"])
            self.assertFalse(pending["feasible_accepted"])
            self.assertEqual(summary["paired_B1_physical_valid_dates"], 0)
            self.assertEqual(status["audit_errors"], [])

    def test_prior_failed_source_keeps_classification_and_unknown_native_cost(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);manifest = self.setup_campaign(root)
            previous = root / "old_epoch/RESULT.json";previous.parent.mkdir()
            previous.write_text(json.dumps(dict(PASS=False, status="INPUT_OR_SOURCE_FAILURE",
                source_SHA="old-epoch", source_commit="old-commit", error="OLD_SOURCE_DRIFT",
                Native_Runtime=123., worker_wall_seconds=45.)))
            ledger = previous.parent / "NATIVE_RUNTIME_LEDGER.json"
            ledger.write_text(json.dumps({"measured_Native_Runtime": 123., "calls": [{"runtime_unavailable": True}]}))
            manifest["prior_attempts"] = {"B2/2025-05-01": [dict(result=record(previous), native_ledger=record(ledger),
                source_SHA="old-epoch", source_commit="old-commit")]}
            (root / "CAMPAIGN_MANIFEST.json").write_text(json.dumps(manifest))
            status = summarize(root)
            historical = status["attempts"][0]
            self.assertEqual(historical["classification"], "INPUT_OR_SOURCE_FAILURE")
            self.assertEqual(historical["error"], "OLD_SOURCE_DRIFT")
            self.assertIsNone(historical["native_runtime_seconds"])
            self.assertEqual(historical["wall_seconds"], 45.)
            self.assertEqual(status["summary"]["B2"]["historical_native_runtime_unknown_attempts"], 1)
            self.assertEqual(status["summary"]["B2"]["result_dates"], 0)
            report = (root / "reports/MAY31_FAILURE_AND_RETRY_REPORT_KO.md").read_text(encoding="utf8")
            self.assertIn("OLD_SOURCE_DRIFT", report)
            self.assertIn("INPUT_OR_SOURCE_FAILURE", report)
            self.assertEqual(status["audit_errors"], [])

    def test_missing_dates_remain_62_rows_and_blank_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);line=root/"limits.csv"
            line.write_text("branch_phase,NormalAmps\nline.l::A,50\n")
            baseline=root/"BASELINE.json";baseline.write_text(json.dumps({"B1_results":{}}))
            b0=root/"B0.json";b0.write_text(json.dumps({"source_files":[]}))
            manifest=root/"CAMPAIGN_MANIFEST.json";manifest.write_text(json.dumps({
                "line_current_authority_csv":str(line),"baseline_manifest":str(baseline),"b0_reclassification":str(b0)}))
            result=summarize(root)
            self.assertEqual(len(result["dates"]),62)
            self.assertTrue(all(r["status"]=="PENDING" for r in result["dates"]))
            self.assertTrue(all(r["global_gap_certified"] is False for r in result["dates"]))
            with (root/"reports/B2_B3_ACTUAL_COMPARISON.csv").open(encoding="utf-8-sig") as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),31)
            self.assertTrue(all(r["B2_actual_line_loading_percent"]=="" for r in rows))
            self.assertFalse(result["paper_experiment_usable"])
            self.assertEqual(len(list((root/"reports").glob("*.svg"))),4)


if __name__=="__main__":unittest.main()
