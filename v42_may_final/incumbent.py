"""Date-scoped Raw admission; FULL replay is the only incumbent authority."""
from pathlib import Path
import shutil
import numpy as np
from v42_pr134_b1.common import atomic, digest, record, sha


def binding(case, arm):
    from tools.u4_primal_alns.verify import matrix_sha, domain_sha
    # Numeric named domains include objective, RHS, bounds and types. Metadata
    # Case SHA may change when output paths change; that is not physical drift.
    return dict(day=case.bundle['day'],arm=arm,
        original_matrix_sha=matrix_sha(case.original_A),
        original_domain_sha=domain_sha(case.original_d),
        selected_matrix_sha=matrix_sha(case.A),selected_domain_sha=domain_sha(case.d),
        route_contract_sha=digest(dict(sites=list(case.graph[0]),initial=case.graph[1],
            arcs=[(a[:4],None if a[-1] is None else vars(a[-1])) for a in case.graph[2]],
            battery=vars(case.graph[3]))))


def moving(case, point):
    original=case.lift(point)
    return any(float(original[j])==1. and case.graph[2][int(str(n).split(',')[-1][:-1])][-1] is not None
        for j,n in enumerate(case.original_d['names']) if str(n).startswith('arc['))


def admit(case, records, folder, validator, arm):
    """Recheck unchanged bytes inside this output, rejecting another date/input."""
    expected=binding(case,arm);accepted=[];receipts=[]
    for ordinal,entry in enumerate(records):
        row=dict(origin=entry.get('origin'),admitted=False)
        try:
            if entry['binding']!=expected:raise ValueError('DATE_OR_NUMERIC_PHYSICAL_CONTRACT_MISMATCH')
            raw=entry['raw'];path=Path(raw['path'])
            if record(path)!=raw:raise ValueError('RAW_BYTES_DRIFT')
            owned=folder/f'INHERITED_{ordinal:03d}.npz'
            shutil.copyfile(path,owned)
            if sha(owned)!=raw['sha256']:raise ValueError('RAW_COPY_DRIFT')
            cert=validator(case,owned,{})
            with np.load(owned,allow_pickle=False) as z:point=z['point'].copy()
            replay=cert.get('original_matrix_and_96_slot_physical_replay',{})
            from v42_m1_research.check_ub import vector_sha
            if not (cert.get('PASS') is True
                    and cert.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is True
                    and replay.get('PASS') is True and replay.get('case_sha')==case.case_sha
                    and point.shape==(case.A.shape[1],) and np.isfinite(point).all()
                    and cert.get('point_vector_sha256')==vector_sha(point)):
                raise ValueError('CURRENT_ORIGINAL_FULL_REPLAY_REJECTED')
            atomic(owned.with_suffix('.REPLAY.json'),cert)
            accepted.append((point,cert));row.update(admitted=True,UB=cert['Global_UB'],raw=record(owned),
                case_sha=case.case_sha,MOVE=moving(case,point),unchanged_Raw=True)
        except (ValueError,KeyError,OSError) as exc:row['reason']=str(exc)
        receipts.append(row)
    atomic(folder/'CASE_INCUMBENT_ADMISSION.json',dict(binding=expected,records=receipts,
        Native_optimize_calls=0,cross_date_reuse=False))
    return accepted


class Bank:
    """Pool outcomes cannot increase the independently verified case-wide UB."""
    def __init__(self,case):
        self.case=case;self.best=None;self.best_moving=None;self.contract=None

    def offer(self,point,cert):
        from v42_m1_research.check_ub import vector_sha
        replay=cert.get('original_matrix_and_96_slot_physical_replay',{})
        if not (cert.get('PASS') is True and replay.get('PASS') is True
                and replay.get('case_sha')==self.case.case_sha
                and cert.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is True
                and cert.get('point_vector_sha256')==vector_sha(point)
                and cert.get('Global_UB')==float(self.case.d['objective']@point+float(self.case.d['constant']))):
            raise ValueError('CURRENT_RAW_FULL_CERTIFICATE_REQUIRED')
        item=(np.asarray(point).copy(),dict(cert))
        if self.best is None or cert['Global_UB']<self.best[1]['Global_UB']:self.best=item
        if moving(self.case,point) and (self.best_moving is None or cert['Global_UB']<self.best_moving[1]['Global_UB']):
            self.best_moving=item

    def fields(self):
        return dict(BEST_GLOBAL_UB=None if self.best is None else self.best[1]['Global_UB'],
            BEST_MOVING_FEASIBLE_UB=None if self.best_moving is None else self.best_moving[1]['Global_UB'])

    def save(self,folder,arm):
        if self.contract is None:self.contract=binding(self.case,arm)
        entries=[]
        for label,item in (('GLOBAL',self.best),('MOVING',self.best_moving)):
            if item is None:continue
            point,cert=item;path=folder/f'BEST_{label}_INCUMBENT.npz'
            np.savez_compressed(path,point=point)
            atomic(path.with_suffix('.REPLAY.json'),dict(cert,point_path=str(path),point_file_sha256=sha(path)))
            entries.append(dict(origin='CASE_FULL_BANK_'+label,binding=self.contract,raw=record(path)))
        atomic(folder/'VALIDATED_CASE_INCUMBENTS.json',entries)
        atomic(folder/'CASE_INCUMBENT_BANK.json',self.fields())
