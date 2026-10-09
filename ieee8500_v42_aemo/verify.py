"""Independent saved-array arithmetic, per-customer mapping and phasor checks."""
import numpy as np
from .common import *
from .archives import CORE_KEYS
from .run_b0 import compare
from .engine import target_vreg


def verify_stage(folder):
    axes=read(folder/'AC_AXES.json');slots=rows(folder/'SLOTS.csv');rec=read(folder/'RECEIPT.json')
    mask=np.array(axes['objective_mask'],bool)
    ratings=np.array([r['normal_amps'] for r in axes['lines']])
    assert len(slots)==96 and len(axes['nodes'])==8531
    assert axes['original_object_inventory']['lines']==3703
    assert axes['original_object_inventory']['transformers']==1190
    assert len({r['element'] for r in axes['lines'] if r['objective_included']})==3698
    with np.load(folder/'AC_96.npz') as z:
        a={key:z[key] for key in CORE_KEYS}
    assert all(v.shape[0]==96 and np.isfinite(v).all() for v in a.values())
    assert np.max(np.abs(a['line_rho']-a['line_amps']/ratings))<1e-12
    voltage=a['node_voltage_pu'];rho=a['line_rho']
    for t,row in enumerate(slots):
        assert int(row['slot'])==t
        binding=int(np.argmax(np.where(mask,rho[t],-np.inf)))
        assert row['binding_line']==axes['lines'][binding]['element']
        assert int(row['binding_local_node'])==axes['lines'][binding]['node']
        quantities=dict(rho_max=float(rho[t,mask].max()),Vmin=float(voltage[t].min()),Vmax=float(voltage[t].max()),
            full_both_terminal_conductor_rho_max=float(rho[t].max()),
            transformer_current_rho_max=float(a['transformer_current_rho'][t].max()),
            transformer_nameplate_kva_rho_max=float(a['transformer_winding_nameplate_kva_rho'][t].max()),
            undervoltage_cells=int((voltage[t]<.95).sum()),overvoltage_cells=int((voltage[t]>1.05).sum()),
            full_line_overload_cells=int((rho[t]>1).sum()),
            transformer_current_overload_cells=int((a['transformer_current_rho'][t]>1).sum()),
            transformer_nameplate_overload_cells=int((a['transformer_winding_nameplate_kva_rho'][t]>1).sum()))
        for group in ('Primary','Triplex'):
            select=mask&np.array([r['group']==group for r in axes['lines']])
            quantities[group+'_rho_max']=float(rho[t,select].max())
        for key,val in quantities.items():assert abs(float(row[key])-val)<1e-10,(folder.name,t,key)
    assert abs(rec['rho_max']-rho[:,mask].max())<1e-10
    assert rec['voltage_violation_cells']==int(((voltage<.95)|(voltage>1.05)).sum())
    assert rec['AC_arrays']['sha256']==sha(folder/'AC_96.npz')
    controls=rows(folder/'CONTROL_STATES_96.csv')
    assert len(controls)==96*31
    for t in range(96):
        rr=[r for r in controls if int(r['slot'])==t]
        assert sum(r['kind']=='RegControl' for r in rr)==12
        assert sum(r['kind']=='CapControl' for r in rr)==9
        assert sum(r['kind']=='Capacitor' for r in rr)==10
        assert all(r['enabled']=='True' for r in rr)
        for r in rr:
            if r['kind']=='RegControl':
                assert float(r['min_tap'])<=float(r['tap_ratio'])<=float(r['max_tap'])
                assert float(r['Vreg'])==target_vreg(rec['policy'],r['name'])
    with np.load(folder/'PHASOR_FORENSICS.npz') as z:
        li=z['line_indices'];ni=z['node_indices'];currents=z['line_complex_A'];powers=z['line_complex_kVA'];vv=z['node_complex_V']
    assert np.max(np.abs(np.abs(currents)-a['line_amps'][:,li]))<1e-10
    nodes={axes['nodes'][i].lower():j for j,i in enumerate(ni)}
    inventory={r['element']:r for r in read(PR193/'ORIGINAL_FEEDER_INVENTORY.json')['lines']}
    error=0.;identities=[]
    for j,i in enumerate(li):
        meta=axes['lines'][i];node=meta['node']
        bus=inventory[meta['element']]['buses'][meta['terminal']-1].split('.')[0].lower()
        volt=np.zeros(96,complex) if node==0 else vv[:,nodes[bus+'.'+str(node)]]
        identity=volt*np.conj(currents[:,j])/1000
        error=max(error,float(np.abs(identity-powers[:,j]).max()))
        if meta['element'].lower()=='line.tpx21459660c0' and meta['objective_included']:
            for t in range(96):identities.append(dict(stage=folder.name,slot=t,local_hot=node,
                voltage_V=float(abs(volt[t])),P_kw=float(powers[t,j].real),Q_kvar=float(powers[t,j].imag),
                current_A=float(abs(currents[t,j])),current_from_power_voltage_A=float(abs(powers[t,j])*1000/abs(volt[t])),
                identity_error_kVA=float(abs(identity[t]-powers[t,j])),rho=float(rho[t,i])))
    assert error<1e-8,'PHASOR_POWER_IDENTITY_FAILED'
    return dict(stage=folder.name,arithmetic_PASS=True,physical_all96_PASS=rec['hard_constraints_PASS'],
                phasor_identity_max_error_kVA=error,source_receipt=sha(folder/'RECEIPT.json')),identities


def verify_customers(source,prefix='B0_'):
    stage=REPORT/'ac'/(prefix+source);loads=rows(REPORT/'FIXED_VARIABLE_LOAD_AUDIT.csv')
    pv=rows(REPORT/'PV_PCC_CAPACITY_AUDIT.csv')
    with np.load(DATA/'derived'/f'{source}_INPUTS.npz') as z:data={k:z[k] for k in z.files}
    with np.load(stage/'CUSTOMER_PV_PQ_96.npz') as z:nom=z['original_nominal'];actual=z['actual_customer'];solar=z['actual_PV']
    fixed=np.array([r['status']=='fixed' for r in loads]);base=np.array([[float(r['original_P_kw']),float(r['original_Q_kvar'])] for r in loads])
    factor=np.repeat((BG_SCALE*data['gross_factor'])[:,None],2354,axis=1);factor[:,fixed]=BG_SCALE
    expected=factor[:,:,None]*base[None,:,:]
    assert np.max(np.abs(nom-expected))<1e-10
    assert fixed.sum()==48 and (~fixed).sum()==2306 and np.max(np.ptp(nom[:,fixed],axis=0))==0
    capacity=np.array([float(r['installed_kw']) for r in pv]);expected_pv=data['pv_factor'][:,None]*capacity
    # Original model1 becomes constant impedance outside its voltage-characteristic
    # limits. Bus pu base (208/sqrt3 V) differs slightly from Load/Generator120V.
    inv=read(PR193/'ORIGINAL_FEEDER_INVENTORY.json');bases={r['bus'].lower():r['kv_base_ln'] for r in inv['buses']}
    axes=read(stage/'AC_AXES.json');node_lookup={n.lower():i for i,n in enumerate(axes['nodes'])}
    with np.load(stage/'AC_96.npz') as z:volts=z['node_voltage_pu']
    nodes=np.array([node_lookup[r['bus'].lower()] for r in pv])
    vpu=volts[:,nodes]*np.array([bases[r['bus'].split('.')[0].lower()]/float(r['nominal_kv']) for r in pv])
    vmin=np.array([float(r['Vminpu']) for r in loads]);vmax=np.array([float(r['Vmaxpu']) for r in loads])
    effect=np.where(vpu>vmax,(vpu/vmax)**2,np.where(vpu<vmin,(vpu/vmin)**2,1.))
    pv_error=float(np.abs(solar[:,:,0]-expected_pv*effect).max())
    assert pv_error<1e-5,('PV_MODEL1_CHARACTERISTIC_DRIFT',pv_error)
    assert np.max(np.abs(solar[:,:,1]))<1e-4
    assert np.all(data['total_gpu']<=data['capacities'][None,:]+1e-9)
    assert np.max(np.abs(data['PCC_Q_kvar']-data['PCC_P_kw']*np.tan(np.arccos(.95))))<1e-10
    rec=read(stage/'RECEIPT.json')
    assert abs(rec['background_nominal_kWh']-nom[:,:,0].sum()/4)<1e-7
    return dict(source=source,PASS=True,Fixed_count=48,Variable_count=2306,
        background_nominal_kWh=float(nom[:,:,0].sum()/4),background_actual_kWh=float(actual[:,:,0].sum()/4),
        research_PV_installed_kW=float(capacity.sum()),PV_actual_kWh=float(solar[:,:,0].sum()/4),
        original_model1_voltage_characteristic_error_kw=pv_error)


def run():
    stages=[];identity=[]
    for folder in sorted((REPORT/'ac').iterdir()):
        if not (folder/'AC_96.npz').exists():continue
        result,detail=verify_stage(folder);stages.append(result);identity.extend(detail)
    for x,y,out in [('B0_PLANNING','B0_PLANNING_FRESH','PLANNING_FRESH_VERIFICATION.json'),
                    ('B0_ACTUAL','B0_ACTUAL_FRESH','ACTUAL_FRESH_VERIFICATION.json')]:compare(x,y,out)
    customers=[verify_customers(x) for x in ('PLANNING','ACTUAL')]
    if (REPORT/'emergency/FINAL_VALIDATION.json').exists():
        for x in ('PLANNING','ACTUAL'):
            compare('FINAL_B0_'+x,'FINAL_B0_'+x+'_FRESH','FINAL_'+x+'_FRESH_VERIFICATION.json')
            customers.append(verify_customers(x,'FINAL_B0_'))
    assert read(REPORT/'PLANNING_VOLTAGE_POLICY_SELECTION.json')['selected_policy'] is None
    table(REPORT/'TRIPLEX_PHASOR_IDENTITY_96.csv',identity)
    write(REPORT/'INDEPENDENT_VERIFICATION.json',dict(PASS=True,scope='saved-data/AC arithmetic and reproduction, not operating feasibility',
        stages=stages,customers=customers,
        final_B0_all96_physical_PASS=read(REPORT/'emergency/FINAL_VALIDATION.json')['B0_AC_physical_qualification_PASS'] if (REPORT/'emergency/FINAL_VALIDATION.json').exists() else False,
        independent_day=False,Native_calls=0))
    final=(REPORT/'emergency/FINAL_VALIDATION.json').exists() and read(REPORT/'emergency/FINAL_VALIDATION.json')['B0_AC_physical_qualification_PASS']
    print('independent verification PASS',len(stages),'cases; final B0 AC qualification',final,flush=True)


if __name__=='__main__':run()
