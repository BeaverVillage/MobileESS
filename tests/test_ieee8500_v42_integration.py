"""Small contract/row fixtures only: no Native or OpenDSS certification."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from ieee8500_v42.integration import (
    GATES, LocationPort, comparison_plan, digest, execute_production,
    file_sha, make_location_strengthening_hook, validate_location_limits,
    verify_source_identity, research_port_contract, write_research_contract_artifacts,
    build_research_fleet_configuration, port_battery_energy_delta,
)


UNITS = tuple(f"MESS{i:02d}" for i in range(1, 7))
SITES = tuple(f"AIDC{i:02d}" for i in range(1, 13)) + tuple(f"STA{i:02d}" for i in range(1, 13))


def fixture():
    ports = tuple(LocationPort(s, "source_bus", (1, 2), "SPLIT_PHASE_240V",
                              20., 20., 30., UNITS, (0,), "1" * 64, True) for s in SITES)
    values = {f"{prefix}[{unit},{site},0]": 0. for prefix in ("Pch", "Pdis", "Q")
              for unit in UNITS for site in SITES}
    locations = [[SITES[0]] * 6]
    return ports, values, locations


class IntegrationContracts(unittest.TestCase):
    def simulation_fixture(self, directory):
        records = write_research_contract_artifacts(directory)
        ports = tuple(LocationPort(s, "original_LV_bus", (1, 2), "SPLIT_PHASE_240V",
            5., 5., 6., UNITS, (0,), "", False, authority_kind="SIMULATION_DESIGN",
            simulation_design_sha=records["design_sha"], simulation_authority_sha=records["authority_sha"],
            field_certified=False, q_abs_kvar=3.) for s in SITES)
        return ports, records

    def test_same_frozen_condition_and_independent_stage_policy(self):
        plan = comparison_plan({"day": "2025-05-01", "status": "NOT_SELECTED"})
        self.assertEqual([a["arm"] for a in plan["arms"]], ["B0", "B1", "B2", "B3"])
        self.assertEqual(len({a["scenario_sha"] for a in plan["arms"]}), 1)
        self.assertEqual([s["stage"] for s in plan["arms"][3]["stages"]], ["A1", "M1", "A2", "M2"])
        self.assertEqual([s["gap_target"] for s in plan["arms"][3]["stages"]], [.005, .03, .005, .03])
        self.assertTrue(all(s["native_runtime_limit_seconds"] == 5400 and s["Threads"] == 1
                            and s["P2_calls"] == 0 for a in plan["arms"] for s in a["stages"]))
        self.assertEqual(set(plan["unresolved_gates"]), set(GATES))
        self.assertFalse(plan["production_ready"])
        with self.assertRaises(PermissionError):
            execute_production(approved=True, all_gates_pass=True)

    def test_fixture_gate_cannot_be_promoted_and_tampering_fails(self):
        scenario = {"day": "2025-05-01", "status": "SELECTED_AND_FROZEN"}
        gate = GATES[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps({"gate": gate, "PASS": True,
                "scenario_sha": digest(scenario), "evidence_kind": "FAKE_SOURCE_TEST",
                "verifier_source_sha": "1" * 64}), encoding="utf-8")
            receipts = {gate: {"path": str(path), "sha256": file_sha(path)}}
            self.assertIn(gate, comparison_plan(scenario, gate_receipts=receipts)["unresolved_gates"])
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ARTIFACT_DRIFT"):
                comparison_plan(scenario, gate_receipts=receipts)

    def test_source_byte_identity_and_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.py"
            path.write_bytes(b"a=1\r\n")
            manifest = {"v42_git_sha": "1" * 40, "files": {"source.py": file_sha(path)}}
            self.assertTrue(verify_source_identity(directory, manifest)["PASS"])
            path.write_bytes(b"a=1\n")
            with self.assertRaisesRegex(ValueError, "IDENTITY_DRIFT"):
                verify_source_identity(directory, manifest)
            manifest["files"] = {"../escape.py": "2" * 64}
            with self.assertRaisesRegex(ValueError, "IDENTITY_DRIFT"):
                verify_source_identity(directory, manifest)

    def test_uncertified_ports_and_wrong_phase_counts_are_rejected(self):
        port = fixture()[0][0]
        with self.assertRaisesRegex(ValueError, "ZERO_PQ"):
            replace(port, certified=False).validate(1)
        with self.assertRaisesRegex(ValueError, "PHASE_NODE"):
            replace(port, nodes=(1, 2, 3)).validate(1)
        self.assertTrue(replace(port, certified=False, p_charge_kw=0,
                                p_discharge_kw=0, pcs_kva=0).validate(1))

    def test_individual_feasibility_does_not_hide_shared_port_overload(self):
        ports, values, locations = fixture()
        for unit in UNITS[:2]:
            values[f"Pdis[{unit},{SITES[0]},0]"] = 12.
        result = validate_location_limits(values, locations, ports, UNITS, horizon=1)
        self.assertFalse(result["PASS"])
        self.assertEqual({v["kind"] for v in result["violations"]}, {"SHARED_PORT"})
        self.assertEqual(result["maximum_violation_kw_or_kvar"], 4.)
        self.assertFalse(result["real_opendss_verified"])

    def test_eligibility_time_and_nonlocation_output_independently_fail(self):
        ports, values, locations = fixture()
        values[f"Q[{UNITS[0]},{SITES[0]},0]"] = 1.
        for restricted in (replace(ports[0], eligible_units=UNITS[1:]),
                           replace(ports[0], available_slots=())):
            result = validate_location_limits(values, locations, (restricted,) + ports[1:], UNITS, horizon=1)
            self.assertFalse(result["PASS"])
        locations[0][0] = "TRANSIT_01"
        self.assertFalse(validate_location_limits(values, locations, ports, UNITS, horizon=1)["PASS"])

    def test_missing_variable_and_wrong_vehicle_axis_fail_closed(self):
        ports, values, locations = fixture()
        values.pop(next(iter(values)))
        with self.assertRaises(KeyError):
            validate_location_limits(values, locations, ports, UNITS, horizon=1)
        with self.assertRaisesRegex(ValueError, "SIX_VEHICLE"):
            validate_location_limits(values, locations, ports, UNITS[:4], horizon=1)

    def test_append_hook_preserves_existing_variables_rows_and_objective(self):
        ports, values, locations = fixture()
        class RowFixture:
            NumVars = 777
            NumConstrs = 37
            objective = "ORIGINAL_RHO_MAX"
            def update(self):
                pass
            def addConstr(self, expression, *, name):
                self.NumConstrs += 1
        stay = {(s, 0): i for i, s in enumerate(SITES)}
        context = SimpleNamespace(horizon=1, sites=SITES, initial_sites=dict.fromkeys(UNITS, SITES[0]),
            stay=stay, x={(u, i): int(i == 0) for u in UNITS for i in range(24)},
            charge={(u, s, 0): 0. for u in UNITS for s in SITES},
            discharge={(u, s, 0): 0. for u in UNITS for s in SITES},
            reactive={(u, s, 0): 0. for u in UNITS for s in SITES})
        model = RowFixture()
        receipt = make_location_strengthening_hook(ports, quicksum=sum)(model, context)
        self.assertEqual(receipt["appended_rows"], 24 * (6 * 20 + 18))
        self.assertEqual(model.NumConstrs, 37 + receipt["appended_rows"])
        self.assertEqual(model.NumVars, 777)
        self.assertEqual(model.objective, "ORIGINAL_RHO_MAX")
        self.assertEqual(receipt["real_full_model_equivalence"], "NOT_TESTED")

    def test_sha_bound_authorized_simulation_ports_are_research_only(self):
        with tempfile.TemporaryDirectory() as directory:
            ports, records = self.simulation_fixture(directory)
            contract = research_port_contract(ports, horizon=1, simulation_authority=records['authority_path'])
            self.assertTrue(contract['research_design_admitted'])
            self.assertEqual(contract['simulation_design_port_count'],24)
            self.assertFalse(contract['field_certification_verified'])
            self.assertFalse(contract['production_ready'])
            self.assertEqual(contract['actual_six_unit_native_and_SOC_adapter'],'UNVERIFIED')
            self.assertTrue(ports[0].validate(1,simulation_authority=records['authority_path']))
            with self.assertRaisesRegex(ValueError,'RESEARCH_ONLY'):
                ports[0].validate(1,execution_scope='PRODUCTION',simulation_authority=records['authority_path'])
            with self.assertRaises(PermissionError):
                execute_production(research_authorized=True, ports=ports, certificates_present=True)

    def test_missing_tampered_or_unapproved_simulation_authority_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ports, records = self.simulation_fixture(directory)
            port=ports[0];path=Path(records['authority_path'])
            with self.assertRaisesRegex(ValueError,'SHA_BOUND'):
                replace(port,simulation_authority_sha='1'*64).validate(1,simulation_authority=path)
            with self.assertRaisesRegex(ValueError,'SOURCE_SHA'):
                replace(port,simulation_design_sha='1'*64).validate(1,simulation_authority=path)
            authority=json.loads(path.read_text(encoding='utf-8'));authority['user_authorized']=False
            path.write_text(json.dumps(authority),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'EXPLICIT_USER'):
                replace(port,simulation_authority_sha=file_sha(path)).validate(1,simulation_authority=path)

    def test_simulation_scope_does_not_authorize_larger_PQ_or_other_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            ports, records = self.simulation_fixture(directory)
            for port in (replace(ports[0],p_discharge_kw=5.1),replace(ports[0],q_abs_kvar=3.1),
                         replace(ports[0],pcs_kva=6.1),replace(ports[0],connection='SINGLE_PHASE_120V',nodes=(1,))):
                with self.assertRaisesRegex(ValueError,'ENVELOPE'):
                    port.validate(1,simulation_authority=records['authority_path'])
            with self.assertRaisesRegex(ValueError,'ZERO_PQ'):
                replace(ports[0],authority_kind='UNVERIFIED',physical_evidence_sha='1'*64).validate(1)

    def test_field_certificate_boolean_does_not_unlock_production(self):
        legacy_certified_port=fixture()[0][0]
        with self.assertRaisesRegex(ValueError,'ACTUAL_FIELD_CERTIFICATES'):
            legacy_certified_port.validate(1,execution_scope='PRODUCTION')

    def test_simulation_shared_reactive_ceiling_independently_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            ports,records=self.simulation_fixture(directory)
            _,values,locations=fixture()
            for unit in UNITS[:2]:values[f'Q[{unit},{SITES[0]},0]']=2.
            result=validate_location_limits(values,locations,ports,UNITS,horizon=1,
                simulation_authority=records['authority_path'])
            self.assertFalse(result['PASS'])
            self.assertEqual({v['kind'] for v in result['violations']},{'SHARED_PORT'})
            self.assertEqual(result['maximum_violation_kw_or_kvar'],1.)
            self.assertEqual(result['execution_scope'],'RESEARCH')
            self.assertFalse(result['field_certification_verified'])

    def test_simulation_append_hook_accepts_authorized_PQ_and_enforces_shared_Q(self):
        with tempfile.TemporaryDirectory() as directory:
            ports, records = self.simulation_fixture(directory)
            class RowFixture:
                NumVars = 777
                NumConstrs = 37
                objective = 'ORIGINAL_RHO_MAX'
                def __init__(self):
                    self.rows = {}
                def update(self):
                    pass
                def addConstr(self, expression, *, name):
                    self.rows[name] = bool(expression)
                    self.NumConstrs += 1
            context = SimpleNamespace(horizon=1, sites=SITES,
                initial_sites=dict.fromkeys(UNITS, SITES[0]),
                stay={(s, 0): i for i, s in enumerate(SITES)},
                x={(u, i): int(i == 0) for u in UNITS for i in range(24)},
                charge={(u, s, 0): 0. for u in UNITS for s in SITES},
                discharge={(u, s, 0): 0. for u in UNITS for s in SITES},
                reactive={(u, s, 0): 0. for u in UNITS for s in SITES})
            context.discharge[UNITS[0], SITES[0], 0] = 5.
            context.reactive[UNITS[0], SITES[0], 0] = 3.
            append = make_location_strengthening_hook(ports, quicksum=sum,
                simulation_authority=records['authority_path'])
            model = RowFixture()
            receipt = append(model, context)
            self.assertTrue(all(model.rows.values()))
            self.assertEqual(receipt['appended_rows'], 24 * (6 * 20 + 20))
            self.assertEqual((model.NumVars, model.objective), (777, 'ORIGINAL_RHO_MAX'))
            self.assertEqual(model.NumConstrs, 37 + receipt['appended_rows'])
            self.assertEqual(receipt['simulation_design_port_count'], 24)
            self.assertEqual(receipt['LV_auxiliary_efficiency_SOC_adapter'], 'UNVERIFIED')
            context.discharge[UNITS[0], SITES[0], 0] = 0.
            for unit in UNITS[:2]:
                context.reactive[unit, SITES[0], 0] = 2.
            overloaded = RowFixture()
            append(overloaded, context)
            failed_rows = [name for name, passed in overloaded.rows.items() if not passed]
            self.assertEqual(failed_rows, ['ieee8500_shared_port[AIDC01,0]:q_upper'])

    def test_original_six_initial_map_and_user_rating_fractions_preserved(self):
        fleet=build_research_fleet_configuration()
        self.assertEqual(fleet['initial_locations'],dict(zip(UNITS,('STA01','STA12','STA08','STA06','STA03','STA10'))))
        p=fleet['physical']
        self.assertEqual((p['active_power_limit_kw'],p['pcs_kva'],p['capacity_kwh']),(450,600,1800))
        self.assertEqual((p['energy_min_kwh'],p['energy_max_kwh'],p['initial_energy_kwh'],p['terminal_energy_kwh']),(660,1620,1140,1140))
        self.assertEqual((p['charge_efficiency'],p['discharge_efficiency']),(.95,.95))
        self.assertEqual(fleet['active_original_native_vehicle_count'],4)
        self.assertEqual(fleet['actual_six_unit_Native_Actual_Fresh_adapter'],'UNVERIFIED')
        self.assertFalse(fleet['append_only_port_rows_implement_auxiliary_SOC_losses'])
        self.assertEqual(fleet['Native_calls'],0)

    def test_LV_SOC_composes_auxiliary_loss_and_original_route_energy(self):
        self.assertAlmostEqual(port_battery_energy_delta(5,0),1.06875)
        self.assertAlmostEqual(port_battery_energy_delta(0,5),-1.25/.855)
        self.assertAlmostEqual(port_battery_energy_delta(5,0,mode='MAIN_PCS'),1.1875)
        self.assertAlmostEqual(port_battery_energy_delta(0,5,route_energy_kwh=2),-1.25/.855-2)
        first=port_battery_energy_delta(5,0)
        second=port_battery_energy_delta(0,first*.855/.25)
        self.assertAlmostEqual(first+second,0)
        with self.assertRaisesRegex(ValueError,'MODE'):
            port_battery_energy_delta(1,1)
        with self.assertRaisesRegex(ValueError,'CEILING'):
            port_battery_energy_delta(450,0)


if __name__ == "__main__":
    unittest.main()
