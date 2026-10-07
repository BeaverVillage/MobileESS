"""Exact temporary native-oracle subsets; the scientific pool is unchanged."""
from dataclasses import replace
import numpy as np
import scipy.sparse as sp

def migration_query(cache, cardinality, kind):
    if kind not in ('STAY','MIGRATION'):raise ValueError('QUERY_KIND')
    coefficients={};constant=0.
    for unit in cache['units']:
        for e in unit['v'].get('q',{}).values():
            if e[0]=='v':coefficients[int(e[1])]=coefficients.get(int(e[1]),0.)+1.
            elif e[0]=='e':
                constant+=float(e[1])
                for j,a in zip(e[2],e[3]):coefficients[int(j)]=coefficients.get(int(j),0.)+float(a)
            else:constant+=float(e[1])
    target=cardinality if kind=='MIGRATION' else 0
    if not coefficients and target!=constant:raise ValueError('NO_MIGRATION_NATIVE_SUPPORT')
    original=cache['snapshot'];n=original.matrix.shape[1]
    row=sp.csr_matrix(([a for j,a in sorted(coefficients.items())],([0]*len(coefficients),[j for j,a in sorted(coefficients.items())])),shape=(1,n))
    return replace(original,matrix=sp.vstack((original.matrix,row),format='csr'),
        senses=np.concatenate((original.senses,np.asarray(['=']))),rhs=np.r_[original.rhs,float(target)-constant]).require()

def select(candidates, migration_completed):
    if not migration_completed:raise PermissionError('TARGETED_MIGRATION_SEARCH_MUST_COMPLETE_BEFORE_SELECTION')
    unique={}
    order=lambda c:(-c['residual_score'],c['price'],c['identity'])
    for c in sorted(candidates,key=order):unique.setdefault((c['class_id'],c['coefficient_sha256']),c)
    migration=sorted((c for c in unique.values() if c['kind']=='MIGRATION'),key=order)
    stay=sorted((c for c in unique.values() if c['kind']=='STAY'),key=order)
    chosen_migration=migration[:32]
    stay_limit=32 if len(migration)>len(chosen_migration) else 64-len(chosen_migration)
    return sorted(chosen_migration+stay[:stay_limit],key=order)
