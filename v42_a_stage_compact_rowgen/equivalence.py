"""Check BOTH directions of the identical-continuous-lane sum projection."""
from collections import defaultdict
from fractions import Fraction
import numpy as np

def role(unit):return 'OPT' if unit['optional'] else 'HIST' if unit['stay_count'] else 'SINGLE'

def mapping(original_units,compact_units,original_columns):
    targets={role(u):u for u in compact_units};fold={};owners={}
    for u in original_units:
        r=role(u);v=targets[r]['v']
        for family,items in u['v'].items():
            for key,e in items.items():
                target=v[family][key]
                if e[0]=='v':pairs=((int(e[1]),int(target[1])),) if target[0]=='v' else ()
                elif e[0]=='e':
                    if target[0]!='e' or e[1]!=target[1] or len(e[2])!=len(target[2]) or not np.array_equal(e[3],target[3]):raise ValueError('NATIVE_EXPRESSION_PROJECTION_OBSTRUCTION')
                    pairs=zip(map(int,e[2]),map(int,target[2]))
                else:
                    if e!=target:raise ValueError('NATIVE_CONSTANT_PROJECTION_OBSTRUCTION')
                    pairs=()
                for j,t in pairs:
                    if j in fold and fold[j]!=t:raise ValueError('NONFUNCTIONAL_NATIVE_COLUMN_PROJECTION')
                    fold[j]=t;owners[j]=(r,u['id'])
    if set(fold)!=set(range(original_columns)):raise ValueError('UNOWNED_NATIVE_PRIMITIVE_COLUMN')
    return fold,owners

def verify(original,original_B,original_units,compact,compact_B,compact_units,N):
    fold,owners=mapping(original_units,compact_units,original.matrix.shape[1]);rows=[];coverage=defaultdict(set)
    ob=original_B.tocsc();cb=compact_B.tocsc()
    for j,t in fold.items():
        scale=N if owners[j][0]=='OPT' and N>1 else 1
        for source,target in ((original.lower[j],compact.lower[t]),(original.upper[j],compact.upper[t])):
            if abs(source)>=1e100 and abs(target)>=1e100:continue
            if Fraction(float(source))*scale!=Fraction(float(target)):raise ValueError('NATIVE_BOX_SUM_PROJECTION_OBSTRUCTION')
        ol,oh=ob.indptr[j:j+2];cl,ch=cb.indptr[t:t+2]
        if not np.array_equal(ob.indices[ol:oh],cb.indices[cl:ch]) or not np.array_equal(ob.data[ol:oh],cb.data[cl:ch]):raise ValueError('ORIGINAL_COUPLING_COEFFICIENT_LOSS')
    def signature(A,i,sense,rhs,transform):
        lo,hi=A.indptr[i:i+2];co=defaultdict(Fraction)
        for j,a in zip(A.indices[lo:hi],A.data[lo:hi]):
            target,scale=transform(int(j));co[target]+=Fraction(float(a))*scale
        return (str(sense),rhs if isinstance(rhs,Fraction) else Fraction(float(rhs)),tuple(sorted((j,a) for j,a in co.items() if a)))
    required=set();tautologies=0
    for i in range(original.matrix.shape[0]):
        lo,hi=original.matrix.indptr[i:i+2];js=original.matrix.indices[lo:hi]
        units={owners[int(j)] for j in js}
        if not units:
            b=original.rhs[i];sense=original.senses[i]
            if (sense=='=' and b==0) or (sense=='<' and b>=0) or (sense=='>' and b<=0):tautologies+=1;continue
            raise ValueError('INFEASIBLE_CONSTANT_NATIVE_ROW')
        lane=len(units)==1 and next(iter(units))[0]=='OPT' and N>1
        if lane:
            sig=signature(original.matrix,i,original.senses[i],Fraction(float(original.rhs[i]))*N,lambda j:(fold[j],Fraction(1)))
            coverage[sig].add(next(iter(units))[1])
        else:
            sig=signature(original.matrix,i,original.senses[i],original.rhs[i],lambda j:(fold[j],Fraction(1,N) if owners[j][0]=='OPT' and N>1 else Fraction(1)))
        required.add(sig)
    actual=set()
    for i in range(compact.matrix.shape[0]):
        lo,hi=compact.matrix.indptr[i:i+2]
        if lo==hi:
            b=compact.rhs[i];sense=compact.senses[i]
            if (sense=='=' and b==0) or (sense=='<' and b>=0) or (sense=='>' and b<=0):continue
        actual.add(signature(compact.matrix,i,compact.senses[i],compact.rhs[i],lambda j:(j,Fraction(1))))
    if required!=actual:raise ValueError('NATIVE_ROW_SUM_PROJECTION_OBSTRUCTION:'+str((len(required-actual),len(actual-required))))
    if any(len(us)!=N for us in coverage.values()):raise ValueError('NOT_EVERY_IDENTICAL_LANE_COVERS_EACH_ORIGINAL_ROW')
    return dict(PASS=True,original_rows=original.matrix.shape[0],original_cols=original.matrix.shape[1],
        compact_rows=compact.matrix.shape[0],compact_cols=compact.matrix.shape[1],unique_row_signatures=len(actual),
        checked_original_columns=len(fold),exact_coefficient_box_and_row_signature_checks=True,
        forward='sum identical original lanes, unchanged histogram; sum each lane inequality',
        inverse='split sum equally using exact rational 1/N, unchanged histogram; each original row and box checked',
        coupling_equivalence='original B = compact B times exact sum projection',constant_tautologies_not_constraints_deleted=tautologies)
