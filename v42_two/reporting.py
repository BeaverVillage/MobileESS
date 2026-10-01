"""Reserve reliability metrics for a fixed plan, never a selection objective."""
from v42_root.certify import dense_value

def reserve_metrics(m,dense):
    # Named upstream partition handles are only 1,152 cells, not a second solve.
    rows=[];total=0.;raw_cc=0.;raw_rt=0.
    for site,cap in m._two_caps.items():
        for t in range(24,120):
            get=lambda name: dense_value(m.getVarByName(name),dense)
            k=get(f'known[{site},{t}]');u=get(f'anonymous_GPU[{site},{t-24}]')
            tc=get(f'arrival_target_GPU[{site},{t-24}]');tr=get(f'risk[{site},{t}]')
            cc=get(f'CC4_reserve[{site},{t}]');rt=get(f'RT_reserve[{site},{t}]')
            xc=get(f'CC4_shortfall[{site},{t}]');xr=get(f'RT_shortfall[{site},{t}]')
            h=cap-k-u;minimum=max(0.,tc+tr-h);total+=minimum;raw_cc+=xc;raw_rt+=xr
            # A symmetric reporting allocation of available headroom. This is
            # conditional arithmetic after all intervention decisions; it does
            # not select or modify jobs, CC4 timing, power, or feasible domains.
            ratio=min(1.,max(0.,h)/(tc+tr)) if tc+tr>0 else 0.
            rows.append(dict(site=site,slot=t,known_GPU=k,anonymous_nominal_GPU=u,
                CC4_target=tc,Runtime_target=tr,headroom=h,
                minimum_total_shortfall_for_fixed_upstream=minimum,
                symmetric_CC4_shortfall=tc*(1-ratio),symmetric_Runtime_shortfall=tr*(1-ratio),
                solver_CC4_reserve=cc,solver_Runtime_reserve=rt,solver_CC4_shortfall=xc,solver_Runtime_shortfall=xr))
    return dict(total_minimum_shortfall_for_selected_upstream=total,
        symmetric_CC4_component=sum(r['symmetric_CC4_shortfall'] for r in rows),
        symmetric_Runtime_component=sum(r['symmetric_Runtime_shortfall'] for r in rows),
        raw_solver_total_shortfall=raw_cc+raw_rt,raw_solver_CC4_shortfall=raw_cc,raw_solver_Runtime_shortfall=raw_rt,
        optimized=False,component_split_scientific=False,
        note='Raw unoptimized auxiliaries may exceed minimum shortfall; conditional minimum and proportional split are reporting only, never an electrical certificate or a solution selection criterion',rows=rows)
