"""Phase-aware OpenDSS trajectory result arrays, KPIs, and persistence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

from .backend_contract import canonical_sha256, sha256_file
from .day_state import atomic_json


@dataclass(frozen=True)
class OpenDSSResult:
    day: str
    namespace: str
    case: str
    schedule_sha256: str
    node_names: tuple[str, ...]
    node_phases: tuple[str, ...]
    branch_names: tuple[str, ...]
    branch_phases: tuple[str, ...]
    branch_kinds: tuple[str, ...]
    convergence: np.ndarray
    voltage_pu: np.ndarray
    phase_current_a: np.ndarray
    phase_current_loading_pu: np.ndarray
    transformer_total_kva_loading_pu: np.ndarray
    losses_kw_kvar: np.ndarray
    regulator_taps: np.ndarray
    capacitor_states: np.ndarray
    opendss_version: str
    elapsed_seconds: float

    def validate(self) -> None:
        slots = 96
        shapes = {
            "convergence": (self.convergence, (slots,)),
            "voltage": (self.voltage_pu, (slots, len(self.node_names))),
            "current": (self.phase_current_a, (slots, len(self.branch_names))),
            "loading": (self.phase_current_loading_pu, (slots, len(self.branch_names))),
            "tx_kva": (self.transformer_total_kva_loading_pu, (slots, len(self.branch_names))),
            "losses": (self.losses_kw_kvar, (slots, 2)),
            "taps": (self.regulator_taps, (slots, 7)),
            "caps": (self.capacitor_states, (slots, 4)),
        }
        if any(np.asarray(array).shape != shape for array, shape in shapes.values()):
            raise ValueError("V28R2_OPENDSS_RESULT_AXIS")
        finite = (
            self.voltage_pu, self.phase_current_a, self.phase_current_loading_pu,
            self.losses_kw_kvar, self.regulator_taps, self.capacitor_states,
        )
        if not all(np.isfinite(array).all() for array in finite):
            raise ValueError("V28R2_OPENDSS_RESULT_NONFINITE")
        tx_mask = np.asarray([kind == "transformer" for kind in self.branch_kinds])
        tx_values = self.transformer_total_kva_loading_pu[:, tx_mask]
        line_values = self.transformer_total_kva_loading_pu[:, ~tx_mask]
        if not np.isfinite(tx_values).all() or not np.isnan(line_values).all():
            raise ValueError("V28R2_OPENDSS_TRANSFORMER_KVA_MASK")
        if not bool(np.asarray(self.convergence, dtype=bool).all()):
            raise RuntimeError("V28R2_OPENDSS_UNEXPECTED_NONCONVERGENCE")
        if not (
            len(self.node_names) == len(self.node_phases)
            and len(self.branch_names) == len(self.branch_phases) == len(self.branch_kinds)
        ):
            raise ValueError("V28R2_OPENDSS_PHASE_AXIS")

    @property
    def summary(self) -> dict[str, object]:
        self.validate()
        line_mask = np.asarray([kind == "line" for kind in self.branch_kinds])
        tx_mask = ~line_mask
        line = self.phase_current_loading_pu[:, line_mask]
        tx_current = self.phase_current_loading_pu[:, tx_mask]
        tx_kva = self.transformer_total_kva_loading_pu[:, tx_mask]
        voltage_violation = (self.voltage_pu < 0.95 - 1e-9) | (self.voltage_pu > 1.05 + 1e-9)
        line_violation = line > 1.0 + 1e-9
        tx_current_violation = tx_current > 1.0 + 1e-9
        tx_kva_violation = tx_kva > 1.0 + 1e-9
        return {
            "artifact_id": "V28R2_FRESH_OPENDSS_TRAJECTORY_RESULT_V1",
            "status": "PHYSICAL_RESULT",
            "day": self.day, "namespace": self.namespace, "case": self.case,
            "schedule_sha256": self.schedule_sha256,
            "OpenDSS_solve_count": int(np.asarray(self.convergence, dtype=bool).sum()),
            "convergence_count": int(np.asarray(self.convergence, dtype=bool).sum()),
            "node_phase_count": len(self.node_names),
            "branch_phase_count": len(self.branch_names),
            "rho_max_AC": float(np.max(line)),
            "p95_loading": float(np.percentile(line, 95)),
            "p99_loading": float(np.percentile(line, 99)),
            "Vmin_pu": float(np.min(self.voltage_pu)),
            "Vmax_pu": float(np.max(self.voltage_pu)),
            "transformer_phase_current_loading_max": float(np.max(tx_current)),
            "transformer_total_kva_loading_max": float(np.max(tx_kva)),
            "losses_kwh": float(np.sum(self.losses_kw_kvar[:, 0]) * 0.25),
            "losses_kvarh": float(np.sum(self.losses_kw_kvar[:, 1]) * 0.25),
            "voltage_violation_count": int(voltage_violation.sum()),
            "voltage_violation_exposure": float(voltage_violation.mean()),
            "line_current_violation_count": int(line_violation.sum()),
            "line_current_violation_exposure": float(line_violation.mean()),
            "transformer_current_violation_count": int(tx_current_violation.sum()),
            "transformer_current_violation_exposure": float(tx_current_violation.mean()),
            "transformer_kva_violation_count": int(tx_kva_violation.sum()),
            "transformer_kva_violation_exposure_phase_rows": float(tx_kva_violation.mean()),
            "physical_violation": bool(
                voltage_violation.any() or line_violation.any()
                or tx_current_violation.any() or tx_kva_violation.any()
            ),
            "schedule_mutation_count": 0,
            "clean_engine_count": 1,
            "elapsed_seconds": float(self.elapsed_seconds),
            "opendss_version": self.opendss_version,
        }

    def violation_rows(self) -> list[dict[str, object]]:
        self.validate()
        rows: list[dict[str, object]] = []
        for slot, node in zip(*np.where((self.voltage_pu < .95 - 1e-9) | (self.voltage_pu > 1.05 + 1e-9))):
            rows.append({
                "slot": int(slot), "kind": "VOLTAGE", "asset": self.node_names[node],
                "phase": self.node_phases[node], "value": float(self.voltage_pu[slot, node]),
                "lower_limit": .95, "upper_limit": 1.05,
            })
        for slot in range(96):
            for branch, (name, phase, kind) in enumerate(zip(
                self.branch_names, self.branch_phases, self.branch_kinds, strict=True,
            )):
                current = float(self.phase_current_loading_pu[slot, branch])
                if current > 1.0 + 1e-9:
                    rows.append({
                        "slot": slot, "kind": f"{kind.upper()}_PHASE_CURRENT",
                        "asset": name, "phase": phase, "value": current, "upper_limit": 1.0,
                    })
                kva = float(self.transformer_total_kva_loading_pu[slot, branch])
                if kind == "transformer" and kva > 1.0 + 1e-9:
                    rows.append({
                        "slot": slot, "kind": "TRANSFORMER_TOTAL_KVA_PHASE_ROW",
                        "asset": name, "phase": phase, "value": kva, "upper_limit": 1.0,
                    })
        return rows

    def write(self, output: Path) -> Mapping[str, object]:
        self.validate()
        output.mkdir(parents=True, exist_ok=True)
        arrays_path = output / "OPENDSS_PHASE_ARRAYS.npz"
        temporary = output / f"OPENDSS_PHASE_ARRAYS.{os.getpid()}.tmp.npz"
        np.savez_compressed(
            temporary,
            node_names=np.asarray(self.node_names), node_phases=np.asarray(self.node_phases),
            branch_names=np.asarray(self.branch_names), branch_phases=np.asarray(self.branch_phases),
            branch_kinds=np.asarray(self.branch_kinds), convergence=self.convergence,
            voltage_pu=self.voltage_pu, phase_current_a=self.phase_current_a,
            phase_current_loading_pu=self.phase_current_loading_pu,
            transformer_total_kva_loading_pu=self.transformer_total_kva_loading_pu,
            losses_kw_kvar=self.losses_kw_kvar, regulator_taps=self.regulator_taps,
            capacitor_states=self.capacitor_states,
        )
        os.replace(temporary, arrays_path)
        summary_path = output / "OPENDSS_SUMMARY.json"
        violations_path = output / "OPENDSS_VIOLATIONS.json"
        atomic_json(summary_path, self.summary)
        atomic_json(violations_path, {
            "artifact_id": "V28R2_FRESH_OPENDSS_VIOLATIONS_V1",
            "physical_violations_are_results": True,
            "rows": self.violation_rows(),
        })
        manifest = {
            "artifact_id": "V28R2_FRESH_OPENDSS_OUTPUT_MANIFEST_V1",
            "day": self.day, "namespace": self.namespace, "case": self.case,
            "schedule_sha256": self.schedule_sha256,
            "files": {
                path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
                for path in (arrays_path, summary_path, violations_path)
            },
        }
        manifest["manifest_payload_sha256"] = canonical_sha256(manifest)
        atomic_json(output / "OPENDSS_OUTPUT_MANIFEST.json", manifest)
        return manifest
