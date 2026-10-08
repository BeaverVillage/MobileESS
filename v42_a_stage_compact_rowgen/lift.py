"""Independent lift to every original primitive expanded scientific column."""
from fractions import Fraction
import numpy as np
from .equivalence import mapping

def expanded_point(state,point):
    target=np.zeros(state['reference'].matrix.shape[1]);target[:state['n']]=point[:state['n']]
    for meta in state['metas'].values():
        z=point[meta['offset']:meta['offset']+meta['kernel_columns']].copy()
        for j,p in zip(meta.get('compact_path_columns',()),meta['points']):
            # Per-job p/N is exactly binary64 by the coefficient gate. This
            # floating evaluation is independent of the exact rational proof.
            perjob=np.asarray([float(Fraction(float(v))/meta['N']) for v in p])
            z+=point[meta['offset']+j]*perjob
        fold,owners=mapping(meta['reference_units'],meta['units'],len(meta['reference_columns']))
        for j,t in fold.items():target[meta['reference_columns'][j]]=z[t]/(meta['N'] if owners[j][0]=='OPT' and meta['N']>1 else 1)
    return target

def full_artificial_point(fullmaster,master,rows,point,original_columns):
    full=np.zeros(fullmaster.snapshot.matrix.shape[1]);full[:original_columns]=point[:original_columns]
    locations={};count={}
    for j,r in enumerate(fullmaster.artificial_rows):
        k=count.get(r,0);locations[r,k]=j;count[r]=k+1
    count={}
    for j,r in enumerate(master.artificial_rows):
        source=rows[r];k=count.get(source,0);count[source]=k+1
        full[original_columns+locations[source,k]]=point[original_columns+j]
    return full
