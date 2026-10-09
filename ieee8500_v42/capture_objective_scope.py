"""Read-only measurement-source audit; never imports or executes the source."""
from pathlib import Path
import json
from .integration import file_sha


def capture(root, external_source_root):
    root, external = Path(root).resolve(), Path(external_source_root).resolve()
    paths = [root / "v42_thermal/measurement.py", root / "v42_native/grid.py",
             external / "dayahead/full_ieee123_g11_v16_1.py",
             external / "dayahead/v28r2/opendss_backend.py",
             external / "dayahead/v28r2/opendss_mapping.py",
             external / "dayahead/v28r2/trajectory.py"]
    return {"schema": "IEEE8500_V42_OBJECTIVE_SOURCE_SCOPE_AUDIT_V1",
            "source_files": [{"path": str(p), "sha256": file_sha(p)} for p in paths],
            "canonical_source_objective": {
                "scope": "ALL_ENABLED_LINE_ORIENTED_PARENT_TERMINAL_NONNEUTRAL_PHASE_ROWS",
                "numerator": "abs current selected by NodeOrder==ABC(1,2,3)",
                "denominator": "compiled original Line.NormAmps",
                "terminals": "parent_bus terminal from source oriented branch roster",
                "neutral_in_objective": False, "all_terminal_maximum_in_objective": False,
                "original_topology_root": "150.1/150.2/150.3",
                "source_phase_edge_rule": "first-two-terminal common node intersection with 1/2/3"},
            "additional_physical_audit": {
                "all_terminal_conductors": True, "all_transformer_windings": True,
                "maximum_must_be_labeled_separately": True,
                "source_canonical_objective_not_silently_replaced": True},
            "ieee8500_canonical_phase_mapping": "NOT_CERTIFIED",
            "identical_min_rho_meaning_ieee123_ieee8500": "NOT_VERIFIED",
            "native_calls": 0, "OpenDSS_calls": 0, "full_model_builds": 0,
            "evidence_kind": "READ_ONLY_SOURCE_STATIC_AUDIT"}


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / "docs/ieee8500_v42_single_case/OBJECTIVE_SCOPE_AUDIT.json"
    if destination.exists():
        raise FileExistsError("OBJECTIVE_SOURCE_AUDIT_ALREADY_EXISTS")
    result = capture(root, "C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance")
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("SOURCE_ONLY: canonical parent-phase and additional full-conductor audits separated")


if __name__ == "__main__":
    main()
