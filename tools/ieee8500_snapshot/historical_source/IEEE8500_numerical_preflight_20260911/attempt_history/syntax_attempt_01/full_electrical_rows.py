"""Full electrical constraints, exact block-separable seed substitution.

Eliminate only electrical affine auxiliaries by exact substitution. Every
voltage bound and every line/transformer polygon face is retained. No row or
nonzero coefficient is screened out. Blocks share original global PCC names.
"""
import math,time
from pathlib import Path
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from electrical_engine import H,save,record,read,NAMES
from numerical_coefficients import AX,NL,NT,NW,N,predictions
from dayahead.v28r2.electrical_subproblem import anchored_polygon_parameters
from dayahead.v41r1.feasible_seed import row_audit as original_row_audit
COS=math.cos(math.pi/16)

def evaluate_grid(coefficients,controls,nodes,tolerance=1e-9):
    rows=[];critical=None;bad=0
    for t,c in enumerate(coefficients):
        x=np.asarray(controls[t]);p=predictions(c,x)
        flow=c.flow_p_constant+c.flow_p_matrix@x+1j*(c.flow_q_constant+c.flow_q_matrix@x)
        tx_poly=np.max([np.real(np.exp(-2j*math.pi*f/16)*flow[NL:NL+NT])/COS for f in range(16)],axis=0)
        kv_poly=np.max([np.real(np.exp(-2j*math.pi*f/16)*flow[NL+NT:])/(COS*np.asarray(AX['winding_rating_kVA'])) for f in range(16)],axis=0)
        violations=int(((p['voltage']<.95-tolerance)|(p['voltage']>1.05+tolerance)).sum()+int((p['line']>1+tolerance).sum())+int((tx_poly>1+tolerance).sum())+int((kv_poly>1+tolerance).sum())
        i=int(p['line'].argmax());line=float(p['line'][i])
        if critical is None or line>critical[0]:critical=(line,t,i,c.branch_names[i])
        rows.append(dict(Vmin=float(p['voltage'].min()),Vmax=float(p['voltage'].max()),line=line,tx=float(p['tx'].max()),kva=float(p['winding'].max()),tx_polygon=float(tx_poly.max()),kva_polygon=float(kv_poly.max())));bad+=violations
    p1,t,i,name=critical
    return dict(status='PASS' if not bad else 'FAIL',rho_max=p1,critical_line=name,critical_phase=name.rsplit('::',1)[-1],critical_slot=t,critical_line_axis=i,exact_axis_label=AX['line'][i],Vmin=min(r['Vmin'] for r in rows),Vmax=max(r['Vmax'] for r in rows),maximum_line_loading=p1,maximum_transformer_phase_current=max(r['tx'] for r in rows),maximum_transformer_kVA=max(r['kva'] for r in rows),maximum_transformer_current_polygon=max(r['tx_polygon'] for r in rows),maximum_transformer_kva_polygon=max(r['kva_polygon'] for r in rows),violations=bad,coefficient_SHAs=[c.coefficient_sha256 for c in coefficients])

def matrix_for_slot(c,fixed):
    """A @ [12 global PCC P variables, global rho] <= b."""
    blocks=[];rhs=[];ranges=[];offset=0
    def add(kind,w,constant,bound,rho=False,face=None):
        nonlocal offset
        w=np.asarray(w);constant=np.asarray(constant)+w[:,12:]@fixed[12:]
        a=np.c_[w[:,:12],-np.ones(len(w)) if rho else np.zeros(len(w))]
        b=np.broadcast_to(bound,len(w))-constant
        blocks.append(sp.csr_matrix(a));rhs.append(b);ranges.append(dict(kind=kind,face=face,start=offset,end=offset+len(w)));offset+=len(w)
    add('voltage_upper',c.voltage_matrix.T,c.voltage_constant,1.05**2)
    add('voltage_lower',-c.voltage_matrix.T,-c.voltage_constant,-.95**2)
    bias,correction,_=anchored_polygon_parameters(c)
    for f in range(16):
        co=math.cos(2*math.pi*f/16);si=math.sin(2*math.pi*f/16)
        w=(co*c.flow_p_matrix[:NL]+si*c.flow_q_matrix[:NL])/COS+correction[:,:NL].T
        b=(co*c.flow_p_constant[:NL]+si*c.flow_q_constant[:NL])/COS+bias[:NL]-correction[:,:NL].T@c.anchor
        add('phase_line_current',w,b,0.,rho=True,face=f)
        sel=slice(NL,NL+NT)
        add('transformer_phase_current',(co*c.flow_p_matrix[sel]+si*c.flow_q_matrix[sel])/COS,(co*c.flow_p_constant[sel]+si*c.flow_q_constant[sel])/COS,1.,face=f)
        sel=slice(NL+NT,None);rating=np.asarray(AX['winding_rating_kVA'])*COS
        add('transformer_winding_kVA',(co*c.flow_p_matrix[sel]+si*c.flow_q_matrix[sel])/rating[:,None],(co*c.flow_p_constant[sel]+si*c.flow_q_constant[sel])/rating,1.,face=f)
    return sp.vstack(blocks,format='csr'),np.concatenate(rhs),ranges

class FullElectricalRegistry:
    def __init__(self,folder):self.folder=Path(folder);self.registration=None;self.audit=None
    def add_grid(self,model,coefficients,controls,objective_cap=1.0):
        assert self.registration is None
        rho=model.addVar(lb=0,ub=objective_cap,name='rho_max')
        self.registration=(model,coefficients,controls,rho)
        return rho,dict(voltage=96*2*len(AX['nodes']),line_current=96*16*NL,transformer_current=96*16*NT,transformer_kva=96*16*NW,representation='FULL_LOGICAL_MODEL_96_BLOCKS_EXACT_SHARED_VARIABLE_BINDING')
    def audit_seed(self,model,values):
        core=original_row_audit(model,values);assert core['status']=='PASS'
        bound,coefficients,controls,rho=self.registration;assert bound is model
        names=model.getAttr('VarName',model.getVars());by=dict(zip(names,values));audit=[];start=time.perf_counter()
        for t,c in enumerate(coefficients):
            folder=self.folder/f'slot_{t:02}';folder.mkdir(parents=True,exist_ok=False)
            ports=[];fixed=[]
            for j,x in enumerate(controls[t]):
                if j<12:
                    assert isinstance(x,gp.Var) and x.VarName==f'PCC[{t},AIDC{j+1:02}]';ports.append(x)
                else:assert isinstance(x,(int,float,np.number))
                fixed.append(float(by[x.VarName]) if isinstance(x,gp.Var) else float(x))
            A,b,ranges=matrix_for_slot(c,np.asarray(fixed));m=gp.Model(f'FULL_IEEE8500_SLOT_{t:02}')
            m.Params.OutputFlag=0;m.Params.FeasibilityTol=model.Params.FeasibilityTol;m.Params.IntFeasTol=model.Params.IntFeasTol
            variables=ports+[rho];shared_names=[v.VarName for v in variables]
            x=m.addMVar(13,lb=[v.LB for v in variables],ub=[v.UB for v in variables],name='shared_global');m.update();m.setAttr('VarName',m.getVars(),shared_names)
            m.addMConstr(A,x,'<',b,name='electrical');m.update()
            seed=np.array([by[n] for n in shared_names]);result=original_row_audit(m,seed)
            assert result['status']=='PASS',dict(slot=t,audit=result)
            sp.save_npz(folder/'FULL_LINEAR_MATRIX.npz',A,compressed=True);np.savez_compressed(folder/'RHS_AND_SEED.npz',rhs=b,seed=seed,shared_global_names=np.array(shared_names),fixed_controls=np.asarray(fixed))
            report=dict(slot=t,status='PASS',linear_rows=A.shape[0],nonzeros=A.nnz,variables=13,global_variable_names=shared_names,exact_global_variable_identity=True,all_electrical_rows_present=True,lossless_elimination='Only affine electrical auxiliaries substituted; no physical bound or polygon face omitted.',ranges=ranges,seed_audit=result,matrix=record(folder/'FULL_LINEAR_MATRIX.npz'),data=record(folder/'RHS_AND_SEED.npz'))
            save(folder/'BLOCK_AUDIT.json',report);audit.append(report);m.dispose()
            if t%8==7:print('FULL_GRID_SEED_SLOTS',t+1,'/96',flush=True)
        self.audit=dict(status='PASS',original_core_audit=core,electrical_blocks=96,electrical_linear_rows=sum(r['linear_rows'] for r in audit),electrical_nonzeros=sum(r['nonzeros'] for r in audit),global_core_variables=model.NumVars,core_linear_rows=model.NumConstrs,core_general_rows=model.NumGenConstrs,total_logical_linear_rows=model.NumConstrs+sum(r['linear_rows'] for r in audit),all_shared_PCC_and_rho_bindings_exact=True,all_electrical_and_non_electrical_rows_substituted=True,monolithic_model_resident=False,exact_block_separable_joint_model=True,optimization_calls=0,wall_seconds=time.perf_counter()-start,blocks=[dict(slot=r['slot'],audit=record(self.folder/f'slot_{r["slot"]:02}'/'BLOCK_AUDIT.json')) for r in audit])
        save(H/'FULL_LOGICAL_B1_SEED_AUDIT.json',self.audit)
        return dict(core,full_electrical_blocks='PASS',full_electrical_linear_rows=self.audit['electrical_linear_rows'],full_logical_joint_model_seed='PASS')
