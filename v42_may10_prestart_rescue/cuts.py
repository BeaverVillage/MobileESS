"""Prestart relocation cuts proved from actual capacity and SHIFT rows."""
from dataclasses import replace
from fractions import Fraction
import math
import numpy as np
import scipy.sparse as sp
from .proofs import relocation_window_bound


def original_histograms(state, snapshot):
    jobs, classes = state['data'][1], state['data'][7]['classes']
    by_uid = {members[0]: (key,members) for key,members in classes.items()}
    cardinal_rows = {}
    A = snapshot.matrix
    for i in range(len(state['grows']), A.shape[0]):
        a,b = A.indptr[i:i+2]
        if snapshot.senses[i] == '=' and a != b and np.all(A.data[a:b] == 1):
            cardinal_rows[(tuple(A.indices[a:b]),float(snapshot.rhs[i]))] = i
    result = []
    pre = snapshot.objective('prestart_relocation').coefficients()
    shift = snapshot.objective('shift_magnitude').coefficients()
    for unit in state['reference_descriptor']['units']:
        if not unit.get('stay_count') or unit.get('optional') or unit['uid'] not in by_uid:
            continue
        key,members = by_uid[unit['uid']]
        entries = unit['v']['y']
        if any(e[0] != 'v' for e in entries.values()):
            continue
        columns = sorted(int(e[1]) for e in entries.values())
        if any(snapshot.vtypes[j] not in ('I','B') or snapshot.lower[j] < 0 for j in columns):
            continue
        row = cardinal_rows.get((tuple(columns),float(len(members))))
        expected = {(site,start) for start,site in state['domains'][unit['uid']].stays}
        if row is None or set(entries) != expected:
            continue
        job = jobs[unit['uid']]
        if any(jobs[uid].reference_site != job.reference_site or jobs[uid].reference_start != job.reference_start for uid in members):
            raise ValueError('HISTOGRAM_REFERENCE_OBJECTIVES_NOT_IDENTICAL')
        if any(pre.get(int(e[1]),Fraction()) != int(site != job.reference_site) for (site,start),e in entries.items()):
            raise ValueError('HISTOGRAM_PRESTART_COEFFICIENT_IDENTITY_FAILED')
        if any(shift.get(int(e[1]),Fraction()) != abs(start-job.reference_start) for (site,start),e in entries.items()):
            raise ValueError('HISTOGRAM_SHIFT_COEFFICIENT_IDENTITY_FAILED')
        result.append(dict(class_id=key,cardinality=len(members),reference_site=job.reference_site,
            reference_start=job.reference_start,entries={k:int(e[1]) for k,e in entries.items()},cardinality_row=row))
    return result


def window_cuts(state, snapshot, shift_budget=74):
    groups = original_histograms(state,snapshot)
    bysite = {}
    for g in groups:bysite.setdefault(g['reference_site'],[]).append(g)
    A = snapshot.matrix
    proposals, examined = {}, 0
    for (kind,site,t),row in state['axes'].items():
        if kind != 'GPU' or site not in bysite:
            continue
        a,b=A.indptr[row:row+2]
        raw=dict(zip(map(int,A.indices[a:b]),map(float,A.data[a:b])))
        signs=(1,-1) if snapshot.senses[row]=='=' else (1,) if snapshot.senses[row]=='<' else (-1,)
        for sign in signs:
            coefficients={j:Fraction(v)*sign for j,v in raw.items()}
            thresholds=sorted({coefficients.get(j,Fraction()) for g in bysite[site] for (s,start),j in g['entries'].items() if s==site and start==g['reference_start'] and coefficients.get(j,Fraction())>0})
            if len(thresholds)>3:
                thresholds=[thresholds[0],thresholds[len(thresholds)//2],thresholds[-1]]
            for threshold in thresholds:
                eligible=[]
                for g in bysite[site]:
                    j=g['entries'].get((site,g['reference_start']))
                    if j is not None and coefficients.get(j,Fraction())>=threshold:
                        eligible.append(g)
                selected={j for g in eligible for j in g['entries'].values()}
                others=[]
                for j,coefficient in coefficients.items():
                    if j in selected:continue
                    bound=snapshot.lower[j] if coefficient>=0 else snapshot.upper[j]
                    if not math.isfinite(bound) or abs(bound)>=1e100:break
                    others.append(coefficient*Fraction(float(bound)))
                else:
                    capacity=Fraction(float(snapshot.rhs[row]))*sign-sum(others,Fraction())
                    if capacity<0:continue
                    inputs=[];valid=True
                    for g in eligible:
                        reference,remote=[],[]
                        for (s,start),j in g['entries'].items():
                            resource=coefficients.get(j,Fraction())
                            if resource<0:valid=False;break
                            distance=abs(start-g['reference_start'])
                            if s==site:reference.append((distance,resource if resource>=threshold else 0))
                            else:remote.append(distance)
                        if not valid:break
                        inputs.append(dict(class_id=g['class_id'],cardinality=g['cardinality'],complete_domain=True,
                            reference_choices=reference,remote_choices=remote))
                    if not valid or not inputs:continue
                    proof=relocation_window_bound(inputs,capacity,shift_budget);examined+=1
                    if not proof['lower']:continue
                    cols=tuple(sorted(j for g in eligible for (s,start),j in g['entries'].items() if s!=site))
                    if not cols:continue
                    proof.update(original_capacity_row=int(row),row_sign=sign,site=site,time=int(t),threshold=str(threshold),
                        original_cardinality_rows=[g['cardinality_row'] for g in eligible],
                        outside_selected_groups_original_box_min=str(sum(others,Fraction())),
                        capacity_row_nonnegative_selected_terms_verified=True,
                        complete_original_reference_and_remote_choices_verified=True,
                        no_continuous_finish_lane_integerized=True)
                    if cols not in proposals or proof['lower']>proposals[cols]['proof']['lower']:
                        proposals[cols]=dict(columns=cols,lower=proof['lower'],proof=proof)
    # Fixed deterministic selection; no optimization or parameter sweep.
    chosen=sorted(proposals.values(),key=lambda p:(-p['lower'],len(p['columns']),p['columns']))[:32]
    return chosen,dict(histograms_independently_matched=len(groups),resource_window_thresholds_examined=examined,
        positive_inequalities=len(proposals),selected=len(chosen),native_optimization_calls=0)


def append_cuts(snapshot, cuts, mapping):
    rows,cols,data,rhs=[],[],[],[]
    for i,cut in enumerate(cuts):
        for j in cut['columns']:
            if mapping[j]>=0:rows.append(i);cols.append(int(mapping[j]));data.append(1.)
        rhs.append(float(cut['lower']))
    if not cuts:return snapshot
    extra=sp.csr_matrix((data,(rows,cols)),shape=(len(cuts),snapshot.matrix.shape[1]))
    return replace(snapshot,matrix=sp.vstack((snapshot.matrix,extra),format='csr'),
        senses=np.r_[snapshot.senses,[c.get('sense','>') for c in cuts]],rhs=np.r_[snapshot.rhs,rhs]).require()


def shift_cover_cuts(snapshot, shift_row, kept_columns):
    """Exact integer covers from the full, independently rebuilt SHIFT=74 row.

    For integer nonnegative coordinates with a_j>=d, d*sum(x_j)<=74.
    Therefore sum(x_j)<=floor(74/d). All other row terms remain nonnegative.
    This is a valid implication, including every original legal schedule.
    """
    A=snapshot.matrix;a,b=A.indptr[shift_row:shift_row+2]
    indices=A.indices[a:b];values=A.data[a:b]
    if snapshot.senses[shift_row]!='=' or snapshot.rhs[shift_row]!=74:
        raise ValueError('INDEPENDENT_ORIGINAL_SHIFT74_LOCK_REQUIRED')
    if np.any(values<0) or np.any(snapshot.lower[indices]<0):
        raise ValueError('NONNEGATIVE_FULL_SHIFT_ROW_REQUIRED')
    actual={int(j):Fraction(float(v)) for j,v in zip(indices,values) if v}
    if actual!=snapshot.objective('shift_magnitude').coefficients():
        raise ValueError('SHIFT_LOCK_ORIGINAL_OBJECTIVE_COEFFICIENT_DRIFT')
    retained=set(map(int,kept_columns));cuts=[]
    # Fixed before any native run; no post-result threshold sweep.
    for threshold in (2,3,4,5,8,16,25,38):
        columns=tuple(int(j) for j,v in zip(indices,values)
            if j in retained and v>=threshold and snapshot.vtypes[j] in ('I','B'))
        if not columns:continue
        cuts.append(dict(columns=columns,lower=74//threshold,sense='<',proof=dict(
            kind='ORIGINAL_SHIFT_INTEGER_COVER',original_shift_row=int(shift_row),
            threshold=threshold,rhs=74,upper=74//threshold,all_selected_variables_integer=True,
            all_original_shift_terms_nonnegative=True,all_selected_coefficients_ge_threshold=True,
            proof='d*sum(selected integer x)<=sum(original SHIFT terms)=74; floor(74/d)',
            original_feasible_integer_domain_preserved=True,new_global_LB_claimed=False)))
    return cuts
