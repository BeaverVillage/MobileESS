"""Initial rows only; no caps, bounds, tolerance or separation changes."""
import numpy as np

def select_seed(loading,branch_names,asset_count=32):
    loading=np.asarray(loading);names=list(map(str,branch_names))
    assert loading.shape==(96,len(names))
    groups={}
    for j,name in enumerate(names):
        if name.lower().startswith('line.'):
            groups.setdefault(name.split('::')[0].lower(),[]).append(j)
    ranked=sorted(groups,key=lambda name:(-float(loading[:,groups[name]].max()),name))
    selected=ranked[:asset_count];states=set()
    # Cover multiple distinct native assets rather than many observations of
    # the same locally controllable bottleneck. Keep the two peak slots of
    # every phase/terminal for each selected asset.
    for name in selected:
        for j in groups[name]:
            for t in np.argsort(-loading[:,j],kind='stable')[:2]:states.add((int(t),j))
    line_indices=sorted(j for js in groups.values() for j in js)
    for t in range(96):states.add((t,line_indices[int(np.argmax(loading[t,line_indices]))]))
    return states,{'source':'CURRENT_LAYOUT_96_SLOT_B0_PLANNING_LOADING','asset_count':len(selected),'assets':selected,'initial_state_count':len(states),'only_initial_rows_changed':True,'final_active_set_cap':None,'hardcoded_rho_floor':False,'full_separation_unchanged':True}
