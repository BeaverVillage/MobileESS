"""Read-only baseline violation screen of authority-derived folded facets."""
import json
from analyze_point import context
from pure_lp import OUT,write

def main():
    c=context();h=json.loads((OUT/'FOLDED_PCS_LOCAL_HULL.json').read_text());out=[];v=c['value']
    for p in h['facets']:
        if not p['strengthening_candidate']:continue
        vals=[]
        for name in c['d']['names']:
            if not str(name).startswith('Pch['):continue
            u,s,k=str(name)[4:-1].split(',');k=int(k);arc=c['sites'].index(s)*96+k
            r=p['alpha']*(v(str(name))+v(f'Pdis[{u},{s},{k}]'))+p['beta']*v(f'Q[{u},{s},{k}]')-p['gamma']*v(f'arc[{u},{arc}]')
            vals.append(r)
        out.append(dict(facet=p['id'],alpha=p['alpha'],beta=p['beta'],gamma=p['gamma'],count=len(vals),violated=sum(r>1e-8 for r in vals),max_violation=max(vals)))
    write('FOLDED_BASELINE_VIOLATION_SUMMARY.json',out);print(out,flush=True)

if __name__=='__main__':main()
