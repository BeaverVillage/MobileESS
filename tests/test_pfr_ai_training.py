from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from pfr.authority import load_scientific_rebase_authority
from pfr.data_authority import (
    AuthorityKind,
    DataAuthorityError,
    DatasetAuthority,
    DatasetRole,
    FixedInferenceLoad,
    MeasuredPowerUtilizationEnvelope,
    PowerUtilizationPoint,
    measured_field_flags,
    reject_row_wise_cross_dataset_merge,
    validate_dataset_contract,
)
from pfr.training import (
    CheckpointStatePayload,
    DatasetPayload,
    JobLifecycle,
    KestrelOperationalJob,
    ParameterAuthority,
    PreemptibilityMode,
    TrainingParameterization,
    TrainingStateError,
    advance_restart,
    arrive,
    baseline_compute_work_gpu_hours,
    begin_migration,
    complete_migration,
    gang_allocation_feasible,
    mark_ready,
    migration_payload_bytes,
    run_compute_step,
    run_compute_fraction_step,
    start_running,
    validate_assignment_transition,
)


class PfrTrainingFoundationTests(unittest.TestCase):
    def parameterization(self, *, checkpoint_steps: int = 2) -> TrainingParameterization:
        return TrainingParameterization(
            total_work=10.0,
            checkpoint_eligible=True,
            checkpoint_interval_steps=checkpoint_steps,
            checkpoint_state_bytes=None,
            eligible_sites=("IDC01", "IDC02"),
            min_compute_rate_per_hour=1.0,
            max_compute_rate_per_hour=6.0,
            power_authority_id="H100_POWER_UTIL_ENVELOPE_V1",
            model_family=None,
            authority_by_field={
                "total_work": ParameterAuthority.MODELED,
                "checkpoint_interval_steps": ParameterAuthority.MODELED,
                "checkpoint_state_bytes": ParameterAuthority.UNRESOLVED,
                "power_authority_id": ParameterAuthority.EXTERNAL_MEASURED,
            },
        )

    def job(self, *, checkpoint_steps: int = 2):
        source = KestrelOperationalJob(
            job_uid="job-1",
            arrival_step=10,
            deadline_step=30,
            requested_gpu_count=8,
            runtime_seconds_source=3600.0,
            input_bytes=1000,
            source_record_id="kestrel-row-1",
        )
        return source.to_training_state(
            self.parameterization(checkpoint_steps=checkpoint_steps)
        )

    def running_job(self, *, checkpoint_steps: int = 2):
        state = arrive(self.job(checkpoint_steps=checkpoint_steps))
        state = mark_ready(state)
        return start_running(
            state,
            site="IDC01",
            logical_rack="RACK01",
            gang_membership=tuple(f"gpu-{index}" for index in range(8)),
        )

    def test_source_derived_initial_work_is_gang_times_baseline_runtime(self):
        source = KestrelOperationalJob(
            job_uid="job-source-derived",
            arrival_step=0,
            deadline_step=20,
            requested_gpu_count=8,
            runtime_seconds_source=7200.0,
            input_bytes=0,
            source_record_id="row-source-derived",
        )
        self.assertEqual(baseline_compute_work_gpu_hours(source), 16.0)
        parameterization = replace(
            self.parameterization(),
            total_work=16.0,
            authority_by_field={"total_work": ParameterAuthority.SOURCE_DERIVED},
            preemptibility_mode=PreemptibilityMode.CHECKPOINT_ONLY,
        )
        state = source.to_training_state(parameterization)
        self.assertEqual(state.total_work, 16.0)

    def test_scientific_rebase_authority_is_sealed(self):
        authority = load_scientific_rebase_authority()
        self.assertFalse(authority["main_scientific_campaign_started"])
        self.assertEqual(
            authority["legacy_authority"]["G12E"], "FORENSIC_EVIDENCE_ONLY"
        )

    def test_dataset_roles_and_provenance(self):
        records = (
            DatasetAuthority(
                dataset_family="KESTREL_F30",
                role=DatasetRole.MAIN_OPERATIONAL,
                source_identity="kestrel-sha",
                sha256="0" * 64,
                measured_fields=("arrival_timestamp_ns", "requested_gpu"),
                optimizer_input_allowed=True,
            ),
            DatasetAuthority(
                dataset_family="H100_B200_HIGH_RES_TRAINING",
                role=DatasetRole.MEASURED_POWER_UTILIZATION,
                source_identity="figshare-sha",
                sha256="1" * 64,
                measured_fields=("gpu_power_w", "gpu_utilization_percent"),
                modeled_or_unresolved_fields=("training_throughput",),
                calibration_only=True,
            ),
        )
        validate_dataset_contract(records)

    def test_cross_trace_row_merge_is_rejected(self):
        with self.assertRaises(DataAuthorityError):
            reject_row_wise_cross_dataset_merge("KESTREL_F30", "ALIBABA_GPU_2026")

    def test_kestrel_architecture_label_boundary(self):
        parameterization = replace(
            self.parameterization(),
            model_family="Llama",
            authority_by_field={"model_family": ParameterAuthority.KESTREL_MEASURED},
        )
        with self.assertRaises(TrainingStateError):
            parameterization.validate()

    def test_gang_all_or_nothing(self):
        self.assertTrue(gang_allocation_feasible(8, "IDC01", {"IDC01": 8}))
        self.assertFalse(gang_allocation_feasible(8, "IDC01", {"IDC01": 7}))
        self.assertFalse(
            gang_allocation_feasible(8, "IDC01", {"IDC01": 4, "IDC02": 4})
        )
        with self.assertRaises(TrainingStateError):
            run_compute_step(
                self.running_job(),
                allocated_gpus_by_site={"IDC01": 4, "IDC02": 4},
                effective_compute_rate_per_hour=3.0,
                dt_hours=1 / 12,
            )

    def test_checkpoint_boundary_only_migration(self):
        running = self.running_job(checkpoint_steps=1)
        with self.assertRaises(TrainingStateError):
            begin_migration(running, destination="IDC02")
        boundary = run_compute_step(
            running,
            allocated_gpus_by_site={"IDC01": 8},
            effective_compute_rate_per_hour=3.0,
            dt_hours=1 / 12,
        )
        self.assertEqual(boundary.lifecycle, JobLifecycle.CHECKPOINT_READY)
        migrating = begin_migration(boundary, destination="IDC02")
        restarting = complete_migration(
            migrating, restart_steps=2, destination_logical_rack="RACK02"
        )
        self.assertEqual(restarting.current_site, "IDC02")
        self.assertEqual(advance_restart(restarting, elapsed_steps=2).lifecycle, JobLifecycle.RUNNING)

    def test_assignment_is_immutable_between_checkpoints(self):
        running = self.running_job()
        with self.assertRaises(TrainingStateError):
            validate_assignment_transition(running, replace(running, current_site="IDC02"))
        with self.assertRaises(TrainingStateError):
            validate_assignment_transition(
                running, replace(running, required_gpu_gang_size=4)
            )

    def test_remaining_work_and_gpuh_are_separate(self):
        result = run_compute_step(
            self.running_job(checkpoint_steps=10),
            allocated_gpus_by_site={"IDC01": 8},
            effective_compute_rate_per_hour=3.0,
            dt_hours=0.5,
        )
        self.assertAlmostEqual(result.remaining_work, 8.5)
        self.assertAlmostEqual(result.resource_gpuh, 4.0)
        self.assertNotEqual(result.remaining_work, result.resource_gpuh)

    def test_five_minute_fraction_progress_contract(self):
        running = replace(
            self.running_job(checkpoint_steps=10),
            min_compute_rate_per_hour=0.0,
            max_compute_rate_per_hour=8.0,
        )
        result = run_compute_fraction_step(
            running,
            allocated_gpus_by_site={"IDC01": 8},
            compute_rate_fraction=0.75,
        )
        self.assertAlmostEqual(result.remaining_work, 9.5)

    def test_remaining_work_is_nonnegative(self):
        result = run_compute_step(
            replace(self.running_job(checkpoint_steps=10), remaining_work=0.2),
            allocated_gpus_by_site={"IDC01": 8},
            effective_compute_rate_per_hour=6.0,
            dt_hours=1.0,
        )
        self.assertEqual(result.remaining_work, 0.0)
        self.assertEqual(result.lifecycle, JobLifecycle.COMPLETED)

    def test_migration_payload_avoids_double_counting(self):
        checkpoint = CheckpointStatePayload(
            aggregate_bytes=100,
            component_bytes={"model": 30, "optimizer": 70},
        )
        with self.assertRaises(TrainingStateError):
            migration_payload_bytes((), {}, checkpoint)

    def test_destination_inventory_reduces_payload(self):
        datasets = (DatasetPayload("train", 1000), DatasetPayload("code", 100))
        payload = migration_payload_bytes(
            datasets,
            {"train": 750, "code": 100},
            CheckpointStatePayload(component_bytes={"model": 30, "optimizer": 70}),
        )
        self.assertEqual(payload, 350)

    def test_inference_is_fixed_background(self):
        load = FixedInferenceLoad("IDC01", 100.0, "inference-source")
        load.validate()
        with self.assertRaises(DataAuthorityError):
            load.with_flexibility(True)

    def test_measured_and_unresolved_flags_are_disjoint(self):
        flags = measured_field_flags(("power",), ("throughput", "checkpoint"))
        self.assertEqual(flags["power"], AuthorityKind.MEASURED)
        self.assertEqual(flags["throughput"], AuthorityKind.UNRESOLVED)
        with self.assertRaises(DataAuthorityError):
            measured_field_flags(("power",), ("power",))

    def test_power_utilization_envelope_is_not_throughput_curve(self):
        envelope = MeasuredPowerUtilizationEnvelope(
            gpu_type="H100",
            source_identity="figshare-archive",
            source_sha256="c" * 64,
            points=(
                PowerUtilizationPoint(0.0, 1000.0, 0.0),
                PowerUtilizationPoint(0.02, 5361.54, 100.0),
            ),
        )
        self.assertEqual(envelope.power_domain_w, (1000.0, 5361.54))
        with self.assertRaises(DataAuthorityError):
            replace(envelope, throughput_target_status=AuthorityKind.MEASURED).validate()

    def test_contract_json_files_parse(self):
        root = Path(__file__).resolve().parents[1] / "pfr" / "contracts"
        for path in root.glob("*.json"):
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))

    def test_no_forbidden_production_modules(self):
        package = Path(__file__).resolve().parents[1] / "pfr"
        names = {path.name for path in package.rglob("*.py")}
        self.assertNotIn("sitecustomize.py", names)
        self.assertNotIn("z_route.py", names)


if __name__ == "__main__":
    unittest.main()
