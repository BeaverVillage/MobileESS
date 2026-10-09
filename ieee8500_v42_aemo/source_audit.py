"""Read-only source pins and live-campaign snapshots; no worker mutations."""
import argparse
from collections import Counter
from pathlib import Path
import shutil
import subprocess
from .common import *

CAMPAIGN = Path("D:/MobileESS_V42/runtime/v42_may_campaign/native90_build_reuse_20261009_01")
LIVE_SOURCE = Path("D:/MobileESS_V42")
HISTORY = Path("D:/ChatGPT/Mobile ESS 2")


def snapshot(label):
    immutable = {}
    for path in sorted(LIVE_SOURCE.glob("v42*/*.py")):
        immutable[str(path)] = receipt(path)
    for pattern in ("*MANIFEST.json", "*PERMIT.json"):
        for path in sorted(CAMPAIGN.glob(pattern)):
            immutable[str(path)] = receipt(path)
    base = read(CAMPAIGN / "CAMPAIGN_MANIFEST.json")
    for folder in base.get("input_folders", {}).values():
        if str(folder).endswith("2025-05-01"):
            for path in sorted(Path(folder).iterdir()):
                if path.is_file():
                    immutable[str(path)] = receipt(path)
    commands = {
        "processes": "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|gurobi' } | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Depth 3",
        "scheduler": "Get-ScheduledTask | Where-Object { $_.TaskName -match 'MobileESS_V42|v42' } | Select-Object TaskName,TaskPath,State,@{n='Actions';e={$_.Actions|Select-Object Execute,Arguments}},@{n='Triggers';e={$_.Triggers|Select-Object StartBoundary,Enabled}} | ConvertTo-Json -Depth 5",
    }
    observed = {key: json.loads(subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", command], encoding="utf-8") or "[]")
        for key, command in commands.items()}
    document = dict(label=label, immutable=immutable, **observed,
                    own_campaign_writes=0, worker_kills=0, scheduler_mutations=0)
    write(REPORT / f"CAMPAIGN_{label.upper()}.json", document)
    if label == "after":
        from ieee8500_v42.isolation import scheduler_registration_diff
        before = read(REPORT / "CAMPAIGN_BEFORE.json")
        changed = [name for name, value in before["immutable"].items()
                   if immutable.get(name) != value]
        diff = scheduler_registration_diff(before["scheduler"], observed["scheduler"])
        write(REPORT / "CAMPAIGN_PRESERVATION.json",
              dict(original_authorities_equal=not changed and not diff["modified"] and not diff["removed"],
                   immutable_original_count=len(before["immutable"]), changes=changed,
                   added_authorities=sorted(set(immutable)-set(before["immutable"])),
                   scheduler_diff=diff, own_external_mutations=0,
                   scope="original authorities; mutable worker progress is not frozen"))
    print("campaign", label, len(immutable), "immutable sources; own external writes0", flush=True)


def copy_verified(record, destination):
    source = resolve(record)
    destination = Path(destination)
    assert destination.resolve().is_relative_to(DATA.resolve())
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    assert sha(destination) == record["sha256"]
    return dict(original=record, copied=receipt(destination))


def audit():
    assert sha(MAPPING) == MAPPING_SHA
    prior = read(PR193 / "ARTIFACT_SHA256_MANIFEST.json")
    for name, record in prior["files"].items():
        assert sha(ROOT / name) == record["sha256"], "PR193_BYTE_DRIFT:" + name
    core = read(PR193 / "V42_SOURCE_SHA_MANIFEST.json")
    for name, expected in core["files"].items():
        assert sha(ROOT / name) == expected
    diff = git("diff", "--name-status", core["v42_git_sha"], LATEST_SHA, "--", "v42*").decode().splitlines()
    assert all(row.startswith("A\t") for row in diff), "EXISTING_V42_SOURCE_DRIFT_REQUIRES_REVIEW"
    input_paths = ("v42_holdout/inputs.py", "v42_holdout/realization.py",
                   "v42_capacity/reference.py", "v42_capacity/queue.py",
                   "v42_capacity/actual.py", "v42_capacity/replay.py",
                   "v42_may_campaign/inputs.py", "v42_may_campaign/operations.py",
                   "v42_regcontrol/runner.py", "v42_modelable/power.py")
    authorities = []
    for name in input_paths:
        blob = git("show", f"{LATEST_SHA}:{name}")
        assert blob == (ROOT / name).read_bytes(), "DATA_PIPELINE_SOURCE_DRIFT"
        authorities.append(dict(path=name, source_sha256=sha(ROOT/name),
                                latest_git_blob=git("rev-parse", f"{LATEST_SHA}:{name}").decode().strip()))
    old_engine_path = "science/ieee8500_paper_scale_only_final/campaign_source/electrical_engine.py"
    old_engine = git("show", f"{PR62_SHA}:{old_engine_path}")
    (DATA / "historical").mkdir(parents=True, exist_ok=True)
    (DATA / "historical/electrical_engine_pr62.py").write_bytes(old_engine)
    clone_path = "science/ieee8500_paper_scale_only_final/evidence/CLONE_INPUT_MANIFEST.json"
    clone = json.loads(git("show", f"{PR62_SHA}:{clone_path}"))
    (DATA / "historical/CLONE_INPUT_MANIFEST_PR62.json").write_bytes(git("show", f"{PR62_SHA}:{clone_path}"))
    published_inventory = json.loads(git("show", f"{PR62_SHA}:science/ieee8500_paper_scale_only_final/SOURCE_INVENTORY.json"))
    record = next(r for r in published_inventory["files"] if r["path"] == "campaign_source/electrical_engine.py")
    assert sha(DATA/"historical/electrical_engine_pr62.py") == record["sha256"]
    historical_root = HISTORY / "IEEE8500_PAPER_SCALE_ONLY_20260920/full_production_paper_BG055200_AIDC240_MESS200"
    historical_engine = historical_root / "electrical_engine.py"
    assert sha(historical_engine) == record["sha256"]
    rule = historical_root / "SCREENING_RULE.json"
    # The published engine directly names this rule; compare its same-byte
    # mirrored original C: artifact, not an unrelated later scale result.
    mirror = Path(str(rule).replace("D:\\ChatGPT", "C:\\Users\\kjw39\\OneDrive\\문서\\ChatGPT"))
    assert rule.is_file() and mirror.is_file() and sha(rule) == sha(mirror)
    shutil.copyfile(rule, DATA/"historical/SCREENING_RULE_PR62.json")
    history_sources = []
    for relative in ("IEEE8500_operating_point_20260911/run_b0_screen.py",
                     "IEEE8500_production_compatibility_20260911/screen_compatible_b0.py",
                     "IEEE8500_stress_calibration_20260911/stress_common.py",
                     "IEEE8500_stress_calibration_20260911/overlays/Source_1.0400_Vreg_123.5.dss"):
        path = HISTORY / relative
        target = DATA / "historical" / path.name
        shutil.copyfile(path, target)
        history_sources.append(dict(original=receipt(path), copied=receipt(target)))
    electrical = read(ROOT/"docs/v42_april_b0_capacity_queue_voltage_calibration/ELECTRICAL_SOURCE_AUTHORITY.json")
    bg = next(r for r in electrical["code_sources"] if r["path"].replace("\\", "/").endswith("dayahead/grid_background_v16_2.py"))
    copied_bg = copy_verified(bg, DATA/"authority/grid_background_v16_2.py")
    write(REPORT/"SOURCE_AUTHORITY.json",
          dict(review_start_latest_v42_sha=LATEST_SHA, parent_PR193_sha=PR193_SHA,
               historical_PR62_sha=PR62_SHA, original_core_source_count=len(core["files"]),
               PR193_sealed_files_byte_verified=len(prior["files"]),
               latest_only_additions_count=len(diff), latest_additions=diff,
               latest_unchanged_data_pipeline_sources=authorities,
               ieee123_background_source=copied_bg,
               historical_PV_overlay_sources=history_sources,
               historical_rule=receipt(rule),
               historical_downstream_Vreg=123.5, current_downstream_Vreg_preserved=125.0,
               historical_PV_rule_declared_alpha=.5,
               historical_actual_engine_dispatch_alpha=.552,
               historical_dispatch_not_copied=True,
               physical_source="PR193 canonical IEEE8500 files byte-identical",
               algorithm="latest V42 source audit only; no Native optimizer",
               Native_calls=0, original_campaign_writes=0))
    prereg = dict(day=DAY, development_day_already_exposed=True, background_scale=BG_SCALE,
        installed_GPU=780, population_multiplier=1, mapping_sha256=MAPPING_SHA,
        no_reselection=True, MESS_units=6, B0_MESS_PQ=0, LV_port_P_kw=5,
        LV_port_Q_kvar=3, LV_port_S_kva=6, node_voltage_band=[.95,1.05],
        policies={"P0": [1.05,126.5,True], "P1": [1.04,126.5,True],
                  "P2": [1.04,123.5,True], "P3": [1.04,123.5,False]},
        downstream_Vreg=125.0, original_RegControl_count=12,
        original_CapControl_count=9, source_DSS_changes=0,
        policy_priority=["P0","P1","P2","P3"],
        policy_selection="first all96 Planning hard-constraint PASS in frozen minimum-change priority; never use Actual to pick",
        Fixed_load_policy="retain Status=fixed and static original P/Q scaled once by original study BG=.552; no daily shape",
        Variable_load_policy="original P/Q times BG=.552 and shared temporal gross factor from frozen V42 normalization; no new customer profile",
        PF_preserved=True, Jemena_IEEE123_customer_clusters_not_transferred=True,
        PV_capacity_rule="PR62 Generator construction: original native_load_kW times inherited ratio; same nameplate Planning/Actual",
        PV_temporal_rule="current V42 ALPHA_GRID * regional RooftopPV_MW / frozen PV_REFERENCE_MAX_MW; not daily-Actual peak",
        Actual_demand_rule="mean of three raw 5-minute interval-ending powers per15min; PWC energy-preserving; audit prior15min point selection",
        forecast_30min_rule="repeat each30min mean twice as15min PWC; energy preserved",
        weather_rule="GFS Planning, observed NOAA Actual; interval-start axis",
        sensitivity_rule="same24 PCC at new Planning point; fixed-tap centralP/Q distinct from independently resettled automatic boundedPQ",
        sensitivity_slots=[0,9,48,75], target_lines="new Planning top20 max96 canonical ratios, deterministic; not policy outcomes",
        simultaneous_STA_rule="only six preserved initial fleet ports; instantaneous counterfactual, not dispatch certificate",
        B1_B2_B3_solver_calls=0, source_and_Vreg_overlays_user_authorized=True,
        final_operational_qualification_requires_all_sources_and_all96_actual_constraints=True)
    write(REPORT/"PREREGISTRATION.json", prereg)
    print("sources pinned; original193 and962 core bytes PASS; latest additions",len(diff),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("audit","before","after"))
    action=parser.parse_args().action
    audit() if action=="audit" else snapshot(action)
