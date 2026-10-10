"""Scientific reporting checks, independent of any optimizer implementation."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from v42_common_reporting.report import current_metric, load_receipt, record, stage_row, summarize


class ReportingTests(unittest.TestCase):
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
            with (root/"reports/B2_B3_ACTUAL_COMPARISON.csv").open(encoding="utf-8-sig") as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),31)
            self.assertTrue(all(r["B2_actual_line_loading_percent"]=="" for r in rows))
            self.assertFalse(result["paper_experiment_usable"])
            self.assertEqual(len(list((root/"reports").glob("*.svg"))),4)


if __name__=="__main__":unittest.main()
