"""Exact local baseline supplement and compact CSV views for LV v3.

Four additional independently settled reference snapshots reproduce the
preregistered baseline; no candidate selection or new perturbation is performed.
"""
from __future__ import annotations

import numpy as np
from pathlib import Path
from . import lv_sensitivity as lv
from .ac import IEEE8500AC, _complex
from .capacity import FIXED_AIDC
from .common import read, write, table, receipt, sha
from .geometry import read_csv


def run():
    folder=lv.FOLDER;policy=read(folder/'PREREGISTRATION.json')
    candidates=sorted(read_csv(lv.REPORT/'LV_STA_CANDIDATES.csv'),key=lambda r:r['candidate_bus'])
    if [r['candidate_bus'] for r in candidates]!=policy['candidate_buses']:
        raise ValueError('BASELINE_SUPPLEMENT_CANDIDATE_IDENTITY_DRIFT')
    if sha(lv.BASE_POWER)!=policy['inputs']['unchanged_V42_REFERENCE_power']['sha256']:
        raise ValueError('BASELINE_SUPPLEMENT_POWER_IDENTITY_DRIFT')
    prereg=dict(schema='LV_V3_BASELINE_READBACK_SUPPLEMENT',slots=policy['slots'],
        additional_base_AC_solves=4,new_candidate_perturbations=0,
        purpose='retain exact local base axes, nameplate coil currents, actual line-to-line voltage and compact CSV views',
        baseline=receipt(folder/'PREREGISTRATION.json'),auditor=receipt(Path(__file__)),
        score_source=receipt(folder/'CANDIDATE_SCORES.csv'),physical_status='SIMULATION_DESIGN_NOT_FIELD',
        production_certificate=False,Native_calls=0,full_model_builds=0)
    dest=folder/'BASELINE_READBACK_PREREGISTRATION.json'
    if dest.exists() and read(dest)!=prereg:raise ValueError('BASELINE_READBACK_PREREGISTRATION_DRIFT')
    write(dest,prereg)
    engine=IEEE8500AC(output_dir=folder/'baseline_readback_dss')
    if engine.source_hashes!=policy['source_sha256']:raise ValueError('BASELINE_SOURCE_SHA_DRIFT')
    for site,bus in FIXED_AIDC.items():engine.add_pcc(site,bus,'MV_3PH')
    for pid,row in zip(policy['probe_ids'],candidates):engine.add_pcc(pid,row['candidate_bus'],'LV_SPLIT_240')
    locals_=[lv.axes_for_candidate(engine,row) for row in candidates]
    n=len(candidates);maxpath=max(len(x['path']) for x in locals_);maxct=max(len(x['tx_current']) for x in locals_)
    hot=np.full((4,n,maxpath,2,2),np.nan);neutral=np.full((4,n,maxpath,2),np.nan)
    v=np.zeros((4,n,2));vll=np.zeros((4,n));current=np.full((4,n,maxct),np.nan)
    currentrho=np.full_like(current,np.nan);kva=np.zeros((4,n,3),complex);kvarho=np.zeros((4,n,3))
    nameplatecoil=np.zeros((n,3));nameplatekva=np.zeros((n,3));triplexratings=np.full((n,maxpath),np.nan)
    txlookup={r['element'].lower():r for r in engine.inventory['transformers']}
    linelookup={r['element'].lower():r for r in engine.inventory['lines']}
    for k,(row,local) in enumerate(zip(candidates,locals_)):
        tx=txlookup[row['upstream_transformer']]
        nameplatecoil[k]=[w['nameplate_coil_amps'] for w in tx['windings']]
        nameplatekva[k]=[w['kva_nameplate'] for w in tx['windings']]
        triplexratings[k,:len(local['path'])]=[linelookup[line]['normal_amps'] for line in local['path']]
    baseline=read(folder/'BASELINE_SUMMARIES.json');errors=[]
    with np.load(lv.BASE_POWER,allow_pickle=False) as z:p,q=z['PCC_P_kw'],z['PCC_Q_kvar']
    for t,slot in enumerate(policy['slots']):
        demand={site:(float(p[slot,k]),float(q[slot,k])) for k,site in enumerate(sorted(FIXED_AIDC))}
        snap=engine.solve(lv.BG,demand,'auto',reset_controls=True)
        arrays=engine.measurement_arrays()
        if not arrays['converged'] or not arrays['control_actions_done'] or arrays['control_queue_size']:
            raise ValueError('BASELINE_SUPPLEMENT_NOT_SETTLED')
        if snap['control_state']!=baseline[t]['control_state']:raise ValueError('BASELINE_REPRODUCTION_CONTROL_DRIFT')
        numeric=('rho_max','rho_max_all_terminals','vmin_pu','vmax_pu','transformer_current_rho_max','transformer_nameplate_kva_rho_max')
        error=max(abs(snap['summary'][key]-baseline[t]['summary'][key]) for key in numeric)
        if error>1e-10:raise ValueError('BASELINE_REPRODUCTION_NUMERIC_DRIFT')
        errors.append(dict(slot=slot,maximum_summary_absolute_error=error,controls_equal=True))
        for k,(pid,local) in enumerate(zip(policy['probe_ids'],locals_)):
            hot[t,k,:len(local['path'])]=arrays['line_amps'][local['hot']]
            neutral[t,k,:len(local['path'])]=arrays['triplex_implied_neutral_amps'][local['neutral']]
            v[t,k]=arrays['node_voltage_pu'][local['nodes']]
            current[t,k,:len(local['tx_current'])]=arrays['transformer_amps'][local['tx_current']]
            currentrho[t,k,:len(local['tx_current'])]=arrays['transformer_current_rho'][local['tx_current']]
            kva[t,k]=arrays['transformer_winding_complex_kva'][local['tx_kva']]
            kvarho[t,k]=arrays['transformer_winding_nameplate_kva_rho'][local['tx_kva']]
            engine.d.Circuit.SetActiveElement(engine.pccs[pid]['element'])
            volts=_complex(engine.d.CktElement.Voltages())
            vll[t,k]=abs(volts[0]-volts[1])
        print('LVv3 baseline exact local readback',slot,flush=True)
    np.savez_compressed(folder/'BASE_LOCAL.npz',candidate_bus=np.array(policy['candidate_buses']),
        slot=np.array(policy['slots']),PCC_node_voltage_pu=v,PCC_line_to_line_voltage_V=vll,
        Triplex_hot_A=hot,Triplex_implied_neutral_A=neutral,Triplex_normal_amps=triplexratings,
        CT_current_A=current,CT_current_rho=currentrho,CT_winding_complex_kva=kva,
        CT_winding_nameplate_kva_rho=kvarho,CT_nameplate_coil_amps=nameplatecoil,CT_nameplate_kva=nameplatekva)
    # Keep every response in NPZ; compact textual views cover all line maxima and
    # the 20 potential-ranked candidates. Counts and hashes preserve provenance.
    best={r['candidate_bus'] for r in read_csv(folder/'TOP20_CANDIDATE_SCORES.csv')}
    aggregates=[];compact=[];replaced={}
    for slot in policy['slots']:
        file=folder/f'TOP20_RESPONSE_SLOT_{slot:02d}.csv'
        original=receipt(file);rows=read_csv(file)
        selected=[r for r in rows if r['bus'] in best]
        groups={}
        for row in rows:groups.setdefault((row['component'],row['line']),[]).append(row)
        for (component,line),group in sorted(groups.items()):
            derivatives=np.array([float(row['dRho_pu_per_unit']) for row in group])
            imin=int(derivatives.argmin());imax=int(derivatives.argmax())
            aggregates.append(dict(slot=slot,component=component,line=line,customers=len(group),
                minimum_dRho=float(derivatives[imin]),minimum_dRho_bus=group[imin]['bus'],
                maximum_dRho=float(derivatives[imax]),maximum_dRho_bus=group[imax]['bus'],
                median_dRho=float(np.median(derivatives)),
                source_path_intersecting_customers=sum(r['source_path_contains_line']=='True' for r in group)))
        table(file,selected);compact.extend(selected)
        replaced[file.name]=dict(original_full_csv=original,original_rows=len(rows),
            compact_csv=receipt(file),compact_rows=len(selected),
            full_derivatives_retained_in=receipt(folder/f'LV_SLOT_{slot:02d}.npz'))
    table(folder/'TOP20_LINE_AGGREGATE.csv',aggregates)
    table(folder/'TOP20_CANDIDATE_RESPONSES.csv',compact)
    write(folder/'BASELINE_READBACK_RECEIPT.json',dict(status='PASS_EXACT_BASELINE_LOCAL_REPRODUCTION',
        candidates=n,additional_base_AC_solves=4,new_candidate_perturbations=0,
        summary_reproduction=errors,source_unchanged=engine.verify_source_unchanged(),
        compact_csv_provenance=replaced,physical_status='SIMULATION_DESIGN_NOT_FIELD',production_certificate=False,
        artifacts={name:receipt(folder/name) for name in ('BASE_LOCAL.npz','TOP20_LINE_AGGREGATE.csv','TOP20_CANDIDATE_RESPONSES.csv')},
        Native_calls=0,full_model_builds=0))
    original_receipt=read(folder/'RECEIPT.json')
    original_receipt['compact_csv_supplement']=receipt(folder/'BASELINE_READBACK_RECEIPT.json')
    original_receipt['additional_reproduction_base_AC_solves']=4
    for name in replaced:original_receipt['artifacts'][name]=receipt(folder/name)
    write(folder/'RECEIPT.json',original_receipt)


if __name__=='__main__':run()
