"""Targeted V39I checks only; no Gurobi optimize calls or earlier-day reruns."""
import ast
import itertools
import math
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from dayahead.tools import run_v39i_minmax as i
from dayahead.tools import run_v39i_threshold as threshold
from dayahead.tools import v39i_report as report
h=i.h


class EncodingTests(unittest.TestCase):
    def test_threshold_prefix_exact_for_split_cohorts(self):
        # Each tuple is the individual delays of a cohort split across options.
        for count in (1,2,3):
            for delays in itertools.product(range(5),repeat=count):
                for dmax in range(5):
                    z={t:int(t<=dmax) for t in range(1,5)}
                    valid=all(sum(d==t for d in delays)<=count*z[t] for t in range(1,5))
                    self.assertEqual(valid,max(delays)<=dmax)
                    if valid:self.assertLessEqual(sum(delays),count*dmax)
                    self.assertEqual(sum(z.values()),dmax)

    def test_incumbent_upper_bound_excludes_no_minimum(self):
        for values in ((0,1,5),(2,4,9),(3,3,7)):
            for incumbent in values:
                self.assertEqual(min(values),min(v for v in values if v<=incumbent))

    def test_half_open_domain_accounting(self):
        pre,inside,post=report.interval_parts([0,20,24,110,120,130],[24,30,120,130,121,134],[2,3,4,5,6,7])
        np.testing.assert_array_equal(pre,[48,12,0,0,0,0])
        np.testing.assert_array_equal(inside,[0,18,384,50,0,0])
        np.testing.assert_array_equal(post,[0,0,0,50,6,28])

    def test_model_has_only_dmax_solve_and_exact_primary_equality(self):
        source=Path(threshold.__file__).read_text(encoding="utf-8")
        tree=ast.parse(source)
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="solve_stage"]
        self.assertEqual(len(calls),1)
        self.assertEqual(ast.literal_eval(calls[0].args[1]),0)
        self.assertIn('bundle["objectives"][0]==i.PRIMARY[day]',source)
        self.assertIn('start-cs[k]["lo"]<=threshold else 0',source)
        self.assertEqual(i.MAX_PARALLEL_DAY_WORKERS,2)
        self.assertEqual(i.GUROBI_THREADS_PER_MODEL,4)

    def test_delay_threshold_feasible_sets_are_nested(self):
        schedules=list(itertools.product(range(6),repeat=3))
        previous=set()
        for bound in range(6):
            current={s for s in schedules if max(s)<=bound}
            self.assertTrue(previous<=current)
            previous=current


class FinalArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data={}
        for day in i.DAYS:
            out=i.ROOT/"days"/day
            cls.data[day]={"out":out,"new":pd.read_parquet(out/"V39I_MINMAX_DELAY_SCHEDULE.parquet"),
                "old":pd.read_parquet(h.ROOT/"days"/day/"V39H_SHADOW_SCHEDULE.parquet"),
                "result":h.read(out/"V39I_MINMAX_DELAY_RESULT.json")}

    def test_certified_primary_exact_integer_equality(self):
        for day,d in self.data.items():
            with self.subTest(day=day):
                b=d["new"]
                actual=int((2*b.requested_gpus*np.minimum(b.start_delay_slots,b.duration_slots)).sum())
                self.assertEqual(actual,i.PRIMARY[day])
                self.assertEqual(int(b.occupancy_deviation_GPU_slots.sum()),actual)
                eq=h.read(d["out"]/"V39I_MINMAX_FORMULATION.json")
                self.assertEqual(eq["primary_constraint_sense"],"=")
                self.assertEqual(eq["primary_equality_RHS"],actual)
                self.assertFalse(eq["secondary_changed_job_equality_added"])

    def test_dmax_global_exactness_and_definition(self):
        for day,d in self.data.items():
            with self.subTest(day=day):
                r=d["result"];b=d["new"];s=r["solver_certificate"]
                self.assertTrue(r["D_MAX_exact_optimality"])
                self.assertEqual(s["status"],"EXACT_BY_ADJACENT_THRESHOLDS")
                feasible=s["T_star_FEASIBLE"];infeasible=s["T_star_minus_1_INFEASIBLE"]
                self.assertEqual(feasible["threshold_slots"],r["D_MAX_slots"])
                self.assertEqual(feasible["outcome"],"FEASIBLE")
                self.assertTrue(feasible["independently_verified"])
                self.assertEqual(infeasible["threshold_slots"],r["D_MAX_slots"]-1)
                self.assertEqual(infeasible["outcome"],"INFEASIBLE")
                self.assertEqual(infeasible["stage"]["status"],3)
                self.assertTrue(infeasible["globally_infeasible"])
                self.assertEqual(infeasible["fingerprint"],r["fingerprint"])
                self.assertEqual(feasible["schedule_SHA256"],r["schedule_SHA256"])
                self.assertEqual(s["MIPGap_setting"],0)
                self.assertEqual(r["D_MAX_slots"],int(b.loc[b.eligible,"start_delay_slots"].max()))
                self.assertEqual(r["D_MAX_slots"],s["T_star_slots"])
                self.assertEqual(r["D_MAX_minutes"],r["D_MAX_slots"]*15)
                self.assertLessEqual(r["D_MAX_slots"],int(d["old"].start_delay_slots.max()))
                self.assertEqual(s["Threads"],4)

    def test_full_job_gpu_runtime_and_service_preservation(self):
        for day,d in self.data.items():
            with self.subTest(day=day):
                old=d["old"];new=d["new"]
                self.assertEqual(list(old.job_uid),list(new.job_uid))
                for col in ("requested_gpus","RSP_duration_slots","RSP_duration_seconds","eligible","latest_start","RSP_scheduled_start","RW_scheduled_completion"):
                    np.testing.assert_array_equal(old[col],new[col])
                self.assertTrue(np.array_equal(new.duration_slots,new.scheduled_end_slot-new.scheduled_start_slot))
                self.assertTrue((new.start_delay_slots>=0).all())
                self.assertTrue((new.scheduled_start_slot<=new.latest_start).all())
                self.assertTrue((new.loc[~new.eligible,"start_delay_slots"]==0).all())
                self.assertTrue(new.loc[new.start_delay_slots.gt(0),"qos"].eq("standby").all())
                self.assertTrue(new.loc[new.start_delay_slots.gt(0),"state_at_issue"].eq("PENDING").all())
                service=report.service_audit(old,new)
                self.assertTrue(service["RW_completion_noninferiority_pass"])
                self.assertTrue(service["frozen_safe_runtime_preserved"])
                self.assertEqual(service["new_RW_completion_violations"],0)
                self.assertEqual(service["eligible_RW_completion_violations"],0)

    def test_grid_independent_certificate_and_zero_violations(self):
        for day,d in self.data.items():
            with self.subTest(day=day):
                a=h.read(d["out"]/"V39I_GRID_VERIFICATION.json");g=a["grid"]
                self.assertEqual(a["status"],"PASS")
                self.assertTrue(a["all_hard_constraints_pass"])
                self.assertTrue(g["pass"])
                for field in ("site_capacity_violations","aggregate_capacity_violations","gang_splits","rack_compatibility_failures","safe_duration_changes"):
                    self.assertEqual(a[field],0)
                for field in ("voltage_violation_count","line_current_violation_count","transformer_current_violation_count","transformer_kva_violation_count","transformer_polygon_violation_count"):
                    self.assertEqual(g[field],0)
                self.assertLessEqual(g["Vmax"],1.05)
                self.assertGreaterEqual(g["Vmin"],.95)
                self.assertLessEqual(g["all_inequalities_max_absolute_residual"],0)
                self.assertEqual(a["site_grid_domain_issue_slots"],[24,120])
                self.assertEqual(g["critical_issue_slot"],g["critical_target_slot"]+24)
                self.assertIn(".",g["critical_voltage_bus_phase"])

    def test_saved_integer_occupancy_and_c1_witness(self):
        for day,d in self.data.items():
            with self.subTest(day=day):
                with np.load(d["out"]/"V39I_VERIFIED_WITNESS.npz") as saved:
                    occ=saved["GPU_complete"];pcc=saved["PCC_target"]
                b=d["new"];capacity,_=h._load_capacity(i.REPO);sites=list(capacity.aidc_ids)
                recomputed=np.zeros_like(occ)
                for r in b.itertuples(index=False):recomputed[r.scheduled_start_slot:r.scheduled_end_slot,sites.index(r.AIDC)]+=int(r.requested_gpus)
                np.testing.assert_array_equal(recomputed,occ)
                self.assertLessEqual(int(occ.sum(axis=1).max()),624)
                self.assertTrue((occ[24:120]<=np.array([capacity.site_capacity[s] for s in sites])).all())
                with np.load(d["out"]/"V39G_C1_INTEGER_TABLES.npz") as tables:
                    c1=np.array([[tables[s][t,occ[t+24,k]] for k,s in enumerate(sites)] for t in range(96)])
                np.testing.assert_array_equal(c1,pcc)

    def test_time_domain_exact_partition_no_offdomain_authority(self):
        for day,d in self.data.items():
            with self.subTest(day=day):
                saved=h.read(d["out"]/"V39I_TIME_DOMAIN_AUDIT.json")
                for name,key in (("old_V39H","old"),("new_V39I","new")):
                    audit=report.domain_audit(day,d[key])
                    self.assertEqual(saved[name],audit)
                    total=int((d[key].requested_gpus*d[key].duration_slots).sum())/4
                    self.assertEqual(total,audit["reservation_GPU_h_outside_grid_domain"]+audit["reservation_GPU_h_inside_grid_domain"])
                    self.assertFalse(audit["outside_domain_site_assignment_physically_verified"])
                    self.assertTrue(audit["outside_domain_portions_reservation_accounting_only"])

    def test_max_attaining_job_audit_is_complete(self):
        for day,d in self.data.items():
            with self.subTest(day=day):
                rows=pd.read_csv(d["out"]/"V39I_MAX_DELAY_JOB_AUDIT.csv",dtype={"job_uid":str})
                for key,flag in (("old","attains_old_maximum"),("new","attains_new_maximum")):
                    b=d[key];expected=set(b.loc[b.start_delay_slots.eq(b.start_delay_slots.max()),"job_uid"])
                    self.assertEqual(set(rows.loc[rows[flag],"job_uid"]),expected)
                self.assertFalse(rows.individual_UID_necessity_globally_proven.any())
                self.assertTrue(rows.new_V39I_slack_consumption_fraction.between(0,1).all())
                self.assertTrue(rows.new_V39I_completion_margin_to_RW_min.ge(0).all())

    def test_no_migration_or_forbidden_calls(self):
        for day,d in self.data.items():
            with self.subTest(day=day):
                b=d["new"];r=d["result"]
                self.assertTrue((b.loc[b.state_at_issue.eq("RUNNING"),"AIDC"]==b.loc[b.state_at_issue.eq("RUNNING"),"initial_AIDC"]).all())
                for key in ("primary_optimization_reruns","migration_MILP_reruns","full_preflight_calls","May_campaign_calls","Actual_reads","Fresh_reads","secondary_optimization_calls"):
                    self.assertEqual(r[key],0)
                for key in ("RUNNING_site_changes","WAN_transfer_count","MESS_moves"):
                    self.assertEqual(r["audit"][key],0)
                self.assertEqual(r["schedule_SHA256"],h.grid.sha(d["out"]/"V39I_MINMAX_DELAY_SCHEDULE.parquet"))

    def test_frozen_sources_authorities_and_earlier_artifacts_unchanged(self):
        provenance=report.preservation()
        # A concurrent task committed the already-dirty monitor without changing
        # working bytes. HEAD identity is recorded, not a scientific invariant.
        self.assertTrue(provenance["HEAD_delta_working_files_match_start_SHA"])
        self.assertTrue(provenance["production_source_SHA256_unchanged"])
        self.assertTrue(provenance["V39H_all_metadata_unchanged"])
        self.assertTrue(provenance["V39H_required_SHA256_unchanged"])
        self.assertTrue(provenance["V39E_F_G_metadata_unchanged"])
        for d in self.data.values():
            eq=h.read(d["out"]/"V39I_INPUT_EQUIVALENCE.json")
            for path,sha in eq["input_SHA256"].items():self.assertEqual(h.grid.sha(path),sha)


if __name__=="__main__":
    unittest.main()
