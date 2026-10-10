"""Physical hook plumbing fixtures; none of these claim production AC evidence."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest

import numpy as np

from v42_b3_joint.contracts import digest
from v42_dstatcom import integration as subject
from v42_dstatcom.settings import ControllerSettings


class Collection:
    def __init__(self): self.active=None; self.values={"original": [10.,2.]}
    def AllNames(self): return list(self.values)
    def Name(self,name): self.active=name
    def kW(self): return self.values[self.active][0]
    def kvar(self): return self.values[self.active][1]


class Solution:
    def __init__(self): self.solves=0; self.done=True
    def SolveSnap(self): self.solves+=1
    def ControlActionsDone(self): return self.done
    def Converged(self): return True
    def ControlIterations(self): return 2
    def Iterations(self): return 6
    def TotalIterations(self): return 6
    def MostIterationsDone(self): return 4
    def MaxControlIterations(self): return 100
    def MaxIterations(self): return 15
    def ControlMode(self): return 0


class Authority:
    def __init__(self):
        self.engine=SimpleNamespace(Solution=Solution(),Loads=Collection(),Generators=Collection())
        self.drift=False
    def compile_verified(self): return self.engine, {}, self.inventory(self.engine)
    def inventory(self,engine):
        return dict(regulators=[dict(name="reg"+str(k),enabled=not self.drift) for k in range(7)],CapControl_count=0)
    def source(self): return dict(inventory=self.inventory,native_state=lambda engine:([1.]*7,[1]*4))
    def assert_inventory(self,inventory,initial=False):
        if not all(r["enabled"] for r in inventory["regulators"]): raise ValueError("SOURCE_REGCONTROL_DISABLED")
    def regulator_parameters(self,inventory): return dict(regulators=inventory["regulators"],MaxControlIterations=100)
    def digest(self,value): return digest(value)


def original_voltage(engine,nodes): return [1.]
def original_fresh(): pass
def original_mapping(): pass
def install_fixture(engine,spec,settings):
    engine.Loads.values["dstat_"+spec.site_id]=[1.,0.]
    return SimpleNamespace(engine=engine,installation_receipt=dict(site=spec.site_id,fixture_only=True))


class Controller:
    fail=False
    mutate=False
    def __init__(self,devices,settings,source_SHA=None): self.devices=devices;self.previous_state=0
    def settle_slot(self,engine,slot):
        previous=self.previous_state;self.previous_state+=1
        for _ in range(2): engine.Solution.SolveSnap()
        if self.mutate: engine.Loads.values["original"][0]+=1
        return dict(PASS=not self.fail,controller_converged=not self.fail,ControlActionsDone=True,
                    solution_converged=True,additional_feedback_solve_count=2,finaldevices=[],fixture_previous_state=previous)


class ScopeFixture:
    def __init__(self):
        self.authority=Authority()
        self.backend=SimpleNamespace(_voltage_vector=original_voltage)
        authority,backend=self.authority,self.backend
        def run_fresh_opendss(trajectory):
            engine,_,_=authority.compile_verified()
            for slot in range(96):
                engine.Solution.SolveSnap()
                backend._voltage_vector(engine,["fixture"])
            return engine
        backend.run_fresh_opendss=run_fresh_opendss
        self.operations=SimpleNamespace(fresh=original_fresh)
        self.mapping=SimpleNamespace(apply_trajectory_slot=original_mapping)
        self.replay=SimpleNamespace(fresh=original_fresh)
    def bindings(self): return self.authority,self.operations,self.backend,self.mapping,self.replay,Controller
    def trajectory(self,namespace="ACTUAL",arm="B2"):
        return SimpleNamespace(namespace=namespace,case=arm,day="2025-05-01",
            pcc_p_kw=np.zeros((96,12)),pcc_q_kvar=np.zeros((96,12)),mess_p_kw=np.zeros((96,4)),
            mess_q_kvar=np.zeros((96,4)),mess_locations_96x4=np.full((96,4),"STA01"))


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        manifest=self.root/"connections.json";manifest.write_text('{"fixture":true}')
        identity=dict(schema=subject.SCHEMA,hardware=[subject.SiteSpec.from_dict(dict(site_id="STA01",pcc_bus="pcc",phases=[1,2,3],
            nominal_kv_ln=.48/(3**.5),rating_kvar=750)).to_dict()],controller=ControllerSettings().to_dict(),
            connection_manifest=subject.record(manifest))
        self.scenario=dict(identity,scenario_SHA=digest(identity))
        self.fixture=ScopeFixture();Controller.fail=False;Controller.mutate=False
        from v42_dstatcom import authority as execution_authority
        self.guard_patch=patch.object(execution_authority,"authorize_actual",return_value=dict(FAKE_SOURCE_TEST=True))
        self.guard_patch.start();self.addCleanup(self.guard_patch.stop)
        self.planning_guard=patch.object(execution_authority,"authorize_physical",create=True,
            return_value=dict(FAKE_SOURCE_TEST=True))
        self.planning_guard.start();self.addCleanup(self.planning_guard.stop)
        self.addCleanup(setattr,Controller,"fail",False);self.addCleanup(setattr,Controller,"mutate",False)
    def scope(self):
        return subject.scenario_scope(self.scenario,self.root/"audit",source_SHA=digest("fixture"),arm="B2",day="2025-05-01")
    def patches(self):
        return patch.object(subject,"_bindings",self.fixture.bindings),patch.object(subject,"install",install_fixture)

    def test_exact_actual_frame_receives_feedback_before_original_collection_and_restores(self):
        compile_function=self.fixture.authority.compile_verified
        voltage_function=self.fixture.backend._voltage_vector
        body=self.fixture.backend.run_fresh_opendss.__code__
        p1,p2=self.patches()
        with p1,p2:
            with self.scope() as audit:
                # Compile outside the Original ACTUAL frame must not install.
                self.fixture.authority.compile_verified()
                self.assertEqual(audit.sessions,{})
                engine=self.fixture.backend.run_fresh_opendss(self.fixture.trajectory())
        self.assertTrue(audit.result["PASS"])
        self.assertEqual(audit.result["logical_Fresh_slots"],96)
        self.assertEqual(audit.result["additional_feedback_solve_count"],192)
        self.assertEqual(audit.result["total_physical_SolveSnap_count"],288)
        self.assertEqual(engine.Solution.solves,288)
        self.assertIs(self.fixture.backend.run_fresh_opendss.__code__,body)
        self.assertEqual(self.fixture.authority.compile_verified,compile_function)
        self.assertIs(self.fixture.backend._voltage_vector,voltage_function)
        self.assertEqual(subject.record(audit.receipt["path"]),audit.receipt)
        self.assertEqual(audit.result["configured_MaxControlIterations"],[100])
        self.assertEqual(audit.result["configured_MaxIterations"],[15])
        progress_path=self.root/"audit/DSTATCOM_ACTUAL_PROGRESS.json"
        progress=json.loads(progress_path.read_text())
        self.assertEqual(progress["logical_Fresh_slots_completed"],96)
        self.assertEqual(progress["additional_feedback_solve_count"],192)
        self.assertEqual(progress["status"],"COMPLETE")
        self.assertNotIn("controller",progress)
        self.assertNotIn("iteration_trace",progress)
        self.assertLess(progress_path.stat().st_size,4096)
    def test_dayahead_frame_never_installs_or_feedback_solves(self):
        p1,p2=self.patches()
        with p1,p2:
            with self.scope() as audit:
                engine=self.fixture.backend.run_fresh_opendss(self.fixture.trajectory("DAYAHEAD"))
        self.assertEqual(engine.Solution.solves,96)
        self.assertEqual(audit.result["status"],"NOT_RUN")
        self.assertFalse(audit.result["PASS"])
        self.assertEqual(audit.installations,[])
    def test_wrong_arm_actual_is_rejected_with_preserved_error_receipt(self):
        p1,p2=self.patches()
        with p1,p2:
            with self.assertRaisesRegex(ValueError,"SOURCE_IDENTITY_DRIFT"):
                with self.scope() as audit:
                    self.fixture.backend.run_fresh_opendss(self.fixture.trajectory(arm="B1"))
        self.assertFalse(audit.result["PASS"])
        self.assertIn("SOURCE_IDENTITY_DRIFT",audit.result["error"])
    def test_hardware_failure_cannot_become_pass_even_when_original_ac_converges(self):
        Controller.fail=True
        p1,p2=self.patches()
        with p1,p2:
            with self.scope() as audit:
                self.fixture.backend.run_fresh_opendss(self.fixture.trajectory())
        self.assertEqual(audit.result["logical_Fresh_slots"],96)
        self.assertFalse(audit.result["PASS"])
        self.assertEqual(audit.result["hardware_or_controller_failed_slots"],list(range(96)))
    def test_original_plan_input_change_rejected_and_hook_restored(self):
        Controller.mutate=True
        p1,p2=self.patches()
        with p1,p2:
            with self.assertRaisesRegex(ValueError,"EXOGENOUS_OR_PLAN_MUTATION"):
                with self.scope() as audit:
                    self.fixture.backend.run_fresh_opendss(self.fixture.trajectory())
        self.assertFalse(audit.result["PASS"])
        self.assertIs(self.fixture.backend._voltage_vector,original_voltage)
        self.assertEqual(audit.result["logical_Fresh_slots"],0)
        self.assertEqual(audit.result["additional_feedback_solve_count"],2)
        self.assertEqual(audit.result["completed_physical_SolveSnap_count"],3)
        self.assertEqual(len(json.loads(Path(audit.result["physical_solve_events_receipt"]["path"]).read_text())),3)
    def test_original_regulator_drift_during_feedback_is_rejected_without_reset_or_repair(self):
        solution=self.fixture.authority.engine.Solution
        original_solve=type(solution).SolveSnap
        def altered_fixture_solve(instance):
            original_solve(instance)
            if solution.solves==2: self.fixture.authority.drift=True
        p1,p2=self.patches()
        with p1,p2,patch.object(type(solution),"SolveSnap",altered_fixture_solve):
            with self.assertRaisesRegex(ValueError,"SOURCE_REGCONTROL_DISABLED"):
                with self.scope() as audit:
                    self.fixture.backend.run_fresh_opendss(self.fixture.trajectory())
        self.assertTrue(self.fixture.authority.drift)
        self.assertFalse(audit.result["PASS"])
        self.assertEqual(audit.result["logical_Fresh_slots"],0)
        self.assertEqual(audit.result["total_physical_SolveSnap_count"],2)
    def test_tampered_frozen_connection_receipt_blocks_scope_before_dss(self):
        Path(self.scenario["connection_manifest"]["path"]).write_text("changed")
        with self.assertRaisesRegex(ValueError,"CONNECTION_MANIFEST_RECEIPT_DRIFT"):
            with self.scope(): pass
        self.assertEqual(self.fixture.authority.engine.Solution.solves,0)
    def test_self_hashed_scenario_and_source_string_cannot_replace_explicit_actual_permit(self):
        self.guard_patch.stop()
        self.planning_guard.stop()
        with self.assertRaisesRegex(PermissionError,"SOURCE_BOUND_ACTUAL_PERMIT_REQUIRED"):
            with self.scope(): pass
        self.assertEqual(self.fixture.authority.engine.Solution.solves,0)
        self.assertFalse((self.root/"audit").exists())
    def test_planning_scope_without_source_bound_namespace_permit_rejected_before_dss(self):
        self.planning_guard.stop()
        with self.assertRaisesRegex(PermissionError,"SOURCE_BOUND_ACTUAL_PERMIT_REQUIRED"):
            with subject.scenario_scope(self.scenario,self.root/"planning",source_SHA=digest("fixture"),
                    arm="B2",day="2025-05-01",namespace="DAYAHEAD"): pass
        self.assertEqual(self.fixture.authority.engine.Solution.solves,0)
        self.assertFalse((self.root/"planning").exists())
    def test_forecast_and_actual_build_separate_controller_and_source_initial_state(self):
        first_fixture=self.fixture
        p1,p2=self.patches()
        with p1,p2:
            with subject.scenario_scope(self.scenario,self.root/"planning",source_SHA=digest("fixture"),
                    arm="B2",day="2025-05-01",namespace="DAYAHEAD") as planning:
                first_fixture.backend.run_fresh_opendss(first_fixture.trajectory("DAYAHEAD"))
        self.assertEqual(planning.rows[-1]["controller"]["fixture_previous_state"],95)
        self.fixture=ScopeFixture()
        p1,p2=self.patches()
        with p1,p2:
            with self.scope() as actual:
                self.fixture.backend.run_fresh_opendss(self.fixture.trajectory())
        self.assertIsNot(planning.sessions[id(first_fixture.authority.engine)][1],
                         actual.sessions[id(self.fixture.authority.engine)][1])
        self.assertEqual(actual.rows[0]["controller"]["fixture_previous_state"],0)
        self.assertEqual(actual.result["source_initial_controls"]["taps"],[1.]*7)
        self.assertEqual(planning.result["namespace"],"DAYAHEAD")
        self.assertEqual(actual.result["namespace"],"ACTUAL")
        self.assertNotEqual(planning.trajectory_SHA,actual.trajectory_SHA)
        self.assertTrue((self.root/"planning/DSTATCOM_PLANNING_PROGRESS.json").exists())
        self.assertFalse(actual.result["Planning_Q_Tap_or_controller_state_transfer_to_Actual"])
        self.assertTrue(planning.result["PASS"] and actual.result["PASS"])
    def test_planning_permit_cannot_hook_actual_backend_frame(self):
        p1,p2=self.patches()
        with p1,p2:
            with subject.scenario_scope(self.scenario,self.root/"planning",source_SHA=digest("fixture"),
                    arm="B2",day="2025-05-01",namespace="DAYAHEAD") as audit:
                self.fixture.backend.run_fresh_opendss(self.fixture.trajectory())
        self.assertEqual(audit.sessions,{})
        self.assertEqual(audit.result["status"],"NOT_RUN")
        self.assertFalse(audit.result["PASS"])
    def test_self_hashed_legacy_controller_cannot_silently_use_new_default_fields(self):
        # Exact frozen V1 settings lack the later V2 saturation/hysteresis fields.
        snapshot=Path(r"D:/v42_dstatcom_development_20261010/source_epochs/b37e20bc1e6172ca2600e3ebcd42e8dd5f6ba95d2b78d6e42f02b211cd676618/v42_dstatcom/settings.py")
        if not snapshot.exists(): self.skipTest("Preserved completed V1 source unavailable")
        import importlib.util,sys
        spec=importlib.util.spec_from_file_location("v42_preserved_v1_settings_test",snapshot)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
        try: spec.loader.exec_module(module)
        finally: sys.modules.pop(spec.name,None)
        value=json.loads(json.dumps(self.scenario));value["controller"]=module.ControllerSettings().to_dict()
        value["scenario_SHA"]=digest(subject.scenario_identity(value))
        with self.assertRaisesRegex(ValueError,"COMPLETE_VERSIONED_FIELDS_REQUIRED"):
            subject.validate_scenario(value)
    def test_controller_missing_field_or_hardware_default_not_in_frozen_identity_rejected(self):
        value=json.loads(json.dumps(self.scenario));del value["controller"]["damping"]
        value["scenario_SHA"]=digest(subject.scenario_identity(value))
        with self.assertRaisesRegex(ValueError,"CONTROLLER_COMPLETE_VERSIONED_FIELDS_REQUIRED"):
            subject.validate_scenario(value)
        value=json.loads(json.dumps(self.scenario));del value["hardware"][0]["endpoint_id"]
        value["scenario_SHA"]=digest(subject.scenario_identity(value))
        with self.assertRaisesRegex(ValueError,"HARDWARE_COMPLETE_FIELDS_REQUIRED"):
            subject.validate_scenario(value)


if __name__ == "__main__": unittest.main()
