from __future__ import annotations
import json, shutil, time
from pathlib import Path
import pandas as pd
from .context import Context
from .locate import locate_inputs
from .calibration import calibrate
from .trajectory import build as build_trajectory
from .capacity import build as build_capacity
from .scenarios import representative
from .validate import validate
from .report import write as write_report
from .utils import setup_logger,write_json,write_parquet_checked,create_review_zip,sha256_file


def run(ctx: Context)->Path:
    for p in [ctx.run_dir,ctx.output_dir,ctx.scenario_dir,ctx.report_dir,ctx.log_dir]: p.mkdir(parents=True,exist_ok=True)
    logger=setup_logger(ctx.log_dir/"execution.log"); start=time.time(); ctx.inputs=locate_inputs(ctx.config,logger); shutil.copy2(ctx.config_path,ctx.run_dir/"pipeline_used.yaml")
    write_json(ctx.report_dir/"input_metadata.json",{"k5c2":ctx.inputs.k5c2,"k5a":ctx.inputs.k5a,"k5b3":ctx.inputs.k5b3})
    comp=ctx.config["resources"]["parquet_compression"]
    logger.info("Calibrating flexible-event scores from rolling OOF predictions")
    cal,cross=calibrate(ctx.inputs.k5b3,ctx.inputs.k5a,ctx.config)
    write_parquet_checked(cal.probabilities,ctx.scenario_dir/"calibrated_event_probabilities_2025.parquet",compression=comp)
    write_parquet_checked(cal.hazard_wide,ctx.scenario_dir/"calibrated_event_hazard_2025_wide.parquet",compression=comp)
    write_parquet_checked(cross,ctx.scenario_dir/"oof_temporal_cross_calibration_predictions.parquet",compression=comp)
    cal.audit.to_csv(ctx.report_dir/"calibration_cross_validation_metrics.csv",index=False,encoding="utf-8-sig"); write_json(ctx.report_dir/"calibration_maps.json",cal.maps); write_json(ctx.report_dir/"calibration_summary.json",cal.summary)
    mark=pd.read_parquet(ctx.inputs.k5c2/"scenarios/flexible_positive_mark_library.parquet")
    write_parquet_checked(mark,ctx.scenario_dir/"flexible_positive_mark_library.parquet",compression=comp)
    rep=representative(cal.hazard_wide,mark,ctx.config); write_parquet_checked(rep,ctx.scenario_dir/"representative_calibrated_flexible_scenarios.parquet",compression=comp)
    logger.info("Building 48-step fixed-load trajectories")
    traj=build_trajectory(ctx.inputs.k5c2,ctx.inputs.k5a,ctx.config); write_parquet_checked(traj.trajectory,ctx.output_dir/"fixed_48step_trajectory_2025.parquet",compression=comp); write_json(ctx.report_dir/"fixed_trajectory_audit.json",traj.audit)
    logger.info("Building pre-2025 capacity and rack sensitivity cases")
    cap=build_capacity(ctx.inputs.k5c2,ctx.inputs.k5a,ctx.config)
    cap.all_site.to_csv(ctx.output_dir/"capacity_sensitivity_site_parameters.csv",index=False,encoding="utf-8-sig"); cap.all_rack.to_csv(ctx.output_dir/"capacity_rack_sensitivity_parameters.csv",index=False,encoding="utf-8-sig"); cap.summary.to_csv(ctx.output_dir/"capacity_rack_sensitivity_summary.csv",index=False,encoding="utf-8-sig")
    cap.main_site.to_csv(ctx.output_dir/"optimization_main_site_capacity.csv",index=False,encoding="utf-8-sig"); cap.main_rack.to_csv(ctx.output_dir/"optimization_main_rack_parameters.csv",index=False,encoding="utf-8-sig"); write_parquet_checked(cap.main_envelope,ctx.output_dir/"optimization_main_power_envelope_2025_5min.parquet",compression=comp); write_json(ctx.report_dir/"capacity_rack_audit.json",cap.audit)
    art={"probabilities":cal.probabilities,"hazard":cal.hazard_wide,"trajectory":traj.trajectory,"trajectory_audit":traj.audit,"capacity":cap,"calibration_audit":cal.audit,"calibration_summary":cal.summary}
    val=validate(art,ctx.config); write_json(ctx.report_dir/"validation.json",val); write_report(ctx.report_dir/"REPORT.md",val,cal.summary,traj.audit,cap.audit); write_json(ctx.report_dir/"run_timing.json",{"elapsed_seconds":time.time()-start})
    for name in ["generate_calibrated_flexible_scenarios.py","load_optimization_window.py"]: shutil.copy2(ctx.package_root/name,ctx.run_dir/name)
    if val["status"]!="success": raise RuntimeError(f"Stage K5-C3 validation failed: {val['checks']}")
    manifest=[]
    for p in sorted(ctx.run_dir.rglob("*")):
        if p.is_file(): manifest.append({"relative_path":str(p.relative_to(ctx.run_dir)),"size_bytes":p.stat().st_size,"sha256":sha256_file(p)})
    write_json(ctx.run_dir/"manifest.json",manifest)
    stamp=ctx.run_dir.name.split("stage_k5c3_")[-1]; review=Path(ctx.config["paths"]["work_root"])/f"stage_k5c3_optimization_ready_review_{stamp}.zip"
    rows=create_review_zip(ctx.run_dir,review,float(ctx.config["resources"]["review_max_file_mb"]),bool(ctx.config["resources"]["review_include_large_files"])); pd.DataFrame(rows).to_csv(ctx.report_dir/"review_zip_inventory.csv",index=False,encoding="utf-8-sig"); create_review_zip(ctx.run_dir,review,float(ctx.config["resources"]["review_max_file_mb"]),bool(ctx.config["resources"]["review_include_large_files"]))
    logger.info("Stage K5-C3 success: %s",ctx.run_dir); logger.info("Review ZIP: %s",review); return review
