"""Certified, exact-stage Global Gap state and common termination contract.

Bounds are admitted only with current original-model evidence. Restricted
master/Joint objectives, heuristic scores and another stage's bounds cannot
enter this state. Optimization producers retain their existing algorithms.
"""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
from time import time

TERMINATIONS=frozenset(('GLOBAL_GAP_TARGET_MET','NATIVE_BUDGET_EXHAUSTED',
    'VALID_SEARCH_SPACE_EXHAUSTED','NO_FURTHER_CERTIFIED_IMPROVEMENT',
    'NO_FULL_FEASIBLE_SOLUTION','IMPLEMENTATION_OR_NUMERICAL_FAILURE'))
LOWER_ORIGINS=frozenset(('DW_FULL_PRICING','ORIGINAL_INTEGER_MILP','K16','K32','K48'))
SCOPE_KEYS=('source_sha','case_sha','day','arm','stage','matrix_sha','domain_sha','objective_sha')


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


class GlobalGapControl:
    def __init__(self, scope, target, output=None):
        if set(scope)!=set(SCOPE_KEYS) or any(not scope[k] for k in SCOPE_KEYS):
            raise ValueError('EXACT_ORIGINAL_STAGE_BOUND_SCOPE_REQUIRED')
        if not finite(target) or not 0<target<1:
            raise ValueError('POSITIVE_STAGE_GLOBAL_GAP_TARGET_REQUIRED')
        self.scope=deepcopy(scope);self.target=float(target)
        self.lower={};self.upper=None;self.history=[];self.operations=set()
        self.lower_probe_completed=False;self.failure=None;self.termination=None
        self.output=None if output is None else Path(output)
        self._trace=None
        if self.output is not None:
            self.output.mkdir(parents=True,exist_ok=True)
            # One operation owns this stream for its entire lifetime. Readers
            # cannot prevent a writer from reopening a certification log later.
            self._trace=os.open(self.output/'GLOBAL_GAP_TRACE.jsonl',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_APPEND)
        self.record('STAGE_GLOBAL_CONTROL_STARTED')

    def _proof(self,evidence):
        if (not isinstance(evidence,dict) or evidence.get('binding')!=self.scope
                or evidence.get('PASS') is not True):
            raise ValueError('CURRENT_SOURCE_CASE_MATRIX_DOMAIN_OBJECTIVE_EVIDENCE_REQUIRED')

    def offer_upper(self,value,evidence,**runtime):
        self._proof(evidence)
        if (not finite(value) or evidence.get('original_FULL_replayed') is not True
                or evidence.get('integer_point') is not True or not evidence.get('point_sha')):
            raise ValueError('CURRENT_ORIGINAL_FULL_INTEGER_UB_REQUIRED')
        before=self.upper['value'] if self.upper else None
        if before is None or value<before:
            self.upper=dict(value=float(value),evidence=deepcopy(evidence))
            self.record('FULL_UB_IMPROVED',UB_improvement=None if before is None else before-value,**runtime)
        return self.target_met()

    def offer_lower(self,value,origin,evidence,**runtime):
        self._proof(evidence)
        if not finite(value) or origin not in LOWER_ORIGINS:
            raise ValueError('CERTIFIED_GLOBAL_LOWER_BOUND_ORIGIN_REQUIRED')
        if origin=='DW_FULL_PRICING' and not (evidence.get('full_domain_pricing_complete') is True
                and evidence.get('phase_I_zero_certified') is True):
            raise ValueError('COMPLETE_DW_PRICING_AND_PHI_ZERO_REQUIRED')
        if origin=='ORIGINAL_INTEGER_MILP' and not (evidence.get('original_FULL_integer_model') is True
                and evidence.get('native_bound_valid') is True):
            raise ValueError('SAME_ORIGINAL_INTEGER_MILP_NATIVE_GLOBAL_BOUND_REQUIRED')
        if origin.startswith('K') and not (evidence.get('original_FULL_relaxation_proved') is True
                and evidence.get('native_bound_valid') is True and evidence.get('K')==int(origin[1:])):
            raise ValueError('CURRENT_K_RELAXATION_SOURCE_PROOF_REQUIRED')
        old=self.lower.get(origin)
        if old is None or value>old['value']:
            self.lower[origin]=dict(value=float(value),evidence=deepcopy(evidence))
            self.record('GLOBAL_LB_IMPROVED',origin=origin,LB_improvement=None if old is None else value-old['value'],**runtime)
        return self.target_met()

    def bounds(self):
        upper=None if self.upper is None else self.upper['value']
        values={origin:row['value'] for origin,row in self.lower.items()}
        lower=max(values.values(),default=None)
        consistent=upper is None or lower is None or lower<=upper
        gap=None
        if consistent and lower is not None and upper is not None:
            gap=(upper-lower)/max(abs(upper),1e-10)
        return dict(certified_LB_by_origin=values,Global_LB=lower if consistent else None,
            Global_UB=upper,Global_Gap=gap,Global_Gap_percent=None if gap is None else 100*gap,
            bound_consistency=consistent,FULL_feasible=upper is not None,
            global_gap_target=self.target,global_gap_certified=gap is not None and gap<=self.target,
            physical_execution_allowed=upper is not None)

    def target_met(self):
        return self.bounds()['global_gap_certified']

    def begin_operation(self,kind,mathematical_key):
        key=(kind,str(mathematical_key))
        if key in self.operations:
            self.record('DUPLICATE_MATHEMATICAL_OPERATION_REJECTED',operation=kind,mathematical_key=str(mathematical_key))
            return False
        self.operations.add(key)
        self.record('NEW_IMPROVEMENT_OPERATION',operation=kind,mathematical_key=str(mathematical_key))
        return True

    def record(self,event,**details):
        row=dict(event=event,iteration=len(self.history),binding=deepcopy(self.scope),
            epoch_seconds=time(),**self.bounds(),**details)
        self.history.append(row)
        if self._trace is not None:
            data=(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n').encode('utf8')
            view=memoryview(data)
            while view:
                written=os.write(self._trace,view)
                if written<=0:raise OSError('GLOBAL_BOUND_TRACE_APPEND_FAILED')
                view=view[written:]
            os.fsync(self._trace)
        return row

    def finish(self,reason,**details):
        if reason not in TERMINATIONS:raise ValueError('CANONICAL_STAGE_TERMINATION_REQUIRED')
        if self.target_met() and reason!='IMPLEMENTATION_OR_NUMERICAL_FAILURE':reason='GLOBAL_GAP_TARGET_MET'
        elif reason=='GLOBAL_GAP_TARGET_MET':raise ValueError('UNCERTIFIED_GAP_CANNOT_STOP_AS_TARGET_MET')
        self.termination=reason
        result=self.record('STAGE_TERMINATED',termination_reason=reason,**details)
        if self.output is not None:
            from .m_engine import _write
            _write(self.output/'GLOBAL_GAP_SUMMARY.json',result)
        return result

    def close(self):
        if self._trace is not None:
            os.close(self._trace);self._trace=None


def mess_scope(case):
    from .table_v_k48 import identity
    from .a_engine import digest
    source=identity(case)
    return dict(source_sha=source['source_sha'],case_sha=source['stage_case_sha'],
        day=source['day'],arm=source['arm'],stage=source['stage'],
        matrix_sha=source['matrix_sha'],domain_sha=source['domain_sha'],
        objective_sha=digest(dict(coefficients=list(map(float,case.original_d['objective'])),
            constant=float(case.original_d['constant']),sense=1)))


def mess_upper(control,case,bank,**runtime):
    from .m_engine import _certificate_matches
    if control.scope['case_sha']!=case.case_sha or control.scope['source_sha']!=case.identity.get('D0_source_sha'):
        raise ValueError('MESS_GLOBAL_CONTROL_STAGE_SCOPE_DRIFT')
    if bank.best is None:return False
    point,certificate=bank.best
    if not _certificate_matches(case,point,certificate):
        raise ValueError('MESS_GLOBAL_CONTROL_CURRENT_FULL_CERTIFICATE_REQUIRED')
    evidence=dict(PASS=True,binding=control.scope,original_FULL_replayed=True,integer_point=True,
        point_sha=certificate['point_vector_sha256'],original_FULL_certificate=deepcopy(certificate))
    return control.offer_upper(float(certificate['Global_UB']),evidence,**runtime)


def mess_lower(control,case,result,**runtime):
    from .table_v_k48 import identity
    if result.get('source')!=identity(case):
        raise ValueError('MESS_K_GLOBAL_BOUND_CURRENT_SOURCE_CASE_REQUIRED')
    if result.get('numerical_global_bound_contract') is not True:return False
    kind=result.get('K')
    if kind not in (16,32,48) or not result.get('certificate_sha'):
        raise ValueError('MESS_APPROVED_K16_K32_K48_PROOF_REQUIRED')
    evidence=dict(PASS=True,binding=control.scope,original_FULL_relaxation_proved=True,
        native_bound_valid=True,K=kind,certificate_sha=result['certificate_sha'],
        native_call=deepcopy(result.get('Native_call')))
    return control.offer_lower(float(result['Global_LB']),'K'+str(kind),evidence,**runtime)


def stage_native_seconds(budget,scope,*,stage=None):
    parent=getattr(budget,'parent',budget)
    parent._refresh()
    stage=scope['stage'] if stage is None else stage
    return sum(float(row['Native_Runtime']) for row in parent.document['calls']
        if row.get('solver')=='GUROBI' and row.get('Native_Runtime') is not None
        and all(row.get('stage_context',{}).get(k)==v for k,v in
            dict(day=scope['day'],arm=scope['arm'],stage=stage).items()))
