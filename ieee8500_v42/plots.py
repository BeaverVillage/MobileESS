"""Scientific figures from original source and completed, unqualified AC audits.

No synthetic operational data, interpolation of missing runs, performance-based
selection, or model/control mutation. Re-run once optional AC inputs are ready.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import TwoSlopeNorm
from matplotlib.font_manager import FontProperties
import numpy as np

from .geometry import AIDC_BUSES, base_bus, read_coords, read_csv, source_records, traffic_xy

TITLE = "Unqualified preselection diagnostic"
COLORS = {"Primary":"#405d78","Secondary":"#ba935b","Triplex":"#b7c3c8",
          "Transformer":"#8c877a","AIDC":"#b92532","STA":"#1262ad"}
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,
                     "axes.spines.top":False,"axes.spines.right":False,
                     "svg.fonttype":"none","savefig.facecolor":"white"})


def save(fig, folder: Path, name: str) -> list[str]:
    paths=[]
    for ext in ("png","svg"):
        path=folder/f"{name}.{ext}"
        fig.savefig(path,dpi=180,bbox_inches="tight")
        paths.append(str(path))
    plt.close(fig)
    return paths


def attrs(record: str) -> dict[str,str]:
    return {k.lower():v for k,v in re.findall(
        r"([\w%]+)\s*=\s*(\[[^\]]*\]|\([^)]*\)|[^\s]+)",record)}


def source_edges(feeder: Path) -> tuple[list[dict],dict]:
    """Read every original line and active transformer/reactor source edge."""
    coords=read_coords(feeder/"Buscoords.dss")
    edges=[]
    for filename in ("Lines.dss","Triplex_Lines.DSS","Transformers.dss",
                     "LoadXfmrCodes.dss","Regulators.dss"):
        for record in source_records(feeder/filename):
            head=record.split()[:2]
            if len(head)<2 or head[0].lower()!="new":continue
            kind=head[1].split(".")[0].lower()
            if kind not in ("line","transformer","reactor"):continue
            properties=attrs(record)
            if "buses" in properties:
                buses=[base_bus(s) for s in re.split(r"[\s,]+",properties["buses"].strip("[]()")) if s]
            else:
                buses=[base_bus(properties[k]) for k in ("bus1","bus2") if k in properties]
            for bus in buses[1:]:
                a,b=buses[0],bus
                group=("Triplex" if filename=="Triplex_Lines.DSS" else
                       "Primary" if kind=="line" else "Transformer")
                edges.append({"element":head[1],"kind":kind,"a":a,"b":b,"group":group,
                              "drawable":a in coords and b in coords})
    return edges,coords


def source_projection(coords: dict) -> tuple[dict,str]:
    # Translation and the same positive scale on both axes preserve orientation.
    xmin=math.floor(min(p[0] for p in coords.values())/1000)*1000
    ymin=math.floor(min(p[1] for p in coords.values())/1000)*1000
    transformed={b:((p[0]-xmin)/1000,(p[1]-ymin)/1000) for b,p in coords.items()}
    return transformed,f"Source axis origins X={xmin:g}, Y={ymin:g}; displayed units=1,000 native units (CRS unverified)."


def draw_network(ax, edges: list[dict], coords: dict, alpha: float=.8, legend: bool=True):
    counts=defaultdict(int)
    for group in ("Primary","Triplex","Transformer"):
        rows=[e for e in edges if e["group"]==group and e["drawable"]]
        segments=[[coords[e["a"]],coords[e["b"]]] for e in rows]
        if segments:
            description="Transformer/reactor terminal links" if group=="Transformer" else f"{group} source edges"
            collection=LineCollection(segments,colors=COLORS[group],
                linewidths=.65 if group=="Primary" else .45,alpha=alpha,
                label=f"{description} ({len(rows):,})")
            ax.add_collection(collection)
        counts[group]=len(rows)
    ax.autoscale();ax.set_aspect("equal");ax.grid(alpha=.12)
    ax.set_xlabel("Original X offset / 1,000 native units")
    ax.set_ylabel("Original Y offset / 1,000 native units")
    if legend:ax.legend(fontsize=9,loc="upper left")
    return dict(counts)


def original_feeder(root: Path, folder: Path) -> dict:
    feeder=root/"ieee8500_v42/data/feeder"
    edges,source=source_edges(feeder);xy,note=source_projection(source)
    fig,ax=plt.subplots(figsize=(11,10))
    counts=draw_network(ax,edges,xy)
    ax.set_title(f"{TITLE}\nOriginal IEEE8500 source topology",fontsize=16,pad=16)
    sub=xy.get("_hvmv_sub_lsb")
    if sub:
        ax.scatter(*sub,c="#121820",s=130,marker="*",zorder=5)
        ax.annotate("Feeder substation boundary",sub,xytext=(-120,15),textcoords="offset points",
                    arrowprops={"arrowstyle":"-","color":"#333"},fontsize=10)
    missing=[e["element"] for e in edges if not e["drawable"]]
    fig.text(.5,.015,note+"\nAll declared source edges are retained; X/SX points are schematic placements, not customer surveys."
             +f" Coordinate-missing edges: {len(missing)}.",ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.065,1,.97))
    return {"status":"RENDERED","paths":save(fig,folder,"ORIGINAL_FEEDER_TOPOLOGY"),
            "source_edges":len(edges),"drawable_by_group":counts,"coordinate_missing_edges":missing,
            "axis_direction":"original_no_reflection_no_rotation"}


def label_sites(ax, anchors: list[dict], locations: dict):
    """Greedy annotation placement shared across AIDC and STA identities."""
    ax.figure.canvas.draw()
    renderer=ax.figure.canvas.get_renderer();points_to_pixels=ax.figure.dpi/72
    marker_points=[ax.transData.transform(p) for p in locations.values()]
    boxes=[];font=FontProperties(size=9)
    for anchor in anchors:
        site=anchor["location_id"];role=anchor["role"];point=locations[site]
        short=("A" if role=="AIDC" else "S")+site[-2:]
        x,y=ax.transData.transform(point)
        width,height,descent=renderer.get_text_width_height_descent(short,font,False)
        choices=[(5,5),(-24,-14),(5,-14),(-24,5),(5,22),(-24,-30),(5,-30),(-24,22),
                 (5,38),(-24,38),(5,-46),(-24,-46),(25,5),(-44,5),(25,-14),(-44,-14)]
        def bounds(q):
            dx,dy=q;px=x+dx*points_to_pixels;py=y+dy*points_to_pixels
            return (px-2,py-descent-2,px+width+2,py+height+2)
        def score(q):
            box=bounds(q)
            label_overlap=sum(max(0,min(box[2],r[2])-max(box[0],r[0]))*
                       max(0,min(box[3],r[3])-max(box[1],r[1])) for r in boxes)
            marker_overlap=sum(max(0,min(box[2],px+5)-max(box[0],px-5))*
                               max(0,min(box[3],py+5)-max(box[1],py-5)) for px,py in marker_points)
            return label_overlap+marker_overlap
        dx,dy=min(choices,key=score);boxes.append(bounds((dx,dy)))
        ax.annotate(short,point,xytext=(dx,dy),textcoords="offset points",color=COLORS[role],fontsize=9,
                    arrowprops={"arrowstyle":"-","lw":.5,"color":COLORS[role]},zorder=5)


def service_map(root: Path, folder: Path) -> dict:
    feeder=root/"ieee8500_v42/data/feeder";data=root/"ieee8500_v42/data/geometry"
    anchors=json.loads((data/"STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    registry=read_csv(data/"ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv")
    edges,source=source_edges(feeder);xy,note=source_projection(source)
    traffic={a["location_id"]:traffic_xy(a) for a in anchors}
    electrical={r["location_id"]:xy[r["ieee8500_bus"].lower()] for r in registry}
    fig,axs=plt.subplots(1,2,figsize=(15,8))
    draw_network(axs[1],edges,xy,alpha=.4,legend=False)
    for panel,locations in enumerate((traffic,electrical)):
        ax=axs[panel]
        for role,marker in (("AIDC","o"),("STA","s")):
            points=[locations[a["location_id"]] for a in anchors if a["role"]==role]
            ax.scatter([p[0] for p in points],[p[1] for p in points],s=45,marker=marker,c=COLORS[role],
                       label="Fixed v3 AIDC (A01-A12)" if role=="AIDC" else
                       "STA traffic IDs / retained MV hosts (S01-S12)",zorder=4)
        ax.margins(.13);ax.set_aspect("equal");ax.grid(alpha=.12)
        ax.legend(loc="lower left",fontsize=8)
        ax.set_title("Traffic east / north anchors" if panel==0 else "Original feeder axes: retained MV hosts",fontsize=12)
        if panel==0:
            ax.set_xlabel("East (km)");ax.set_ylabel("North (km)")
        label_sites(ax,anchors,locations)
    fig.suptitle(f"{TITLE} — FINAL_NONE\n12 fixed AIDC + 12 original STA service identities",fontsize=16)
    fig.text(.5,.025,"No STA was reselected to LV. Fixed-anchor directions conflict under the preregistered affine / similarity policy.\n"
             +note+" Source panel retains original axis directions and uses independent units.",ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.08,1,.91))
    return {"status":"RENDERED","paths":save(fig,folder,"SERVICE_LOCATION_MAP_FINAL_NONE"),
            "service_locations":24,"final_lv_selected":0,"original_axes_preserved":True}


def load_ac(root: Path):
    folder=root/"docs/ieee8500_v42_single_case/diagnostics/capacity_1p0"
    npz=folder/"AC_96.npz";axes=folder/"AC_AXES.json"
    if not npz.exists() or not axes.exists():
        return None,{"status":"NOT_READY","required":[str(npz),str(axes)]}
    archive=np.load(npz,allow_pickle=False)
    needed=("line_amps","line_rho","node_voltage_pu","regulator_taps")
    if any(k not in archive for k in needed):
        return None,{"status":"NOT_READY","missing_arrays":[k for k in needed if k not in archive]}
    arrays={key:archive[key] for key in needed};archive.close()
    metadata=json.loads(axes.read_text())
    for key,array in arrays.items():
        if array.ndim!=2 or array.shape[0]!=96:
            raise ValueError(f"{key} must contain all 96 solved slots; got {array.shape}")
        if not np.all(np.isfinite(array)):
            raise ValueError(f"Nonfinite solved AC array {key}; no synthetic fill allowed")
    if arrays["line_rho"].shape[1]!=len(metadata["lines"]):raise ValueError("Line axes mismatch")
    if arrays["node_voltage_pu"].shape[1]!=len(metadata["nodes"]):raise ValueError("Node axes mismatch")
    if arrays["regulator_taps"].shape[1]!=len(metadata["regcontrols"]):raise ValueError("RegControl axes mismatch")
    mask=np.array(metadata.get("objective_mask",[r.get("objective_included",False) for r in metadata["lines"]]),dtype=bool)
    if len(mask)!=len(metadata["lines"]) or not mask.any():raise ValueError("Original objective mask absent")
    return (arrays,metadata,mask),None


def daily_ac(root: Path, folder: Path) -> dict:
    data,error=load_ac(root)
    if error:return error
    arrays,metadata,mask=data
    prereg=json.loads((root/"docs/ieee8500_v42_single_case/PREREGISTRATION.json").read_text())
    vmin,vmax=float(prereg["Vmin_pu"]),float(prereg["Vmax_pu"])
    hours=np.arange(96)/4
    fig,axs=plt.subplots(3,1,figsize=(14,11),sharex=True)
    rho=arrays["line_rho"]
    system=np.max(rho[:,mask],axis=1)
    axs[0].plot(hours,system,lw=2,color="#232b36",label="System max (original V42 objective mask)")
    for group in ("Primary","Secondary","Triplex"):
        groupmask=mask & np.array([r["group"]==group for r in metadata["lines"]])
        if groupmask.any():
            axs[0].plot(hours,np.max(rho[:,groupmask],axis=1),lw=1.5,
                        color=COLORS[group] if group!="Triplex" else "#b87839",label=f"{group} max")
    axs[0].axhline(1,color="#b92532",ls="--",lw=1,label="Original line limit 1.0 pu")
    axs[0].axhspan(.8,.85,color="#e6ecef",alpha=.9,label="Desired target .80-.85 (not a hard constraint)")
    axs[0].set_ylabel("Maximum line loading (pu)");axs[0].legend(fontsize=8,ncol=2,loc="upper left")
    voltage=arrays["node_voltage_pu"]
    axs[1].plot(hours,np.min(voltage,axis=1),color="#1262ad",lw=1.7,label="Minimum original node voltage")
    axs[1].plot(hours,np.max(voltage,axis=1),color="#8e477b",lw=1.7,label="Maximum original node voltage")
    axs[1].axhline(vmin,color="#b92532",ls="--",label=f"Hard limits {vmin:g}-{vmax:g} pu")
    axs[1].axhline(vmax,color="#b92532",ls="--")
    axs[1].set_ylabel("Original node voltage (pu)");axs[1].legend(fontsize=8,ncol=2,loc="best")
    for index,name in enumerate(metadata["regcontrols"]):
        label=name["name"] if isinstance(name,dict) else str(name)
        axs[2].step(hours,arrays["regulator_taps"][:,index],where="post",lw=1.1,label=label)
    axs[2].set_ylabel("Independent RegControl tap number")
    axs[2].legend(fontsize=7,ncol=4,loc="best")
    axs[2].set_xlabel("Hour of day — 2025-05-01 (96 × 15 min slots)")
    for ax in axs:ax.grid(alpha=.15);ax.set_xlim(0,24);ax.set_xticks(np.arange(0,25,3))
    fig.suptitle(f"{TITLE}\nB0 AC: original background, fixed workload, retained MV service hosts",fontsize=16)
    fig.text(.5,.025,"Original autonomous RegControls / CapControls. Every original line rating and hard voltage limit is retained.\n"
             "These results do not qualify a final scenario or demonstrate B1 / B2 / B3 performance.",ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.065,1,.92))
    return {"status":"RENDERED","paths":save(fig,folder,"B0_DAILY_LINE_VOLTAGE_TAPS"),
            "slots":96,"rho_max":float(np.max(system)),"voltage_min":float(np.min(voltage)),
            "voltage_max":float(np.max(voltage)),"hard_voltage_limits":[vmin,vmax]}


def line_distribution(root: Path, folder: Path) -> dict:
    data,error=load_ac(root)
    if error:return error
    arrays,metadata,mask=data
    daily={};groups={}
    for column,row in enumerate(metadata["lines"]):
        name=row["element"]
        daily.setdefault(name,0.);groups[name]=row["group"]
        if not mask[column]:continue
        peak=float(np.max(arrays["line_rho"][:,column]))
        daily[name]=max(daily.get(name,0.),peak);groups[name]=row["group"]
    ranking=sorted(daily,key=lambda n:(-daily[n],n))[:20]
    fig,axs=plt.subplots(1,2,figsize=(16,9),gridspec_kw={"width_ratios":[1.25,1]})
    axs[0].barh(np.arange(len(ranking)),[daily[n] for n in ranking],
                color=["#b87839" if groups[n]=="Triplex" else COLORS.get(groups[n],"#405d78") for n in ranking])
    axs[0].set_yticks(np.arange(len(ranking)),[n.removeprefix("Line.") for n in ranking],fontsize=9)
    axs[0].invert_yaxis();axs[0].set_xlabel("Daily peak over objective conductor rows (pu)")
    axs[0].set_title("Top 20 original line identities");axs[0].grid(axis="x",alpha=.15)
    ymax=max(daily.values());bins=np.linspace(0,max(1,ymax)*1.02,45)
    for group in ("Primary","Secondary","Triplex"):
        values=[daily[n] for n in daily if groups[n]==group]
        if values:
            axs[1].hist(values,bins=bins,histtype="step",lw=2,
                        color="#b87839" if group=="Triplex" else COLORS[group],label=f"{group} ({len(values):,})")
    axs[1].axvline(1,color="#b92532",ls="--",label="Original 1.0 pu limit")
    axs[1].set_xlabel("Daily peak line loading (pu)");axs[1].set_ylabel("Original line count")
    axs[1].set_title("Distribution across every original line");axs[1].legend(fontsize=9);axs[1].grid(alpha=.12)
    fig.suptitle(f"{TITLE}\nB0 whole-system bottlenecks and line loading distribution",fontsize=16)
    disabled=len({r["element"] for r in metadata["lines"] if not r["enabled"]})
    fig.text(.5,.025,f"Each original line is counted once; {disabled} original disabled lines retain zero loading. Conductor peaks use the unchanged objective mask.\n"
             "Other terminal/conductor audits remain in the CSV outputs. A local line reduction is distinct from system rho-max improvement.",
             ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.07,1,.92))
    return {"status":"RENDERED","paths":save(fig,folder,"B0_LINE_LOADING_DISTRIBUTION"),
            "original_line_count":len(daily),"disabled_original_line_count":disabled,"top_line":ranking[0]}


def sensitivity_heatmap(root: Path, folder: Path) -> dict:
    path=root/"docs/ieee8500_v42_single_case/SENSITIVITY_PCC_SUMMARY.csv"
    if not path.exists():return {"status":"NOT_READY","required":[str(path)]}
    probes=sorted(AIDC_BUSES)+[f"STA{i:02d}" for i in range(1,13)]
    with path.open(encoding="utf-8-sig",newline="") as stream:rows=list(csv.DictReader(stream))
    metrics=("rho_derivative_pu_per_unit","critical_line_amps_derivative")
    tables={(component,metric):np.full((24,96),np.nan) for component in ("P","Q") for metric in metrics}
    for row in rows:
        match=re.fullmatch(r"(?:MV_)?(AIDC\d{2}|STA\d{2})",row.get("probe_id",""))
        if not match or match[1] not in probes or row.get("component") not in ("P","Q"):continue
        slot=int(row["slot"])
        if not 0<=slot<96:raise ValueError("Sensitivity slot outside 96-slot day")
        index=probes.index(match[1]);component=row["component"]
        for metric in metrics:
            tables[(component,metric)][index,slot]=float(row[metric])
    missing={f"{c}:{m}":int(np.isnan(t).sum()) for (c,m),t in tables.items()}
    if any(missing.values()):return {"status":"NOT_READY","missing_cell_counts":missing,
                                   "expected":"24 original MV hosts × 96 slots × P/Q; no synthetic fill"}
    fig,axs=plt.subplots(2,2,figsize=(17,12),sharex=True,sharey=True)
    for col,metric in enumerate(metrics):
        multiplier=100 if col==0 else 1
        maxabs=max(float(np.max(np.abs(tables[(c,metric)])))*multiplier for c in ("P","Q"))
        maxabs=max(maxabs,1e-12)
        for row,component in enumerate(("P","Q")):
            ax=axs[row,col]
            values=tables[(component,metric)]*multiplier
            picture=ax.imshow(values,aspect="auto",interpolation="nearest",cmap="RdBu_r",
                              norm=TwoSlopeNorm(vmin=-maxabs,vcenter=0,vmax=maxabs),extent=[0,24,23.5,-.5])
            ax.set_yticks(np.arange(24),[p if p.startswith("AIDC") else p+" (MV)" for p in probes],fontsize=8)
            ax.axhline(11.5,color="#333",lw=.7)
            unit="kW" if component=="P" else "kvar"
            ax.set_title(f"{component} injection: "+("system rho-max derivative" if col==0 else "base critical-line current derivative"),fontsize=11)
            label=f"percentage point / {unit}" if col==0 else f"A / {unit}"
            bar=fig.colorbar(picture,ax=ax,pad=.015,fraction=.028);bar.set_label(label,fontsize=9)
            bar.ax.tick_params(labelsize=8)
            ax.set_xticks(np.arange(0,25,4));ax.set_xlabel("Hour of day — 2025-05-01")
    fig.suptitle(f"{TITLE}\nExact AC central differences at 24 retained MV PCC probes; settled base taps fixed",fontsize=16)
    fig.text(.5,.02,"Positive perturbation means injection. Red: increasing loading / current; blue: decreasing. P and Q units remain distinct.\n"
             "Engineering probe sensitivity does not establish a real port, LV support, a flexibility schedule, or B2 / B3 performance.",ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.065,1,.92))
    return {"status":"RENDERED","paths":save(fig,folder,"PCC_PQ_SENSITIVITY_HEATMAP"),
            "probes":probes,"slots":96,"signed_positive":"injection","taps":"fixed settled base"}


def render_all(root: Path) -> dict:
    root=root.resolve();folder=root/"docs/ieee8500_v42_single_case/figures"
    folder.mkdir(parents=True,exist_ok=True)
    answer={}
    for name,renderer in (("original_feeder",original_feeder),("service_map",service_map),
                          ("daily_ac",daily_ac),("line_distribution",line_distribution),
                          ("sensitivity_heatmap",sensitivity_heatmap)):
        answer[name]=renderer(root,folder)
    (folder/"PLOT_STATUS.json").write_text(json.dumps(answer,indent=2)+"\n",encoding="utf-8")
    return answer


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,default=Path("."))
    result=render_all(parser.parse_args().root)
    print(json.dumps({key:value["status"] for key,value in result.items()},indent=2))
