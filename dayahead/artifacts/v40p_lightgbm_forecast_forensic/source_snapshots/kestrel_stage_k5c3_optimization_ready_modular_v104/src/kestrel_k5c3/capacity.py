from __future__ import annotations
from dataclasses import dataclass
import numpy as np, pandas as pd
from .utils import round_up_multiple, allocate_integer_capacity, capped_proportional_allocation

@dataclass
class CapacityResult:
    all_site: pd.DataFrame
    all_rack: pd.DataFrame
    summary: pd.DataFrame
    main_site: pd.DataFrame
    main_rack: pd.DataFrame
    main_envelope: pd.DataFrame
    audit: dict


def _scenario_id(q,u,label): return f"q{int(round(q*1000)):03d}_u{int(round(u*100)):02d}_r{label}"

def build(k5c2,k5a,cfg):
    year=int(cfg["analysis"]["year"]); ccfg=cfg["capacity_sensitivity"]; pool_count=int(cfg["analysis"].get("rack_pool_count",4))
    site=pd.read_parquet(k5a/"outputs/kestrel_12idc_5min_workload.parquet",columns=["timestamp_utc","idc_id","total_avg_active_gpus","fixed_avg_active_gpus_F30","flexible_avg_active_gpus_F30"])
    site["timestamp_utc"]=pd.to_datetime(site.timestamp_utc,utc=True); site["idc_id"]=site.idc_id.astype(str)
    cutoff=pd.Timestamp(ccfg["calibration_period_end"]); cutoff=cutoff.tz_convert("UTC") if cutoff.tzinfo else cutoff.tz_localize("UTC")
    dev=site[site.timestamp_utc<=cutoff].copy(); test=site[site.timestamp_utc.dt.year.eq(year)].copy()
    base=pd.read_csv(k5c2/"outputs/rack_equivalent_4pool_parameters.csv")
    factors=(base.sort_values(["idc_id","pool_id"]).groupby("pool_id",as_index=False).first()[["pool_id","eagle_node_count_share","eagle_idle_share_blended","eagle_cap_proxy_share","source_cluster"]].sort_values("pool_id"))
    if len(factors)!=4: raise ValueError(f"Expected 4 pool factors, found {len(factors)}")
    cap_share=factors.eagle_node_count_share.to_numpy(float); idle_share=factors.eagle_idle_share_blended.to_numpy(float); power_share=factors.eagle_cap_proxy_share.to_numpy(float)
    power_share=power_share/power_share.sum(); idle_share=idle_share/idle_share.sum(); cap_share=cap_share/cap_share.sum()
    paired=pd.read_csv(k5c2/"outputs/paired_h100_power_scenarios_corrected.csv"); mainp=paired[paired.scenario.astype(str).eq("median")].iloc[0]
    idle=float(mainp.idle_it_kw_per_gpu); inc=float(mainp.incremental_it_kw_per_gpu)
    site_rows=[]; rack_rows=[]; summaries=[]
    multiple=int(ccfg["capacity_rounding_gpus"]); min_each=int(ccfg["minimum_gpus_per_pool"])
    for q in map(float,ccfg["quantiles"]):
      for util in map(float,ccfg["target_utilizations"]):
       for label,rf in ccfg["rack_active_fractions"].items():
        rf=float(rf); sid=_scenario_id(q,util,label)
        caps={}; dels={}
        for idc,g in dev.groupby("idc_id"):
            peak=float(g.total_avg_active_gpus.quantile(q)); cap=round_up_multiple(max(peak/util, min_each*pool_count),multiple)
            installed=allocate_integer_capacity(cap,cap_share,multiple,min_each)
            total_deliv=float(cap*rf); deliver=capped_proportional_allocation(total_deliv,power_share,installed)
            total_idle=cap*idle; rack_idle=total_idle*idle_share
            caps[str(idc)]=cap; dels[str(idc)]=deliver.sum()
            site_rows.append({"scenario_id":sid,"capacity_quantile":q,"target_utilization":util,"rack_case":label,"rack_active_fraction":rf,"idc_id":str(idc),"active_gpu_at_development_quantile":peak,"installed_gpu_capacity":cap,"deliverable_active_gpu_capacity":float(deliver.sum()),"development_period_end_utc":cutoff})
            for j,row in factors.reset_index(drop=True).iterrows():
                rack_rows.append({"scenario_id":sid,"capacity_quantile":q,"target_utilization":util,"rack_case":label,"rack_active_fraction":rf,"idc_id":str(idc),"pool_id":int(row.pool_id),"installed_gpu_capacity":int(installed[j]),"deliverable_active_gpu_capacity":float(deliver[j]),"idle_it_kw":float(rack_idle[j]),"rack_power_cap_kw":float(rack_idle[j]+deliver[j]*inc),"eagle_node_count_share":cap_share[j],"eagle_idle_share_blended":idle_share[j],"eagle_cap_proxy_share":power_share[j],"source_cluster":row.source_cluster,"source":"Pre-2025 capacity sizing; Eagle relative rack heterogeneity; synthetic active-fraction sensitivity"})
        devcap=dev.idc_id.map(dels).to_numpy(float); testcap=test.idc_id.map(dels).to_numpy(float)
        summaries.append({"scenario_id":sid,"capacity_quantile":q,"target_utilization":util,"rack_case":label,"rack_active_fraction":rf,"total_installed_gpu_capacity":int(sum(caps.values())),"total_deliverable_active_gpu_capacity":float(sum(dels.values())),"deliverable_to_installed_ratio":float(sum(dels.values())/sum(caps.values())),"development_exceedance_rate":float((dev.total_avg_active_gpus.to_numpy(float)>devcap+1e-9).mean()),"analysis_year_exceedance_rate":float((test.total_avg_active_gpus.to_numpy(float)>testcap+1e-9).mean()),"development_mean_active_to_installed_ratio":float(dev.total_avg_active_gpus.sum()/len(dev.timestamp_utc.unique())/sum(caps.values())),"analysis_mean_active_to_installed_ratio":float(test.total_avg_active_gpus.sum()/len(test.timestamp_utc.unique())/sum(caps.values())),"training_idle_it_kw_total":float(sum(caps.values())*idle)})
    allsite=pd.DataFrame(site_rows); allrack=pd.DataFrame(rack_rows); summary=pd.DataFrame(summaries)
    mc=ccfg["main_case"]; mainid=_scenario_id(float(mc["quantile"]),float(mc["target_utilization"]),str(mc["rack_case"]))
    mainsite=allsite[allsite.scenario_id.eq(mainid)].copy(); mainrack=allrack[allrack.scenario_id.eq(mainid)].copy()
    inference=pd.read_parquet(k5c2/"outputs/idc_inference_token_aware_2025_5min.parquet",columns=["timestamp_utc","idc_id","inference_idle_kw","inference_request_incremental_kw","inference_it_kw"])
    inference["timestamp_utc"]=pd.to_datetime(inference.timestamp_utc,utc=True); inference["idc_id"]=inference.idc_id.astype(str)
    agg = mainrack.groupby("idc_id", as_index=False).agg(
        training_idle_kw=("idle_it_kw", "sum"),
        installed_max_active_gpus=("installed_gpu_capacity", "sum"),
        nominal_deliverable_max_active_gpus=("deliverable_active_gpu_capacity", "sum"),
        rack_power_cap_kw=("rack_power_cap_kw", "sum"),
    )
    env=test.merge(agg,on="idc_id",how="left").merge(inference,on=["timestamp_utc","idc_id"],how="left",validate="one_to_one")
    infcols=["inference_idle_kw","inference_request_incremental_kw","inference_it_kw"]; env[infcols]=env[infcols].fillna(0)
    other=float(cfg["power"]["other_static_fraction_of_idle"]); pue=float(cfg["power"]["main_pue"])
    env["other_static_kw"] = other * (env.training_idle_kw + env.inference_idle_kw)

    # The 2025 Kestrel trace is an unconstrained workload request.  It may
    # exceed a synthetic rack-headroom case.  The nominal rack active-fraction
    # is treated as an operating policy, while installed GPU capacity is the
    # hard planning limit.  Non-shiftable fixed work may override the nominal
    # policy up to installed capacity; any remainder is reported as fixed-load
    # capacity shortfall/SLA slack rather than creating an inverted envelope.
    env["fixed_serviceable_active_gpus"] = np.minimum(
        env.fixed_avg_active_gpus_F30.to_numpy(float),
        env.installed_max_active_gpus.to_numpy(float),
    )
    env["fixed_active_capacity_shortfall_gpus"] = (
        env.fixed_avg_active_gpus_F30 - env.fixed_serviceable_active_gpus
    ).clip(lower=0)
    env["fixed_policy_override_active_gpus"] = (
        env.fixed_serviceable_active_gpus - env.nominal_deliverable_max_active_gpus
    ).clip(lower=0)
    env["effective_dispatch_max_active_gpus"] = np.maximum(
        env.nominal_deliverable_max_active_gpus.to_numpy(float),
        env.fixed_serviceable_active_gpus.to_numpy(float),
    )
    env["effective_dispatch_max_active_gpus"] = np.minimum(
        env.effective_dispatch_max_active_gpus.to_numpy(float),
        env.installed_max_active_gpus.to_numpy(float),
    )
    # Backward-compatible name now denotes the effective dispatch upper bound.
    env["deliverable_max_active_gpus"] = env.effective_dispatch_max_active_gpus

    env["nominal_serviceable_flexible_active_gpus"] = (
        env.effective_dispatch_max_active_gpus - env.fixed_serviceable_active_gpus
    ).clip(lower=0)
    env["minimum_required_flexible_deferral_active_gpus"] = (
        env.flexible_avg_active_gpus_F30 - env.nominal_serviceable_flexible_active_gpus
    ).clip(lower=0)

    env["training_incremental_fixed_kw"] = env.fixed_serviceable_active_gpus * inc
    env["training_incremental_unconstrained_requested_kw"] = env.total_avg_active_gpus * inc
    env["it_power_unconstrained_requested_kw"] = (
        env.training_idle_kw
        + env.training_incremental_unconstrained_requested_kw
        + env.inference_it_kw
        + env.other_static_kw
    )
    env["facility_power_unconstrained_requested_kw"] = pue * env.it_power_unconstrained_requested_kw

    env["it_power_min_deliverable_kw"] = (
        env.training_idle_kw
        + env.training_incremental_fixed_kw
        + env.inference_it_kw
        + env.other_static_kw
    )
    env["it_power_max_deliverable_kw"] = (
        env.training_idle_kw
        + env.effective_dispatch_max_active_gpus * inc
        + env.inference_it_kw
        + env.other_static_kw
    )
    env["facility_power_min_deliverable_kw"] = pue * env.it_power_min_deliverable_kw
    env["facility_power_max_deliverable_kw"] = pue * env.it_power_max_deliverable_kw

    env["nominal_reference_served_active_gpus"] = np.minimum(
        env.total_avg_active_gpus.to_numpy(float),
        env.effective_dispatch_max_active_gpus.to_numpy(float),
    )
    env["nominal_reference_served_active_gpus"] = np.maximum(
        env.nominal_reference_served_active_gpus.to_numpy(float),
        env.fixed_serviceable_active_gpus.to_numpy(float),
    )
    env["training_incremental_nominal_reference_kw"] = env.nominal_reference_served_active_gpus * inc
    env["it_power_nominal_reference_kw"] = (
        env.training_idle_kw
        + env.training_incremental_nominal_reference_kw
        + env.inference_it_kw
        + env.other_static_kw
    )
    env["facility_power_nominal_reference_kw"] = pue * env.it_power_nominal_reference_kw

    env["deliverable_power_span_kw"] = (
        env.it_power_max_deliverable_kw - env.it_power_min_deliverable_kw
    ).clip(lower=0)
    env["available_downward_flex_kw"] = (
        env.it_power_nominal_reference_kw - env.it_power_min_deliverable_kw
    ).clip(lower=0)
    env["available_upward_flex_kw"] = (
        env.it_power_max_deliverable_kw - env.it_power_nominal_reference_kw
    ).clip(lower=0)

    # Backward-compatible aliases. New optimization code should use the
    # explicitly named request/reference columns above.
    env["training_incremental_realized_kw"] = env.training_incremental_unconstrained_requested_kw
    env["it_power_realized_kw"] = env.it_power_unconstrained_requested_kw
    env["facility_power_realized_kw"] = env.facility_power_unconstrained_requested_kw

    env["observed_active_exceeds_deliverable"] = (
        env.total_avg_active_gpus > env.effective_dispatch_max_active_gpus + 1e-9
    )
    env["fixed_active_exceeds_installed"] = env.fixed_active_capacity_shortfall_gpus > 1e-9
    env["scenario_id"] = mainid

    interval_hours = float(cfg["analysis"].get("interval_minutes", 5)) / 60.0
    audit = {
        "main_scenario_id": mainid,
        "capacity_calibration_uses_analysis_year": False,
        "capacity_calibration_end": str(cutoff),
        "scenario_count": len(summary),
        "main_installed_gpu_capacity": int(mainsite.installed_gpu_capacity.sum()),
        "main_deliverable_gpu_capacity": float(mainsite.deliverable_active_gpu_capacity.sum()),
        "main_deliverable_to_installed_ratio": float(
            mainsite.deliverable_active_gpu_capacity.sum() / mainsite.installed_gpu_capacity.sum()
        ),
        "main_analysis_year_exceedance_rate": float(env.observed_active_exceeds_deliverable.mean()),
        "main_fixed_capacity_shortfall_rate": float(env.fixed_active_exceeds_installed.mean()),
        "main_fixed_policy_override_rate": float((env.fixed_policy_override_active_gpus > 1e-9).mean()),
        "minimum_required_flexible_deferral_gpuh": float(
            env.minimum_required_flexible_deferral_active_gpus.sum() * interval_hours
        ),
        "maximum_fixed_capacity_shortfall_gpus": float(env.fixed_active_capacity_shortfall_gpus.max()),
        "idle_it_kw_per_gpu": idle,
        "incremental_it_kw_per_gpu": inc,
        "unconstrained_requested_trace_semantics": (
            "Observed Kestrel workload request; may exceed synthetic rack-headroom cases and is not a dispatch."
        ),
        "nominal_reference_semantics": (
            "Capacity-clipped numerical warm start inside the effective dispatch envelope; not an observed trace."
        ),
    }
    return CapacityResult(allsite,allrack,summary,mainsite,mainrack,env,audit)
