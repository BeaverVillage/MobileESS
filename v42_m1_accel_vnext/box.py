"""Box-step dual guidance; artificial primal columns never enter the true RMP."""
import numpy as np
import gurobipy as gp

def initial_box(true, previous, active):
    # Include the current true optimal dual, so this first guidance LP has a
    # feasible optimal dual. Coordinate widths use only frozen checkpoint data.
    center=.1*np.asarray(true)+.9*np.asarray(previous)
    width=np.maximum(1.05*abs(np.asarray(true)-center),1e-8)
    return dict(center=center, width=width, active=np.asarray(active,dtype=int), serious_steps=0,null_steps=0)

def update(state,true,upper_before,upper_after):
    result={k:(v.copy() if isinstance(v,np.ndarray) else v) for k,v in state.items()}
    if upper_before-upper_after>=1e-5:
        result['center']=np.asarray(true).copy();result['serious_steps']+=1
    else:
        result['width']*=.5;result['null_steps']+=1
    return result

def install(master,state):
    m=master.model
    for i in state['active']:
        theta=float(state['center'][i]);delta=float(state['width'][i])
        m.addVar(lb=0,obj=theta+delta,name=f'box_plus[{i}]',column=gp.Column([1.],[master.coupling[i]]))
        m.addVar(lb=0,obj=-theta+delta,name=f'box_minus[{i}]',column=gp.Column([-1.],[master.coupling[i]]))
    m.update()
    return dict(artificial_columns=2*len(state['active']),coupling_axis_unchanged=True,
                original_pricing_domain_unchanged=True,scientific_certificate_eligible=False)
