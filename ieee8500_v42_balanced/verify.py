"""Independent arithmetic over full saved axes and lossless original customer IDs."""
import itertools
import math
import numpy as np
from .common import *


def direction_verify():
    spec=read(PR193/'joint_selection_v3/score_selection/GEOMETRY_PREREGISTRATION.json')
    fit=read(PR193/'joint_selection_v3/score_selection/GEOMETRY_RESULT.json')['proper_common_transform']
    assert fit['u']**2+fit['v']**2>0
    assert abs(math.hypot(fit['u'],fit['v'])-spec['uniform_scale'])<1e-15
    tol=spec['axis_zero_tolerance_km']; near=spec['near_pair_tolerance_km']
    mapping=rows(MAPPING); records=[]
    for r in mapping:
        x=float(r['source_or_proxy_x']);y=float(r['source_or_proxy_y'])
        tx=fit['u']*x-fit['v']*y+fit['translation_x'];ty=fit['v']*x+fit['u']*y+fit['translation_y']
        assert max(abs(tx-float(r['common_frame_x_km'])),abs(ty-float(r['common_frame_y_km'])))<1e-9
    for a,b in itertools.combinations(mapping,2):
        dx=float(b['traffic_x_km'])-float(a['traffic_x_km']);dy=float(b['traffic_y_km'])-float(a['traffic_y_km'])
        for axis,delta in enumerate((dx,dy)):
            expected=0 if math.hypot(dx,dy)<=near or abs(delta)<=tol else (1 if delta>0 else -1)
            common='common_frame_'+('x' if axis==0 else 'y')+'_km'
            actual_delta=float(b[common])-float(a[common]); actual=1 if actual_delta>0 else -1 if actual_delta<0 else 0
            records.append(dict(site_a=a['location_id'],site_b=b['location_id'],axis='XY'[axis],traffic_delta_km=delta,
                mapped_delta_layout_km=actual_delta,expected_sign=expected,actual_sign=actual,PASS=not expected or expected==actual,
                coordinate_authority='source layout / LV upstream proxy, field geography UNVERIFIED'))
    assert len(records)==552 and all(r['PASS'] for r in records)
    table(REPORT/'DIRECTION_552_AXIS_VERIFICATION.csv',records)
    return dict(PASS_assumed_proxy=True,pairs=276,axes=552,axis_tolerance_km=tol,near_tolerance_km=near,
        common_transform=fit,field_geography_certified=False,locations_changed=0)


def verify():
    customers=read(REPORT/'BALANCED_CUSTOMER_RECORDS.json'); old_customers=read(REPORT/'UNBALANCED_CUSTOMER_RECORDS.json')
    old_index={r['name']:i for i,r in enumerate(old_customers)}
    pair=np.array([[old_index[r['name']+'a'],old_index[r['name']+'b']] for r in customers])
    records=[]
    for source in ('PLANNING','ACTUAL'):
        data=dict(np.load(DATA/'derived'/f'{source}_INPUTS.npz'))
        old_path=OLD/'ac'/('FINAL_B0_'+source)
        old_pq=dict(np.load(old_path/'CUSTOMER_PV_PQ_96.npz'))
        for fresh in (False,True):
            folder=REPORT/'ac'/('BALANCED_'+source+('_FRESH' if fresh else ''))
            z=dict(np.load(folder/'AC_96.npz')); axes=read(folder/'AC_AXES.json'); pq=dict(np.load(folder/'CUSTOMER_PV_PQ_96.npz'))
            previous_axes=read(old_path/'AC_AXES.json')
            for key in ('lines','nodes','transformers','winding_axes','objective_mask'):assert axes[key]==previous_axes[key]
            assert len(axes['nodes'])==8531
            assert len({r['element'] for r in axes['lines']})==3703
            assert len({r['element'] for r in axes['lines'] if r['group']=='Triplex'})==1177
            assert len({r['element'] for r in axes['transformers']})==1190
            ratings=np.array([r['normal_amps'] for r in axes['lines']]); thermal_error=float(np.abs(z['line_rho']-z['line_amps']/ratings).max())
            txratings=np.array([r['normal_amps'] for r in axes['transformers']])
            assert np.abs(z['transformer_current_rho']-z['transformer_amps']/txratings).max()<1e-14
            assert thermal_error<1e-14
            old_expected=old_pq['original_nominal'][:,pair,:].sum(2)
            # The sum axis is the two original legs, not the P/Q axis.
            expected_error=float(np.abs(old_expected-pq['original_nominal']).max())
            assert expected_error<1e-10
            leg_error=float(np.abs(pq['actual_legs']-pq['original_nominal'][:,:,None,:]/2).max())
            actual_customer_error=float(np.abs(pq['actual_customer']-pq['actual_legs'].sum(2)).max())
            assert leg_error<1e-5 and actual_customer_error<1e-9
            pcc=np.zeros((96,24,2));pcc[:,:12,0]=data['PCC_P_kw'];pcc[:,:12,1]=data['PCC_Q_kvar']
            assert np.abs(pq['actual_PCC']-pcc).max()<1e-5
            capacity=np.array([r['kw'] for r in old_customers])*float(read(DATA/'historical/SCREENING_RULE_PR62.json')['PV_ratio'])
            nominal_pv=data['pv_factor'][:,None]*capacity[None,:]
            # Same old Generator node, model1, .120 kV and .88/1.05 limits;
            # actual voltage-dependent output is allowed, installed power is invariant.
            node_index={n:i for i,n in enumerate(axes['nodes'])}
            vpu=np.column_stack([z['node_voltage_pu'][:,node_index[r['buses'][0]]] for r in old_customers])*.208/math.sqrt(3)/.120
            factor=np.where(vpu<.88,(vpu/.88)**2,np.where(vpu>1.05,(vpu/1.05)**2,1.))
            pv_expected=nominal_pv*factor
            pv_error=float(np.abs(pq['actual_PV'][:,:,0]-pv_expected).max())
            assert pv_error<1e-5 and np.abs(pq['actual_PV'][:,:,1]).max()<1e-5
            with np.load(folder/'PHASOR_FORENSICS.npz') as ph:
                ni=ph['node_indices'];li=ph['line_indices']; node_volt={axes['nodes'][i]:ph['node_complex_V'][:,j] for j,i in enumerate(ni)}
                lines=read(PR193/'ORIGINAL_FEEDER_INVENTORY.json')['lines'];bus_by_element={r['element']:r['buses'] for r in lines}
                inferred=[]
                for j,i in enumerate(li):
                    r=axes['lines'][i];base=bus_by_element[r['element']][r['terminal']-1].split('.')[0].lower()
                    voltage=np.zeros(96,dtype=complex) if r['node']==0 else node_volt[base+'.'+str(r['node'])]
                    inferred.append(voltage*np.conj(ph['line_complex_A'][:,j])/1000-ph['line_complex_kVA'][:,j])
                phasor_error=float(np.abs(inferred).max());assert phasor_error<1e-8
            slots=rows(folder/'SLOTS.csv');mask=np.array(axes['objective_mask'])
            canonical=z['line_rho'][:,mask].max(1)
            assert np.abs(canonical-np.array([float(r['rho_max']) for r in slots])).max()<1e-14
            violations=int(((z['node_voltage_pu']<.95)|(z['node_voltage_pu']>1.05)).sum())
            violations+=int((z['line_rho']>1).sum()+(z['transformer_current_rho']>1).sum()+(z['transformer_winding_nameplate_kva_rho']>1).sum())
            controls=rows(folder/'CONTROL_STATES_96.csv')
            assert all(float(r['Vreg'])==123.5 for r in controls if r['kind']=='RegControl')
            assert all(r['states']=='[0]' and r['enabled']=='True' for r in controls if r['kind']=='Capacitor' and r['name']=='capbank3')
            records.append(dict(source=source,fresh=fresh,source_master='Master.dss',original_axis_identity=True,
                thermal_rho_error=thermal_error,customer_PQ_input_error=expected_error,customer_leg_split_error=leg_error,
                customer_total_readback_error=actual_customer_error,PV_characteristic_error=pv_error,
                full_PCC_readback_error=float(np.abs(pq['actual_PCC']-pcc).max()),
                phasor_S_VI_error=phasor_error,power_balance_error=float(np.abs(pq['balance_PQ']).max()),
                all_full_axis_violations=violations,P5_overlay_SHA=sha(REPORT/'overlays/P5.dss'),PASS=violations==0))
    geometry=direction_verify()
    write(REPORT/'INDEPENDENT_VERIFICATION.json',dict(PASS=all(r['PASS'] for r in records),cases=records,geometry=geometry,
        input_conservation_against_committed_P5=True,saved_array_verifier_independent_of_summary=True,
        unseen_day=False,Native_calls=0))
    print('independent all-axis/customer/PV/phasor verification PASS',flush=True)


if __name__=='__main__':verify()
