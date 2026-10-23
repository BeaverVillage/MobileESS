"""Local fixed-state electrical responses, explicitly separate from Job/SOC witnesses."""
from pathlib import Path
import numpy as np
from .audit import DOC,read
from .correction import OUT,RUNTIME,EXT,CorrectedPhysical,put,csvout,priority

def main():
    priority();output=[];contributions=[];overlap=[]
    initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')['initial_sites']
    unit_for_site={site:unit for unit,site in initial.items()}
    for beta in EXT:
        folder=RUNTIME/'correction_time100'/f'TIME_{beta:.2f}_ACTUAL_B0'
        if not (folder/'RECEIPT.json').exists():continue
        from .correction_projection import project
        summary,rows,_,_=project(folder/'RECEIPT.json');t=int(summary['peak_slot'])+24
        e=CorrectedPhysical(f'LOCAL_FIXED_{beta:.2f}','ACTUAL','STATIC')
        state=read(folder/'STATES.json')[t];e.apply('ACTUAL',t,beta)
        base,a,_,_=e.measure('ACTUAL',t,beta,state=state,fixed=True,accounting=False)
        demands=dict(e.base_pcc);indices=np.where(e.canonical)[0]
        maxima={}
        for j in indices:
            r=e.line_axes[j];rho=float(a['line_rho'][j])
            if rho>maxima.get(r['element'],(-1,-1))[0]:maxima[r['element']]=(rho,j)
        top=[j for _,j in sorted(maxima.values(),reverse=True)[:20]];vectors={}
        for site in sorted(e.pccs):
            directions=[('P_PF095',-5.,-5.*np.tan(np.arccos(.95)))] if site.startswith('AIDC') else [('P',-5.,0.),('Q',0.,-5.)]
            for direction,dp,dq in directions:
                for s,(p,q) in demands.items():
                    e.d.Loads.Name(e.pccs[s]['element'].split('.',1)[1]);e.d.Loads.kW(p+(dp if s==site else 0));e.d.Loads.kvar(q+(dq if s==site else 0))
                point,b,_,_=e.measure('ACTUAL',t,beta,state=state,fixed=True,accounting=False)
                response=100*(a['line_rho'][top]-b['line_rho'][top]);vectors[site+'_'+direction]=response
                output.append(dict(beta_BG=beta,site=site,initial_MESS=unit_for_site.get(site),direction=direction,delta_P_kw=dp,delta_Q_kvar=dq,
                    eval_slot=t-24,baseline_fixed_snapshot_rho=base['rho_global'],controlled_fixed_snapshot_rho=point['rho_global'],
                    instantaneous_reduction_pp=100*(base['rho_global']-point['rho_global']),
                    original_TIME_global_rho=summary['rho_objective'],
                    full96_feasible_reduction_pp=None,full96_status='NOT_VERIFIED_LOCAL_RESPONSE_IS_NOT_A_SCHEDULE_WITNESS',
                    status='LOCAL_FIXED_STATE_ELECTRICAL_ONLY_NOT_AIDC_JOB_OR_MESS_SOC_WITNESS',
                    local_physics_PASS=point['physics_PASS'],line=point['binding_line'],phase=point['binding_physical_phase']))
                for rank,(j,delta) in enumerate(zip(top,response)):
                    contributions.append(dict(beta_BG=beta,site=site,direction=direction,rank=rank+1,line=e.line_axes[j]['element'],
                        phase=e.line_axes[j]['physical_phase'],delta_loading_pp=float(delta)))
        sta=[k for k in vectors if k.startswith('STA') and k.endswith('_P')]
        for i,key in enumerate(sta):
            for other in sta[i+1:]:
                x,y=vectors[key],vectors[other]
                overlap.append(dict(beta_BG=beta,STA1=key,STA2=other,
                    both_in_initial_MESS8=key[:-2] in unit_for_site and other[:-2] in unit_for_site,
                    top20_response_cosine=float(np.dot(x,y)/(np.linalg.norm(x)*np.linalg.norm(y))),
                    interpretation='Electrical response overlap, not independent additive energy or optimization potential'))
        csvout('EXTENDED_BETA_GLOBAL_SENSITIVITY.csv',output);csvout('EXTENDED_BETA_TOP20_PCC_RESPONSE.csv',contributions)
        csvout('MESS8_ELECTRICAL_RESPONSE_OVERLAP.csv',overlap)
        print('LOCAL ELECTRICAL',beta,flush=True)

if __name__=='__main__':main()
