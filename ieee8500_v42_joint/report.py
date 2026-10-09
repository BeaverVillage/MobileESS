"""Read-only numerical reporting/plots for completed May01 joint PCC records.

No OpenDSS/Native imports, solves, sensitivity recomputation or scenario tuning.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import shutil
from collections import Counter,defaultdict
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

from .selection import ROOT,REPORT,OLD,HIGH,PRIOR,read as _read,rows,sha,write_json

FIG=REPORT/'figures'
DAY='2025-05-01'
COLORS={'AIDC':'#1267a5','STA':'#d45422'}
matplotlib.rcParams['svg.hashsalt']='IEEE8500_V42_JOINT_MAY01'


def read(path):
    path=Path(path)
    if path.exists():return _read(path)
    packed=path.with_name(path.name+'.gz')
    if packed.exists():return json.loads(gzip.decompress(packed.read_bytes()).decode('utf-8'))
    raise FileNotFoundError(path)


def table(path,data):
    if not data:return
    fields=list(dict.fromkeys(k for row in data for k in row))
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(data)


def complete_inputs():
    config=read(REPORT/'SELECTED_RESEARCH_CONFIGURATION.json')
    mapping=Path(config['mapping']['path'])
    assert sha(mapping)==config['mapping']['sha256']
    run=read(REPORT/'RUN_RECEIPT.json');records=run['records']
    assert len(records)==4 and {(r['source'],r['controlled']) for r in records}=={(s,c) for s in ('PLANNING','ACTUAL') for c in (False,True)},'Incomplete final May01 paired record'
    for record in records:
        assert record['day']==DAY and record['comparison']['PASS']
        for mode in ('first','fresh'):
            data=record[mode];assert data['slots']==96 and data['day']==DAY
            assert data['mapping']['sha256']==config['mapping']['sha256']
            assert len(rows(REPORT/'ac'/data['tag']/'SLOTS.csv'))==96
    assert run['Native_calls']==0 and not run['Actual_retuning']
    return config,mapping,run,records


def numerical_exports(config,mapping,records):
    selected=rows(mapping);case=config['case'];rootcopy=REPORT/'JOINT_LOCATION_SELECTION.csv'
    if rootcopy.exists():assert sha(rootcopy)==sha(mapping),'Do not replace another sealed root mapping'
    else:shutil.copyfile(mapping,rootcopy)
    assert sha(rootcopy)==config['mapping']['sha256']
    for filename in ('ELECTRICAL_REGION_DISPERSION_AUDIT.csv','RELATIVE_POSITION_276PAIR_AUDIT.csv','RELATIVE_POSITION_552AXIS_AUDIT.csv'):
        src=mapping.parent/filename;dst=REPORT/filename
        if dst.exists():assert sha(src)==sha(dst)
        else:shutil.copyfile(src,dst)
    b0=[];mess=[];summaries=[];physical=[];portrows=[];controls=[]
    for record in records:
        for mode in ('first','fresh'):
            result=record[mode];tag=result['tag'];folder=REPORT/'ac'/tag
            metadata={'dataset':tag,'controlled':record['controlled'],'fresh_context':mode=='fresh'}
            output=mess if record['controlled'] else b0
            output.extend({**metadata,**r} for r in rows(folder/'SLOTS.csv'))
            summaries.append({**metadata,**{k:result[k] for k in ('day','source','bg','rho_max','Primary_rho_max','Triplex_rho_max','Vmin','Vmax',
                'peak_slot','binding_line','binding_group','binding_node','voltage_violation_cells','line_overload_cells',
                'CT_current_overload_cells','CT_nameplate_overload_cells','grid_hard_PASS')},
                'Fresh_comparison_PASS':record['comparison']['PASS'],'field_installation_PASS':False})
            controls.extend({**metadata,**r} for r in rows(folder/'CONTROL_STATES_96.csv'))
            checks=[('all_node_voltage_0.95_to_1.05',result['voltage_violation_cells']==0,result['voltage_violation_cells'],'violating node-slot cells'),
                ('all_original_line_both_terminal_ratings',result['line_overload_cells']==0,result['line_overload_cells'],'overload cells'),
                ('all_transformer_current_ratings',result['CT_current_overload_cells']==0,result['CT_current_max'],'maximum current/rating'),
                ('all_transformer_nameplate_ratings',result['CT_nameplate_overload_cells']==0,result['CT_nameplate_max'],'maximum winding kVA/nameplate'),
                ('grid_hard_all96',result['grid_hard_PASS'],96,'solved slots'),
                ('original_DSS_and_ratings',result['source_parameter_audit']['PASS'],result['original_DSS_changed'],'original files changed'),
                ('fresh_numerical_replay',record['comparison']['PASS'],max(record['comparison']['array_errors'].values()),'maximum array difference'),
                ('power_balance',result['all96_power_balance_error']<1e-4,result['all96_power_balance_error'],'maximum P/Q balance error')]
            state=rows(folder/'CONTROL_STATES_96.csv');slots=rows(folder/'SLOTS.csv')
            checks.append(('automatic_controls_settled',all(r['controls_settled']=='True' for r in slots),96,'settled slots'))
            ports=read(folder/'PORT_96.json');assert len(ports)==1152
            for site in selected:
                if site['role']!='STA':continue
                points=[r for r in ports if r['site']==site['location_id']];mv=site['connection_mode']=='MV_3PH'
                limit=600/(math.sqrt(3)*.48) if mv else 27.;smax=600 if mv else 6.
                pmax=450 if mv else 5.;qmax=math.sqrt(600**2-450**2) if mv else 3.
                portpass=all(abs(r['P_kw'])<=pmax+1e-6 and r['S_kva']<=smax+1e-6 and r['I_max_A']<=limit+1e-6 and
                    (mv or abs(r['Q_kvar'])<=3+1e-6) for r in points)
                phaseerror=max(float(np.abs(np.asarray(r['per_conductor_PQ'])[:3]-np.asarray([r['P_kw'],r['Q_kvar']])[None,:]/3).max()) for r in points) if mv else 0.
                portrows.append({**metadata,'source':result['source'],'STA':site['location_id'],'PCC_bus':site['candidate_bus'],
                    'connection_mode':site['connection_mode'],'vehicle_Pmax_kw':450,'vehicle_Smax_kva':600,'vehicle_Emax_kwh':1800,
                    'port_Pmax_kw':pmax,'port_Smax_kva':smax,'nominal_S_circle_Qmax_at_Pmax_kvar_NOT_AC_envelope':qmax,'port_current_limit_A':limit,
                    'dedicated_transformer_kva':750 if mv else 0,'HV_kv_LL':12.47 if mv else '', 'LV_kv_LL':.48 if mv else .240,
                    'phase_count':3 if mv else 1,'split_phase_two_hot_legs':not mv,'simultaneous_vehicle_capacity':1,
                    'actual_P_abs_max_kw':max(abs(r['P_kw']) for r in points),'actual_Q_abs_max_kvar':max(abs(r['Q_kvar']) for r in points),
                    'actual_S_max_kva':max(r['S_kva'] for r in points),'actual_conductor_I_max_A':max(r['I_max_A'] for r in points),
                    'balanced_phase_PQ_error_max':phaseerror,'all96_port_rating_PASS':portpass and phaseerror<1e-5,
                    'source_readback_rows':len(points),'tested_schedule_Q_kvar':0,'full_P450_Q300_rectangle_AC_certified':False,
                    'hardware_status':'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED',
                    'actual_mobile_600kVA_product_GIS_protection_access':'UNVERIFIED'})
            checks.append(('actual_port_current_PQ_and_S',all(r['all96_port_rating_PASS'] for r in portrows if r['dataset']==tag),1152,'actual port readback rows'))
            physical.extend({**metadata,'source':result['source'],'constraint':name,'status':'PASS' if passed else 'FAIL','value':value,'unit_or_scope':unit}
                            for name,passed,value,unit in checks)
    for gate in ('physical_GIS_CRS_and_new_PCC_road_access','short_circuit_protection_anti_islanding_grounding',
                 'mobile_PCS_manufacturer_DC_interface_and_temperature_derating','AIDC_rack_PSU_cooling_transformer_as_built',
                 'nonzero_AIDC_QoS_WAN_checkpoint96_dispatch','new_MV_Native_grid_six_vehicle_API_compatibility'):
        physical.append({'dataset':'COMMON','controlled':'','fresh_context':'','source':'COMMON','constraint':gate,'status':'UNVERIFIED',
            'value':'','unit_or_scope':'Production promotion blocked; not a relaxed electrical limit'})
    endpoint=read(REPORT/'PHYSICAL_ENDPOINT_CONSTRAINT_SUMMARY.json') if (REPORT/'PHYSICAL_ENDPOINT_CONSTRAINT_SUMMARY.json').exists() else None
    physical.append({'dataset':'COMMON','controlled':'','fresh_context':'','source':'PLANNING','constraint':'full_MV_P450_Q300_rectangle',
        'status':'NOT_CERTIFIED','value':endpoint['failed_endpoints'] if endpoint else '',
        'unit_or_scope':'20 of190 endpoints overvoltage; Q0 complete96 schedule is distinct'})
    table(REPORT/'FINAL_B0_PLANNING_ACTUAL_FRESH.csv',b0)
    table(REPORT/'FINAL_MESS_PLANNING_ACTUAL_FRESH.csv',mess)
    table(REPORT/'FINAL_AC_SUMMARY.csv',summaries)
    table(REPORT/'PHYSICAL_CONSTRAINT_AUDIT.csv',physical)
    table(REPORT/'MV_PORT_RATING_AUDIT.csv',portrows)
    table(REPORT/'FINAL_REGCONTROL_CAPCONTROL_TRAJECTORIES.csv',controls)
    bg=[]
    for name,folder in [('C0_PR197_REFERENCE',HIGH/'ac/E1R_C0_BG0.850'),('C1',REPORT/'ac/C1_BG0.850_B0_PLANNING'),('C2',REPORT/'ac/C2_BG0.850_B0_PLANNING')]:
        if (folder/'RECEIPT.json').exists():bg.extend({'case':name,**r} for r in rows(folder/'SLOTS.csv'))
    table(REPORT/'BG085_B0_PLANNING_AC_96.csv',bg)
    return summaries,physical,portrows


def interface_exports(portrows):
    summaries=[];already={r['dataset'] for r in portrows}
    for result in read(REPORT/'INTERFACE_PLANNING_SCREENING.json'):
        label=result['interface'];level=result['level_kw'];tag=result['tag'];soc=rows(REPORT/f'{label}_SOC_96.csv')
        ports=read(REPORT/'ac'/tag/'PORT_96.json');limit=600/(math.sqrt(3)*.48)
        summaries.append({'interface':label,'nominal_P_limit_kw':level,'vehicle_Pmax_kw':450,'vehicle_Smax_kva':600,
            'actual_schedule_charge_kw_per_vehicle':max(float(r['Pch_AC_kw']) for r in soc),
            'actual_schedule_discharge_kw_per_vehicle':max(float(r['Pdis_AC_kw']) for r in soc),
            'actual_schedule_Q_kvar':0,'SOC_min_kwh':min(float(r['E_after_kwh']) for r in soc),
            'SOC_max_kwh':max(float(r['E_after_kwh']) for r in soc),'terminal_SOC_kwh':1140,
            'port_I_max_A':max(r['I_max_A'] for r in ports),'port_actual_PQ_current_PASS':result['port_audit']['port_actual_current_and_PQ_PASS'],
            'Planning_global_max96_rho':result['rho_max'],'Planning_Triplex_max96_rho':result['Triplex_rho_max'],
            'voltage_violation_cells':result['voltage_violation_cells'],'grid_hard_PASS':result['grid_hard_PASS'],
            'full_PQ_rectangle_certified':False,'effect_used_to_select_locations_BG_interface':False})
        if tag in already:continue
        for site in sorted({r['site'] for r in ports}):
            points=[r for r in ports if r['site']==site]
            assert len(points)==96 and all(r['port_mode']=='MV_DEDICATED_480V' for r in points)
            error=max(float(np.abs(np.asarray(r['per_conductor_PQ'])[:3]-np.array([r['P_kw'],r['Q_kvar']])[None,:]/3).max()) for r in points)
            portrows.append({'dataset':tag,'controlled':True,'fresh_context':False,'source':'PLANNING','STA':site,
                'connection_mode':'MV_3PH','vehicle_Pmax_kw':450,'vehicle_Smax_kva':600,'vehicle_Emax_kwh':1800,
                'port_Pmax_kw':level,'port_Smax_kva':600,'port_current_limit_A':limit,'dedicated_transformer_kva':750,
                'HV_kv_LL':12.47,'LV_kv_LL':.48,'phase_count':3,'split_phase_two_hot_legs':False,'simultaneous_vehicle_capacity':1,
                'actual_P_abs_max_kw':max(abs(r['P_kw']) for r in points),'actual_Q_abs_max_kvar':max(abs(r['Q_kvar']) for r in points),
                'actual_S_max_kva':max(r['S_kva'] for r in points),'actual_conductor_I_max_A':max(r['I_max_A'] for r in points),
                'balanced_phase_PQ_error_max':error,'all96_port_rating_PASS':error<1e-5 and all(abs(r['P_kw'])<=level+1e-6 and r['S_kva']<=600+1e-6 and r['I_max_A']<=limit+1e-6 for r in points),
                'source_readback_rows':96,'tested_schedule_Q_kvar':0,'full_P450_Q300_rectangle_AC_certified':False,
                'hardware_status':'ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED','actual_mobile_600kVA_product_GIS_protection_access':'UNVERIFIED'})
    table(REPORT/'MV_PORT_RATING_AUDIT.csv',portrows)
    table(REPORT/'INTERFACE_MODEL_SCHEDULE_COMPARISON.csv',summaries)
    return summaries


def line_audits(records):
    critical=[];top=[]
    fixed=rows(REPORT/'CRITICAL_CORRIDOR_BASELINE.csv')
    for source in ('PLANNING','ACTUAL'):
        before=next(r['first'] for r in records if r['source']==source and not r['controlled'])
        after=next(r['first'] for r in records if r['source']==source and r['controlled'])
        axes=read(REPORT/'ac'/before['tag']/'AC_AXES.json')['lines']
        with np.load(REPORT/'ac'/before['tag']/'AC_96.npz') as a:base=a['line_rho'].copy()
        with np.load(REPORT/'ac'/after['tag']/'AC_96.npz') as a:new=a['line_rho'].copy()
        groups=defaultdict(list)
        for i,r in enumerate(axes):
            if r['objective_included']:groups[r['element']].append(i)
        order=sorted(groups,key=lambda name:(-float(base[:,groups[name]].max()),name))
        names=list(dict.fromkeys(order[:20]+[r['line'] for r in fixed]))
        for rank,name in enumerate(order[:20],1):
            positions=groups[name];t,j=np.unravel_index(np.argmax(base[:,positions]),base[:,positions].shape);idx=positions[j]
            top.append({'source':source,'rank_B0_max96':rank,'line':name,'group':axes[idx]['group'],'phase_node':axes[idx]['node'],
                'peak_slot':int(t),'B0_max96_rho':float(base[t,idx]),'MESS_max96_rho':float(new[:,positions].max()),
                'MESS_same_B0_peak_slot_rho':float(new[t,positions].max()),'original_normal_amps':axes[idx]['normal_amps'],
                'original_rating_changed':False})
        for name in names:
            positions=groups[name];old=base[:,positions].max(axis=1);changed=new[:,positions].max(axis=1);peak=int(old.argmax())
            critical.append({'source':source,'line':name,'group':axes[positions[0]]['group'],
                'original_phase_nodes':','.join(map(str,sorted({axes[i]['node'] for i in positions}))),
                'B0_max96_rho':float(old.max()),'MESS_fixed_schedule_max96_rho':float(changed.max()),
                'difference_of96slot_maxima_rho':float(old.max()-changed.max()),'B0_peak_slot':peak,
                'relief_at_B0_line_peak_slot_rho':float(old[peak]-changed[peak]),
                'slots_line_worsened':int(np.sum(changed>old+1e-8)),
                'AIDC_applied_admissible_control_rho':0.,'Joint_record_equals_MESS':True,
                'scope':'May01 fixed feasible research schedule; not B1/B2/B3 or optimality'})
    table(REPORT/'CRITICAL_CORRIDOR_CONTROL_AUDIT.csv',critical)
    table(REPORT/'FINAL_TOP20_ORIGINAL_LINE_BOTTLENECKS.csv',top)
    return critical,top


def savefig(fig,name):
    FIG.mkdir(exist_ok=True);fig.savefig(FIG/(name+'.svg'),bbox_inches='tight',metadata={'Date':None});fig.savefig(FIG/(name+'.png'),dpi=160,bbox_inches='tight');plt.close(fig)


def topology_data():
    inv=read(OLD/'ORIGINAL_FEEDER_INVENTORY.json');pos={r['bus']:(r['x'],r['y']) for r in inv['buses'] if r['coord_defined']}
    segments=[]
    for r in inv['lines']:
        a,b=[s.split('.')[0].lower() for s in r['buses'][:2]]
        if r['group']=='Primary' and r['enabled'] and a in pos and b in pos:segments.append([pos[a],pos[b]])
    return inv,pos,segments


def label_sites(ax,sites,coordinate_fields=('source_or_proxy_x','source_or_proxy_y'),font=7):
    """Place leader labels in display space; source PCC coordinates never move."""
    ax.figure.canvas.draw();dpi=ax.figure.dpi;occupied=[]
    offsets=[(4,4),(4,-10),(-44,4),(-44,-10),(4,17),(4,-23),(-44,17),(-44,-23),
             (18,29),(18,-35),(-58,29),(-58,-35),(24,43),(24,-49),(-64,43),(-64,-49)]
    for r in sorted(sites,key=lambda r:(float(r[coordinate_fields[1]]),float(r[coordinate_fields[0]]),r['location_id'])):
        point=(float(r[coordinate_fields[0]]),float(r[coordinate_fields[1]]));pixel=ax.transData.transform(point)
        width=len(r['location_id'])*font*.62*dpi/72;height=font*1.4*dpi/72
        best=None
        for dx,dy in offsets:
            x,y=pixel+np.array([dx,dy])*dpi/72;box=(x,y-3*dpi/72,x+width,y+height)
            overlaps=sum(max(0,min(box[2],b[2])-max(box[0],b[0]))*max(0,min(box[3],b[3])-max(box[1],b[1])) for b in occupied)
            outside=max(0,ax.bbox.x0-box[0])+max(0,box[2]-ax.bbox.x1)+max(0,ax.bbox.y0-box[1])+max(0,box[3]-ax.bbox.y1)
            score=overlaps*100+outside*1000+dx*dx+dy*dy
            if best is None or score<best[0]:best=(score,dx,dy,box)
        _,dx,dy,box=best;occupied.append(box)
        ax.annotate(r['location_id'],point,xytext=(dx,dy),textcoords='offset points',fontsize=font,
            color=COLORS[r['role']],arrowprops={'arrowstyle':'-','color':COLORS[r['role']],'linewidth':.45,'alpha':.55})


def plot_topology(mapping):
    inv,pos,segments=topology_data();new=rows(mapping);old=rows(PRIOR)
    fig,axes=plt.subplots(1,2,figsize=(16,9),sharex=True,sharey=True)
    for ax,sites,title in [(axes[0],old,'C0 / PR197 retained locations'),(axes[1],new,'Selected C2 joint locations: 12 MV STA')]:
        ax.add_collection(LineCollection(segments,colors='#c2c9d0',linewidths=.6,alpha=.8))
        for role,mark in [('AIDC','o'),('STA','^')]:
            subset=[r for r in sites if r['role']==role];xy=np.array([[float(r['source_or_proxy_x']),float(r['source_or_proxy_y'])] for r in subset])
            ax.scatter(xy[:,0],xy[:,1],s=55,c=COLORS[role],marker=mark,label=role,zorder=4,edgecolors='white',linewidths=.6)
        ax.autoscale();ax.set_aspect('equal');ax.set_title(title);ax.set_xlabel('Original schematic X (unit/CRS unverified)');ax.legend(loc='lower right');ax.grid(alpha=.12)
        label_sites(ax,sites,font=6)
    axes[0].set_ylabel('Original schematic Y (unit/CRS unverified)')
    fig.suptitle('Original IEEE8500 primary topology; PCC markers use original bus/proxy coordinates',fontsize=12)
    savefig(fig,'01_OLD_NEW_TOPOLOGY_PCC_COMPARISON')
    fig,ax=plt.subplots(figsize=(13,9));ax.add_collection(LineCollection(segments,colors='#d9dfe3',linewidths=.5))
    critical_names={r['line'] for r in rows(REPORT/'CRITICAL_CORRIDOR_CONTROL_AUDIT.csv') if r['source']=='PLANNING' and r['group']=='Primary'}
    highlight=[]
    for line in inv['lines']:
        a,b=[s.split('.')[0].lower() for s in line['buses'][:2]]
        if line['element'] in critical_names and a in pos and b in pos:highlight.append([pos[a],pos[b]])
    ax.add_collection(LineCollection(highlight,colors='#8d3a9c',linewidths=1.7,zorder=2,label='Critical original Primary corridors'))
    for r in new:
        x,y=float(r['source_or_proxy_x']),float(r['source_or_proxy_y']);ax.scatter([x],[y],s=65,c=COLORS[r['role']],marker='o' if r['role']=='AIDC' else '^',zorder=4)
    ax.autoscale();ax.set_aspect('equal');ax.set_title('Selected joint PCCs on original IEEE8500 primary connections');ax.set_xlabel('Source schematic X (unknown native units)');ax.set_ylabel('Source schematic Y (unknown native units)');ax.grid(alpha=.15)
    label_sites(ax,new)
    ax.legend(loc='lower right',fontsize=8)
    savefig(fig,'02_SELECTED_24_PCC_TOPOLOGY')


def plot_geometry_regions(mapping):
    sites=rows(mapping);disp=rows(mapping.parent/'ELECTRICAL_REGION_DISPERSION_AUDIT.csv')
    fig,axes=plt.subplots(1,2,figsize=(15,7));ax=axes[0]
    for role,marker in [('AIDC','o'),('STA','^')]:
        subset=[r for r in sites if r['role']==role]
        for r in subset:
            x,y=float(r['common_frame_x_km']),float(r['common_frame_y_km']);tx,ty=float(r['traffic_x_km']),float(r['traffic_y_km'])
            ax.plot([tx,x],[ty,y],color=COLORS[role],alpha=.2,lw=.6)
            ax.scatter([tx],[ty],marker=marker,facecolor='none',edgecolor=COLORS[role],s=48)
            ax.scatter([x],[y],marker=marker,c=COLORS[role],s=36)
        ax.scatter([],[],c=COLORS[role],marker=marker,label=role+' PCC common frame')
    ax.set_aspect('equal');ax.grid(alpha=.2);ax.legend(fontsize=8);ax.set_xlabel('Common traffic frame east [km]');ax.set_ylabel('Common traffic frame north [km]');ax.set_title('135 degree proper similarity; 552 direction axes PASS\nOpen markers: traffic anchors; lines: layout residuals, not travel')
    label_sites(ax,sites,('common_frame_x_km','common_frame_y_km'),font=6)
    ax=axes[1];x=np.arange(8);A=[int(r['AIDC_count']) for r in disp];S=[int(r['STA_count']) for r in disp]
    ax.bar(x,A,color=COLORS['AIDC'],label='AIDC');ax.bar(x,S,bottom=A,color=COLORS['STA'],label='STA');ax.axhline(6,c='black',ls='--',lw=1,label='Combined cap = 6')
    ax.set_xticks(x,[r['electrical_region'] for r in disp]);ax.set_ylim(0,7);ax.set_ylabel('PCC count');ax.set_title('8 original-tree connected regions; 7 covered\n3 named major lateral labels + trunk/minor aggregate');ax.legend();ax.grid(axis='y',alpha=.2)
    savefig(fig,'03_COMMON_GEOMETRY_AND_REGION_DISTRIBUTION')
    traffic=rows(REPORT/'TRAFFIC_ETA_ACCESS_AUDIT.csv');subset=[r for r in traffic if int(r['departure_slot'])==0]
    units=sorted({r['unit'] for r in subset}) if subset and 'unit' in subset[0] else sorted({r['vehicle_id'] for r in subset})
    key='unit' if subset and 'unit' in subset[0] else 'vehicle_id'
    matrix=np.full((len(units),12),np.nan)
    for r in subset:matrix[units.index(r[key]),int(r['destination_STA'][3:])-1]=float(r['earliest_day0_ready_slot'])
    fig,ax=plt.subplots(figsize=(12,4));im=ax.imshow(matrix,aspect='auto',cmap='YlGnBu');ax.set_xticks(range(12),[f'STA{i:02d}' for i in range(1,13)]);ax.set_yticks(range(len(units)),units)
    for i,j in np.ndindex(matrix.shape):ax.text(j,i,f'{matrix[i,j]:.0f}',ha='center',va='center',fontsize=8)
    fig.colorbar(im,ax=ax,label='Earliest original day0 ready slot');ax.set_title('Original abstract road ETA + 600s connection assumption\nNew PCC physical road access and GIS remain UNVERIFIED')
    savefig(fig,'04_ORIGINAL_TRAFFIC_READY_SLOT_COVERAGE')


def plot_controls(records,critical):
    response=rows(REPORT/'C2_SCORED/SELECTED_CAPACITY_BOUNDED_LINE_RESPONSE.csv')
    sites=[f'AIDC{i:02d}' for i in range(1,13)]+[f'STA{i:02d}' for i in range(1,13)]
    targets=[r['line'] for r in rows(REPORT/'CRITICAL_CORRIDOR_BASELINE.csv')][:20];matrix=np.zeros((24,len(targets)));counts=np.zeros_like(matrix)
    for r in response:
        if r['original_line'] in targets:
            i,j=sites.index(r['location_id']),targets.index(r['original_line']);matrix[i,j]+=float(r['screening_P_relief_rho']);counts[i,j]+=1
    matrix=np.divide(matrix,counts,out=np.zeros_like(matrix),where=counts>0)
    fig,ax=plt.subplots(figsize=(16,9));scale=max(float(np.abs(matrix).max()),1e-9);im=ax.imshow(matrix*100,aspect='auto',cmap='RdBu',vmin=-100*scale,vmax=100*scale)
    ax.set_yticks(range(24),sites);ax.set_xticks(range(len(targets)),[n.replace('Line.','') for n in targets],rotation=65,ha='right',fontsize=8)
    ax.axhline(11.5,c='black',lw=1);ax.set_title('Selected-PCC response on frozen old-C0 screening corridors\nAIDC: source-mask relaxation only; STA: capacity/ETA upper response; not final policy effects');fig.colorbar(im,ax=ax,label='Mean line-rho response [percentage points]')
    savefig(fig,'05_PCC_CRITICAL_CORRIDOR_RESPONSE_HEATMAP')
    fig,axes=plt.subplots(2,3,figsize=(16,8),sharex=True)
    for row,source in enumerate(('PLANNING','ACTUAL')):
        before=next(r['first'] for r in records if r['source']==source and not r['controlled']);after=next(r['first'] for r in records if r['source']==source and r['controlled'])
        a=rows(REPORT/'ac'/before['tag']/'SLOTS.csv');b=rows(REPORT/'ac'/after['tag']/'SLOTS.csv')
        for col,key in enumerate(('rho_max','Primary_rho_max','Triplex_rho_max')):
            ax=axes[row,col];ax.plot(range(96),[float(r[key]) for r in a],c='#34495e',label='B0 / AIDC action 0');ax.plot(range(96),[float(r[key]) for r in b],c='#d45422',label='MESS / Joint with AIDC action 0');ax.set_title(source+' '+key.replace('_rho_max','').replace('rho_max','Overall'));ax.set_ylabel('Maximum original line rho [pu]');ax.grid(alpha=.2);ax.legend(fontsize=7)
            if row==1:ax.set_xlabel('May01 15-minute slot')
    fig.suptitle('96-slot complete grid AC: fixed feasible schedule, not B1/B2/B3 performance',fontsize=12)
    savefig(fig,'06_OVERALL_PRIMARY_TRIPLEX_RHO96')
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,source in zip(axes,('PLANNING','ACTUAL')):
        before=next(r['first'] for r in records if r['source']==source and not r['controlled']);after=next(r['first'] for r in records if r['source']==source and r['controlled'])
        values=[before['rho_max'],before['rho_max'],after['rho_max'],after['rho_max']]
        bars=ax.bar(['B0','AIDC only\napplied action 0','MESS only','Joint\nAIDC action 0'],values,color=['#606f80','#1267a5','#d45422','#7661a8'])
        for b,value in zip(bars,values):ax.text(b.get_x()+b.get_width()/2,value+.005,f'{value:.6f}',ha='center',fontsize=9)
        ax.set_ylim(0,max(values)*1.12);ax.set_ylabel('Global max96 rho [pu]');ax.set_title(source+' 96-slot fixed schedule');ax.grid(axis='y',alpha=.2)
    fig.suptitle('Nonzero AIDC contract unverified: applied action 0; recorded Joint equals MESS',fontsize=11)
    savefig(fig,'07_CERTIFIED_AIDC_MESS_JOINT_COMPARISON')
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,source in zip(axes,('PLANNING','ACTUAL')):
        subset=[r for r in critical if r['source']==source];subset=sorted(subset,key=lambda r:-r['B0_max96_rho'])[:15];y=np.arange(len(subset))
        ax.barh(y-.18,[r['B0_max96_rho'] for r in subset],height=.35,color='#606f80',label='B0');ax.barh(y+.18,[r['MESS_fixed_schedule_max96_rho'] for r in subset],height=.35,color='#d45422',label='MESS fixed schedule')
        ax.set_yticks(y,[r['line'].replace('Line.','') for r in subset],fontsize=7);ax.invert_yaxis();ax.set_xlabel('Maximum rho over all96 slots');ax.set_title(source+' highest original-line bottlenecks');ax.legend(fontsize=8);ax.grid(axis='x',alpha=.2)
    fig.subplots_adjust(wspace=.48)
    savefig(fig,'08_TOP_ORIGINAL_LINE_BOTTLENECK_CHANGES')
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for label,color,style in [('M1','#1267a5','-'),('M2','#d45422','--'),('M3','#7661a8',':')]:
        soc=rows(REPORT/f'{label}_SOC_96.csv');power=np.array([sum(float(r['P_consumption_AC_kw']) for r in soc if int(r['slot'])==t) for t in range(96)])
        units=sorted({r['unit'] for r in soc});energy=np.array([float(next(r['E_after_kwh'] for r in soc if r['unit']==units[0] and int(r['slot'])==t)) for t in range(96)])
        axes[0].plot(range(96),power,c=color,ls=style,label=label);axes[1].plot(range(96),energy,c=color,ls=style,label=label)
    axes[0].set_ylabel('Six-vehicle total AC consumption [kW]');axes[1].set_ylabel('One representative vehicle SOC [kWh]')
    for ax in axes:ax.set_xlabel('May01 15-minute slot');ax.grid(alpha=.2);ax.legend()
    axes[1].axhline(1620,c='black',ls='--',lw=.7);axes[1].axhline(660,c='black',ls='--',lw=.7)
    fig.suptitle('Fixed proxy schedule Q=0; M2/M3 coincide under battery headroom rule\nNo travel; original initial STA identities, slot0 blocked, terminal SOC1140 kWh',fontsize=11)
    savefig(fig,'09_INTERFACE_FIXED_SCHEDULE_AND_SOC96')


def _fmt(value):return f'{float(value):.9f}'


def documents(config,mapping,records,summaries,physical):
    selected=rows(mapping);case=config['case'];bg=config['bg'];prepath=REPORT/'precheck/RECEIPT.json'
    pre=read(prepath) if prepath.exists() else {'status':'PENDING_ROOT_PRECHECK'}
    model_pass=all(r['status']=='PASS' for r in physical if r['dataset']!='COMMON')
    decision=read(REPORT/'PLANNING_SCENARIO_SELECTION.json');rule=read(REPORT/'OPERATING_POINT_PREREGISTRATION.json')
    before={r['source']:r['first'] for r in records if not r['controlled']};after={r['source']:r['first'] for r in records if r['controlled']}
    resulttable=['| 입력 | B0 전체/Primary/Triplex 최대ρ | MESS=적용 Joint 전체최대ρ | B0 Vmin/Vmax | 전압/선로/변압기 위반 |',
        '|---|---|---:|---|---|']
    for source in ('PLANNING','ACTUAL'):
        a,b=before[source],after[source]
        resulttable.append(f"| {source} May01 | {_fmt(a['rho_max'])} / {_fmt(a['Primary_rho_max'])} / {_fmt(a['Triplex_rho_max'])} | {_fmt(b['rho_max'])} | {_fmt(a['Vmin'])} / {_fmt(a['Vmax'])} | {a['voltage_violation_cells']}/{a['line_overload_cells']}/{a['CT_current_overload_cells']+a['CT_nameplate_overload_cells']} |")
    resulttext='\n'.join(resulttable)
    endpoints=read(REPORT/'PHYSICAL_ENDPOINT_CONSTRAINT_SUMMARY.json')
    max_endpoint=max(float(r['Vmax']) for r in endpoints['failed_corners'])
    configtext=f'''# 단일 공동 PCC 연구 시나리오 결정

선정은 **{case}, BG={bg:.2f}, 원본 설치 GPU 합계780, AIDC12·STA12·MESS6**이다. STA는 중압12·저압0이고 원본 ABC 12.47 kV 버스에 별도 750 kVA·12.47/0.480 kV 전용 변압기와 480 V 3상 포트를 모델링했다. 모든 원본 선로·서비스 변압기·전압0.95–1.05 pu 제약 및 전체 `min rho_max` 목적은 유지했다. 원본 DSS와 기존 캠페인, Native/Adaptive/RMP/Pricing/독립 UB/LB 알고리즘을 바꾸지 않았다.

입지·8권역·권역 cap·C1의6MV/6LV parity 및 C2의12MV가 점수와 정책 결과 전에 사전등록됐다. 최종 점수는 기존 C0·BG0.85 B0의 복수 혼잡선로/시간 ±1 kW/±1 kvar AC에 기반하며 6시간 자료와 peak74 보충 자료를 구분 보존했다. 공통 proper similarity135°에서 276쌍/552축·24개 버스 고유성·분산 제약이 PASS였다. 전역 최적화가 아니라 점수 우선순위의 첫 완전 공동 witness이며 overlap은 감사했으나 최적화하지 않았다.

Planning으로만 C1/C2×BG[0.552,0.65,0.75,0.85,0.95] 10개 B0 96슬롯을 검사했다. 원본 제약 PASS·전체ρ0.75–0.85 후보 중 C2 우선, 0.8에 가까운 값, 작은 BG 순이라는 동결 규칙에 따라 {case}/BG{bg}를 선정했다. Actual·MESS 효과·B1/B2/B3 결과는 입지·BG·GPU·포트 정격 선택에 사용하지 않았다. 선정 당시 B0 peak는 slot{before['PLANNING']['peak_slot']}의 {before['PLANNING']['binding_line']} node{before['PLANNING']['binding_node']}이다.

{resulttext}

Planning/Actual 각각 B0·MESS와 별도 Fresh compile을 포함한 May01 8개 완전96슬롯 결과의 모델 전기 적격성은 **{'PASS' if model_pass else 'FAIL'}**다. 이 결과는 현장 설치 인증 또는 AIDC 비영 유연성·B1/B2/B3 Production 인증이 아니다. 최신 날짜 지시는 May01-only이며 May02 입력/과거 결과는 보존하고 새 공동 선정·효과 검증에서 제외했다. Forecast와 private Actual의 paired replay이며 미노출 독립 검증일이라고 주장하지 않는다.

**완전 P450/Q300 제어 영역은 NOT_CERTIFIED다.** 별도 순간 finite endpoint190개 중20개가 P=-450 kW·Q=-300 kvar injection에서 과전압으로 FAIL했고 최고전압은{max_endpoint:.12f} pu였다. line/TX/port-limit 위반0은 과전압을 상쇄하지 않는다. 선택한 완전96 Q0 schedule의 PASS를 임의 Q정책 지원 PASS로 확대하지 않았다. 정격·위치·제어 목표를 바꾸어 통과시키지 않았다.

차량은 P450 kW·S600 kVA·E1800 kWh·Emin660/Emax1620·initial/terminal1140 kWh다. 중압 포트의 실제 상전류 한계는721.687836 A이며 kVA circle만으로 통과시키지 않았다. 원본6개 초기 STA에서 이동0·600초 초기 연결 가정·slot0 차단·STA당 차량1·Q0의 고정 feasible proxy schedule을 사용했다. 충전slot8–15, 방전68–75는 효과 결과 전에 결정됐다. M3의 nominal P450과 실제 schedule 출력은 다르다. 배터리 headroom480 kWh/2h·효율0.95로 충전은252.631579 kW/대, 방전228 kW/대로 제한된다. M2/M3가 같은 이 고정 schedule을 가질 수 있으며 이는 M3 완전450 kW 운전이나 최적 schedule을 인증하지 않는다.

비영96슬롯 AIDC QoS/WAN/checkpoint 실행가능성을 검증하지 못했으므로 이번 연구에서 적용한 admissible AIDC action은0이다. 이는 실제 물리적 유연 잠재력이0이라는 증명이 아니다. 원본 Job·PF0.95·Reference/Queue/C1과 known-mask relaxation은 보존했다. 따라서 이 조건부 모델 AC/SOC 기록에서 AIDC-only=B0, Joint=MESS-only이며 관측 추가 이득은0, 비영 AIDC 공동 기여는미입증이다. 순간 known-mask 또는6STA endpoint는 정책 개선율이 아니다.

C2는 원본 트리8권역 중7권역을 덮지만 STA–STA66쌍 모두 frozen screening P-response cosine≥0.95이고 중앙값0.998440·support Jaccard1.0이다. 3개 named major lateral 라벨과 TRUNK_OR_MINOR_LATERAL 집계 bucket에 걸쳐 있다는 사실을7개 독립 feeder나4개 독립 physical lateral로 바꾸어 표현하지 않는다. 실제 전기적 제어 독립성·공동 추가 이득은 UNPROVEN이다.

하드웨어/GIS·이동의 한계는 **ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED / UNVERIFIED**다. 750 kVA·5.75% |Z|·12.47Δ/0.480Y 사양은 상용 topology 근거를 사용했으며 %R=1, XHL=5.662375826%, noloadloss0.2%, imag0.5%, node0 solid grounding은 연구 가정이다. 실제 mobile600 kVA 제품/DC interface/온도 derating, short-circuit·relay/fuse coordination·역송전 승인·anti-islanding·접지·현장 road access·도식 CRS는 미인증이다. 원본 추상 traffic ETA를 새 PCC의 실측 접근시간이라고 부르지 않는다. 현장 승인 export 기본값0과 시뮬레이션 reverse injection을 구분한다.

최종 map SHA: `{config['mapping']['sha256']}`. top-level JOINT_LOCATION_SELECTION.csv는 선택한 원본 파일의 byte-identical copy다. 배치·BG는 검증 후 효과로 재조정하지 않았으며 source SHA와 모든 실패 endpoint를 보존했다. B1/B2/B3 장시간 Solver 호출은0이다. 새 MV 및6대 DTO Native/grid interface, 실제 비영 AIDC96QoS, 현장 하드웨어/보호/GIS gate가 해결될 때까지 Production 승격은 차단한다.
'''
    (REPORT/'FINAL_SCENARIO_DECISION_KO.md').write_text(configtext,encoding='utf-8')
    mappingtable=['| ID | 원본 IEEE8500 PCC | 역할/접속 | 권역 |','|---|---|---|---|']
    mappingtable += [f"| {r['location_id']} | {r['candidate_bus']} | {r['role']} / {r['connection_mode']} | {r['electrical_region']} |" for r in selected]
    inputs={}
    for source in ('PLANNING','ACTUAL'):
        with np.load(ROOT/f'ieee8500_v42_high/data/facility/recomputed/C0_{source}_INPUTS.npz') as a:
            inputs[source]={'capacity':int(a['capacities'].sum()),'P_peak':float(a['PCC_P_kw'].sum(axis=1).max()),
                'mask_peak':float(a['source_mask_P_upper_bound_kw'].sum(axis=1).max()) if 'source_mask_P_upper_bound_kw' in a else None,
                'mask_at_b0_peak':float(a['source_mask_P_upper_bound_kw'][before[source]['peak_slot']].sum()) if 'source_mask_P_upper_bound_kw' in a else None,
                'certified_peak':float(a['certified_reducible_P_kw'].sum(axis=1).max())}
    pretext=f"선정 후 순간 AC 사전검사는 `{pre.get('status')}`이다. 숫자 CSV 6,270행·33target의 모든 실패를 보존했다. 실패 target행은{pre.get('failed_endpoint_line_rows','PENDING')}이며 target별 중복행이므로 이를 독립 실패 dispatch 수로 세지 않는다. 상세 개별 endpoint port readback은 `{pre.get('endpoint_individual_port_raw_readback','PENDING')}`이다. 실제 port-limit boolean 요약과 전압·선로 수치는 CSV에 남았고 복구 AC solve0이었다. 완전96슬롯 PORT_96.json의 실제 P/Q·상전류는 모두 보존됐다."
    actual_mask_text=f"{inputs['ACTUAL']['mask_peak']:.6f} kW" if inputs['ACTUAL']['mask_peak'] is not None else '미산출(Actual causal queue archive에 source-mask 필드 없음; Planning mask를 대입하지 않음)'
    retention=read(REPORT/'LOCAL_DENSE_AC_RETENTION.json');dense_count=len(retention['files']);dense_bytes=sum(r['bytes'] for r in retention['files'].values())
    efficiency=read(REPORT/'EXECUTION_EFFICIENCY.json')
    effects=[]
    for source in ('PLANNING','ACTUAL'):
        a,b=before[source],after[source];effects.append(f"{source}에서 B0 {_fmt(a['rho_max'])}→MESS/Joint {_fmt(b['rho_max'])}, 차이는{100*(a['rho_max']-b['rho_max']):.6f}%p다. 이는 동일 May01 고정 feasible 연구 schedule의 AC 결과이고 B0–B3 정책 개선율이 아니다.")
    answers=[
        ('Q1. 기존 불가능성은 새 공동 문제에도 적용되는가?','아니다. 고정 AIDC12+guardedMV606+공통 proper rotation 조건에서만 STA6개 도메인0이었다. AIDC 고정을 해제한 C1/C2의 실제552축 PASS witness가 새 문제의 feasible 증거다.'),
        ('Q2–Q3. AIDC12와 STA12는 어디인가?','다음 원본 버스 표와 JOINT_LOCATION_SELECTION.csv/P0_PCC_MAPPING_COMPARISON.csv를 참조한다.'),
        ('Q4. STA MV/LV 수는?','선정 C2는12/0. 비교 C1은 사전 parity6/6, C0는 원래0/12이다. 차량은 모든 경우6대이며 위치24개를 유지한다.'),
        ('Q5. 전기·교통 분산성이 충분한가?','동결 연구 제약(AIDC/STA 각≥4권역, 전체≥6권역, 역할별≤4·합계≤6/권역)은 PASS. C2는 각각7권역이고 원본 traffic24 IDs/ETA가 유지된다. 현장 거리·GIS 접근성과 Native6대 이동 인증, 전기적 응답 독립성은 미확인이라 설치·Production 충분성으로 확대하지 않는다.'),
        ('Q6. 서로 다른 lateral에는 얼마나 분산됐는가?','MAJOR:l2820531=2, MAJOR:l3081380=9, MAJOR:m1047526=5, TRUNK_OR_MINOR_LATERAL 집계=8개다. 원본3개 named major 라벨+집계 bucket이며 arbitrary8권역을 independent lateral로 세지 않는다.'),
        ('Q7. Planningρ는0.75–0.85 범위인가?',f"B0 {_fmt(before['PLANNING']['rho_max'])}로 범위 내다. BG={bg}는 Planning-only 사전 규칙에 따라 선택했고 실제 Actual 값으로 조정하지 않았다."),
        ('Q8. Primary/Triplex 병목은?',f"Planning B0의 Primary/Triplex 최대는{_fmt(before['PLANNING']['Primary_rho_max'])}/{_fmt(before['PLANNING']['Triplex_rho_max'])}, MESS는{_fmt(after['PLANNING']['Primary_rho_max'])}/{_fmt(after['PLANNING']['Triplex_rho_max'])}. Binding은 B0 {before['PLANNING']['binding_line']} node{before['PLANNING']['binding_node']}에서 MESS {after['PLANNING']['binding_line']} node{after['PLANNING']['binding_node']}로 바뀐다. 전체96 binding·상위20·다른 상·Triplex는 별도 CSV로 보존했다."),
        ('Q9. AIDC-only의 실제 제어량은?',f"비영96슬롯 QoS/WAN/checkpoint 계약을 검증하지 못해 적용한 admissible action0 kW다. 실제 물리적 잠재력0의 증명은 아니다. Planning 원본 mask 감축 상한의 시간최대{inputs['PLANNING']['mask_peak']:.6f} kW, B0 peak slot에서{inputs['PLANNING']['mask_at_b0_peak']:.6f} kW는 relaxation이지 실제 정책 인증량이 아니다. 시설 전체 Planning P 피크{inputs['PLANNING']['P_peak']:.6f} kW와 혼동하지 않는다."),
        ('Q10. MESS-only의 실제 제어량은?','6대 stationary proxy schedule에서 충전8슬롯 총1515.789474 kW, 방전8슬롯 총1368 kW, Q0; unit initial/terminal1140·최대1620·기존660–1620 SOC 범위와 current gate를 유지했다. 실제6대 이동 효과는 실행하지 않았고 abstract 원본 access 자료는 별도이다. '+' '.join(effects)),
        ('Q11. Joint의 추가 상호보완 효과는?','비영 AIDC 계약 미검증으로 이번 action을0으로 두어 조건부 연구 기록의 Joint=MESS-only, 관측 추가 효과0이다. 실제 잠재력0을 증명한 것은 아니다. known-mask relaxation+instant sixSTA AC는 미인증 endpoint로만 표시하고 STA응답66쌍 중복을 보존한다.'),
        ('Q12. 무엇이 제한하는가?','AIDC QoS/WAN/checkpoint·작은 source mask, 공통 Primary/Triplex 병목 전환, 실제 포트 상전류·S600·전용TX750, SOC·연결·이동, Native/grid six-vehicle 호환성, 보호·접지·역송전·GIS/현장 데이터 부재다. 정격·전압을 완화하지 않았다.'),
        ('Q13. 모든 V42 비교군에 공통 적용 가능한가?','동일 physical configuration/P5/원본Job/전체minρ 목적을 비교군에 사용하는 연구 설계는 저장했다. 새 MV/grid/Native 및6대 API와 비영 AIDC 계약을 추가 검증해야 한다. B1/B2/B3를 실행하지 않았고 Production 준비 PASS라고 선언하지 않는다.')]
    answers_text='\n'.join('### '+question+'\n\n'+answer+'\n' for question,answer in answers)
    review=f'''# IEEE8500 V42 공동 PCC 최종 검토

**단일 선택은 C2/BG0.85/원본780GPU/12MV STA이며 May01의 완전96슬롯 모델-grid·Fresh 적격성은 {'PASS' if model_pass else 'FAIL'}다. 현장·Native Production 승격은 UNVERIFIED gate로 차단한다.**

{resulttext}

{answers_text}

{chr(10).join(mappingtable)}

### 실행·제어 및 자료 범위

Source1.04 pu, 전체12 RegControl Vreg123.5 V, 기존 CAPBank3 off의 P5 overlay를 모든 비교군에 공통 적용했다. 원본 deadband/tap 한계·CapControl 지연과 임계값·설비 정격은 유지했다. 모든96슬롯 자동 settle, 실제tap 궤적·커패시터 states 및 phase/node 전압을 기록하고 SOURCE/P5 SHA를 보존했다. 원본 source SHA31개는 변하지 않았다. 배경부하 배율0.85와 설치GPU780·실제 workload·PCC power·적용가능 action은 서로 다른 항목이다. GPU780은12site 합계이며 logical rack pool을 실물 rack/냉각/PSU 정격으로 인증하지 않는다. Actual 시설 P 피크는{inputs['ACTUAL']['P_peak']:.6f} kW, Actual mask 피크는{actual_mask_text}, 비영 계약 미검증에 따른 적용action은{inputs['ACTUAL']['certified_peak']:.6f} kW다. 실제 물리 잠재력0이라는 증명이 아니다. PV actual injection은 제거하지 않고 원본 Rooftop 데이터와 weather/AEMO/Kestrel 권위를 유지했다.

May01-only 지시가 과거 May02 paired-check 계획을 덮어썼다. May02 source/input/결과는 보존했고 이번 공동 케이스의 선정·효과·미노출 검증으로 사용하지 않았다. 완료 matching AC는 metadata/SHA를 확인해 재사용했으며 interrupted output은 별도 보존했다. 날짜/시간대는 source 운전 모델의 AEST(+10)이고 host KST와 혼동하지 않는다. Source publication/as-of·CC4/calibration의 미인증 한계는 SOURCE_AUTHORITY.md와 계승 SOURCE_AUDIT.json에 남았다.

최종 May01 실행 효율 원장은 완료96슬롯{efficiency['completed96_reused']}개 재사용, 신규{efficiency['new_completed96_cases']}개(운영점{efficiency['new_completed96_operating_points']}개) 및 finite/base{efficiency['new_finite_operating_points']}개를 구분한다. 완료 운영점의 명시 API Solve{efficiency['new_completed_operating_point_Solution_Solve_calls']}회와 초기화{efficiency['explicit_initialization_Solution_Solve_calls']}회를 합쳐{efficiency['known_completed_explicit_API_Solve_calls']}회다. 기록된 신규 AC runtime은{efficiency['new_recorded_AC_runtime_seconds']:.6f}초이며 finite 구간은 filesystem timestamp 근사다. DSS 내부 network iterations/CalcVoltageBases solve 및 중단된 미완료 May01 M2의0..95 운영점은 이 완료 수치에 들어있지 않다. 이미 완료된 민감도·기존46검증·QoS/geometry를 다시 실행하지 않았고 새 경량 date/resume 테스트{efficiency['new_lightweight_date_resume_tests']}개만 수행했다. Native/장시간 policy Solver0, 보고서 생성의 AC solve0이다.

외부 캠페인 보존 감사에서 이번 작업의 외부campaign 쓰기·중단은0, input/manifest와 scheduler registration 변경도0이다. 다만 다른 활성 작업 중 live 외부source9개(B2 monitor1·seed recovery8)가 변경되고 stationary_dispatch.py1개가 추가되어 `original_authorities_equal=False`로 기록됐다. 모든 live 캠페인 소스가 byte-identical하다고 주장하지 않는다. 이것은 원본 DSS 및 과거PR193/196/197의 sealed 권위 보존과 구분하며, 이번 작업 자체의 진단 runner중단2건을 외부campaign중단으로 혼동하지 않는다. 상세는 별도 CAMPAIGN_PRESERVATION_REFERENCE.json이다.

{pretext}

190개 finite endpoint 중20개는 P=-450/Q=-300 injection의 새480V 포트 노드 과전압으로 FAIL이며 최고{max_endpoint:.12f} pu다. line·TX·port-limit 위반0도 전압 FAIL을 해소하지 않는다. `PHYSICAL_ENDPOINT_CONSTRAINT_SUMMARY.csv/json`은 개별endpoint와 corner를 구분 기록했다. full P450/Q300 rectangle은 NOT_CERTIFIED이며 현재의 Q0 96슬롯 schedule PASS를 무효전력 정책 전체의 안전성 인증으로 확대하지 않는다. 장치 정격·입지·P5를 사후 조정하지 않았다.

전용 포트 hardware는 ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED이다. 상용750kVA 12.47Δ/480Y topology/5.75% impedance 근거는 [Eaton](https://www.eaton.com/content/dam/eaton/products/utility-and-grid-solutions/transformer/pad-mounted-transformer/Eaton-Pad-mounted-Transformer-Brochure-EN-US.pdf), [ELSCO](https://elscotransformers.com/transformers/dry-type-transformers/750-kva-12470-delta-to-480y-277/)이며 모듈 병렬 규모 근거는 [Dynapower MPS125](https://dynapower.com/products/energy-storage/mps-125-energy-storage-inverter/)다. 정확한 mobile600kVA 제품, DC interface·온도·보호·현장 as-built가 인증됐다는 뜻이 아니다. %R1·XHL5.662375826·no-load0.2·imag0.5·ideal grounded node0는 문헌 topology를 따른 모델 가정이다. IEEE1547·short-circuit·인입선/GIS/역송전 승인/접지·anti-islanding commissioning은 미확인이다. 새 primary conductor0, 기존 original Triplex 삭제0·정격확대0다.

8권역과24개 교통서비스의 방향을 통과했어도 실제 접근성·거리 또는 영향 독립성 PASS는 아니다. C2 STA–STA66쌍의 median cosine0.998440은 대부분 같은 주요 선로 응답을 공유한다는 제한이다. 형상 변환은 하나의135° proper similarity이며 0.001 km 축 공차는 탐색 전에 동결했다. 새로운 source/position 좌표를 만들거나 위치별 반사·회전을 하지 않았다. 그림의 label offset은 가독성용이고 PCC 좌표는 source 원본이다.

### 재현·감사 파일

- `python -B -X utf8 -m ieee8500_v42_joint.report`는 완료된 AC/score/geometry/traffic 기록만 읽는다. 이 보고 작업의 AC·Native 호출은0이다.
- JOINT_LOCATION_SELECTION.csv SHA `{config['mapping']['sha256']}`; 같은 mapping은 C2_SCORED에 보존됐다.
- BG085_B0_PLANNING_AC_96.csv, FINAL_B0_PLANNING_ACTUAL_FRESH.csv, FINAL_MESS_PLANNING_ACTUAL_FRESH.csv, FINAL_AC_SUMMARY.csv
- MV_PORT_RATING_AUDIT.csv, PHYSICAL_CONSTRAINT_AUDIT.csv, FINAL_REGCONTROL_CAPCONTROL_TRAJECTORIES.csv
- CRITICAL_CORRIDOR_CONTROL_AUDIT.csv, FINAL_TOP20_ORIGINAL_LINE_BOTTLENECKS.csv, AIDC_MESS_JOINT_PRECHECK.csv
- P0_PCC_MAPPING_COMPARISON.csv, ORIGINAL_PRIMARY_CONNECTION_PATH_AUDIT.csv, JOINT_CONTROL_OVERLAP_AUDIT.csv의 상세는 C1_SCORED/C2_SCORED 하위에 있다.
- Python 생성 SVG/PNG는 figures/에 저장했다. 원본 topology와 named bus/proxy 좌표를 사용했으며 이미지 생성 AI를 사용하지 않았다.

로컬 dense AC archive {dense_count}개·{dense_bytes/1e9:.3f} GB는 `LOCAL_DENSE_AC_RETENTION.json`에 exact SHA/크기로 seal하여 원본 그대로 보존했다. 대용량 AC_96.npz만 Git 전송에서 제외되며 CSV·고객/PV/PCC·phasor·control·port·receipt·code는 별도 전달된다. 큰 JSON 축/parameter snapshot은 lossless gzip으로 전달하고 원본 JSON은 로컬 보존했으며 transport SHA와 decoded SHA를 각각 감사했다. 이 report는 raw JSON이 없을 때 동일 내용의 .json.gz를 읽는다. **remote_clone_dense_AC_available=False**이므로 원격 clone만으로 dense 전체 엄격 검증이나 이 report의 all-line 분석을 실행할 수 없다. 동일 SHA archive를 복원해야 하며 원격 완전 재현 PASS를 주장하지 않는다. 이 보존 조치는 source/data 변경이나 추가 AC 실행이 아니다.

최적해·글로벌 최적성·미노출 독립검증·B0–B3 개선율·실증 설치 가능성을 주장하지 않는다. 실제 정책·Native/grid 결합·현장 gate를 충족하기 전까지 최종 Production 동결을 하지 않는다.
'''
    (REPORT/'FINAL_REVIEW_KO.md').write_text(review,encoding='utf-8')
    return model_pass


def run():
    config,mapping,run_receipt,records=complete_inputs()
    summaries,physical,portrows=numerical_exports(config,mapping,records)
    interface_exports(portrows)
    critical,top=line_audits(records)
    plot_topology(mapping);plot_geometry_regions(mapping);plot_controls(records,critical)
    passed=documents(config,mapping,records,summaries,physical)
    outputs=[p for p in REPORT.iterdir() if p.name in {'JOINT_LOCATION_SELECTION.csv','BG085_B0_PLANNING_AC_96.csv',
        'FINAL_B0_PLANNING_ACTUAL_FRESH.csv','FINAL_MESS_PLANNING_ACTUAL_FRESH.csv','FINAL_AC_SUMMARY.csv',
        'MV_PORT_RATING_AUDIT.csv','INTERFACE_MODEL_SCHEDULE_COMPARISON.csv','PHYSICAL_CONSTRAINT_AUDIT.csv','FINAL_REGCONTROL_CAPCONTROL_TRAJECTORIES.csv',
        'CRITICAL_CORRIDOR_CONTROL_AUDIT.csv','FINAL_TOP20_ORIGINAL_LINE_BOTTLENECKS.csv','FINAL_SCENARIO_DECISION_KO.md','FINAL_REVIEW_KO.md'}]
    outputs+=list(FIG.glob('*.svg'))+list(FIG.glob('*.png'))
    proof={'schema':'JOINT_MAY01_READONLY_REPORT_V1','day':DAY,'selected_case':config['case'],'bg':config['bg'],
        'producer_sha256':sha(Path(__file__)),
        'mapping_sha256':sha(mapping),'source_run_receipt_sha256':sha(REPORT/'RUN_RECEIPT.json'),
        'outputs_sha256':{str(p.relative_to(REPORT)):sha(p) for p in outputs},
        'model_grid_and_port_Fresh_admissibility_PASS':passed,'field_Production_PASS':False,
        'AIDC_applied_admissible_action_kw':0,'nonzero_AIDC_QoS_contract_verified':False,'Joint_record_equals_MESS':True,
        'new_AC_solves':0,'new_Native_calls':0,'new_sensitivity_computations':0,'location_or_scale_changes':0,
        'May02_used':False,'independent_unseen_holdout_claim':False,'global_optimality_claim':False}
    write_json(REPORT/'REPORT_RECEIPT.json',proof)
    print(json.dumps({'model_grid_PASS':passed,'records':len(summaries),'plots':len(list(FIG.glob('*.svg'))),'AC_calls':0,'mapping_sha256':sha(mapping)},indent=2))


if __name__=='__main__':run()
