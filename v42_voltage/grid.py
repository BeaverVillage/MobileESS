"""Fixed-AIDC Planning grid and independent numeric grid certificate."""
import math,re
import numpy as np
from v42_root.common import *
from v42_temporal.native import load_power
from v42_may01.prepare import native_coefficients
from v42_native.grid import GridAuthority,add_grid
from v42_native.voltage import *
from v42_native.contracts import require
from v42_boundary.common import OLD


def coefficients(bundle):
    cert,_,_,_=load_power(bundle)
    return cert,native_coefficients(cert)


def frozen_grid(model,bundle,anchor,p,q):
    cert,coeff=coefficients(bundle)
    require(anchor['voltage_authority_sha256']==authority_sha(),'M1_VOLTAGE_ANCHOR_DRIFT')
    controls=[]
    for t,c in enumerate(coeff):
        require(list(c.control_names)==anchor['control_names'],'AIDC_CONTROL_AXIS_DRIFT')
        row=[]
        for i,name in enumerate(c.control_names):
            s=name.split('[')[1][:-1]
            if name.startswith('aidc_load_kw'):row.append(float(anchor['controls'][t][i]))
            elif name.startswith('mess_p_kw'):row.append(p[s,t])
            elif name.startswith('mess_q_kvar'):row.append(q[s,t])
            else:raise ValueError('UNRECOGNIZED_FROZEN_CONTROL:'+name)
        controls.append(row)
    ga=GridAuthority(sha(Path(cert['input_identity']['identity']['inputs']['OpenDSS_master']['path'])),
                     digest(bundle['capacities']),sha(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),
                     digest(bundle['battery']),PLANNING_LOWER_SQUARED,PLANNING_UPPER_SQUARED,True,stage=Stage.M1,
                     transformer_current_authority_sha256=getattr(coeff[0],'transformer_current_authority_sha256',None))
    rho=add_grid(model,coeff,controls,ga)
    # Legacy constructor interface only. No AIDC/CC4 variable or reserve objective.
    return [('rho',rho),('reserve_shortfall',0.)],controls


def grid_report(bundle,controls,rho,tolerance=1e-5):
    _,coeff=coefficients(bundle);minimum=float('inf');maximum=-float('inf')
    lower_near=upper_near=lower_active=upper_active=0;grid_vio=0.;line_vio=tx_current_vio=tx_kva_vio=0.
    angles=2*np.pi*np.arange(16)/16;cos=np.cos(angles);sin=np.sin(angles)
    for c,x in zip(coeff,controls):
        from v42_thermal.planning import require_coefficient
        require_coefficient(c)
        x=np.asarray(x,dtype=float);volt=c.voltage_constant+c.voltage_matrix.T@x
        minimum=min(minimum,float(volt.min()));maximum=max(maximum,float(volt.max()))
        lo=volt-PLANNING_LOWER_SQUARED;hi=PLANNING_UPPER_SQUARED-volt
        lower_active+=int(np.count_nonzero(abs(lo)<=1e-6));upper_active+=int(np.count_nonzero(abs(hi)<=1e-6))
        lower_near+=int(np.count_nonzero(lo<=1e-4));upper_near+=int(np.count_nonzero(hi<=1e-4))
        grid_vio=max(grid_vio,float(-lo.min()),float(-hi.min()))
        p=c.flow_p_constant+c.flow_p_matrix@x;q=c.flow_q_constant+c.flow_q_matrix@x
        ap=np.asarray(c.branch_limits)*math.cos(math.pi/16)
        pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
        raw=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];active=np.argmax(raw,axis=1)
        grad=(cos[active,None]*c.flow_p_matrix+sin[active,None]*c.flow_q_matrix)/ap[:,None]
        correction=c.current_matrix.T-grad;bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
        for k,name in enumerate(c.branch_names):
            faces=cos*p[k]+sin*q[k]
            if re.fullmatch(r'transformer\.mess_(?:idc|sta)\d{2}_tx::[abc]',name.lower()) is None:
                if name.lower().startswith('transformer.'):
                    tx_current_vio=max(tx_current_vio,float(c.current_constant[k]+c.current_matrix[:,k]@x-1))
                else:line_vio=max(line_vio,float(np.max(faces/ap[k]+correction[k]@(x-c.anchor)+bias[k])-rho))
            rating=c.transformer_ratings[k]
            if rating is not None:tx_kva_vio=max(tx_kva_vio,float(np.max(faces)-rating*math.cos(math.pi/16)))
    require(len(controls)==len(coeff),'GRID_CERTIFICATE_HORIZON')
    from v42_thermal.authority import current_identity
    return dict(PASS=max(grid_vio,line_vio,tx_current_vio,tx_kva_vio)<=tolerance,**current_identity(),
                voltage_authority_sha256=authority_sha(),min_voltage_pu=math.sqrt(max(0,minimum)),
                max_voltage_pu=math.sqrt(max(0,maximum)),lower_active=lower_active,upper_active=upper_active,
                lower_near_binding=lower_near,upper_near_binding=upper_near,active_tolerance_squared=1e-6,
                near_binding_tolerance_squared=1e-4,voltage_rows=sum(2*len(c.voltage_constant) for c in coeff),
                voltage_max_violation=max(0,grid_vio),line_max_violation=max(0,line_vio),
                transformer_current_max_violation=max(0,tx_current_vio),transformer_kVA_max_violation=max(0,tx_kva_vio),
                Fresh_AC=False,voltage_fallback=False)
