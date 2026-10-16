"""Conservative certified-prefix reuse; full independent Fresh stays separate.

This first step does not claim a complete DSS engine-state clone. Every
candidate still runs the original chronological SolveSnap sequence, but an
identical, previously verified historical slot is not measured/inventoried
again. Current candidate measurements and inventory checks are never skipped.
"""
from copy import deepcopy
import ast
import inspect
import textwrap

import numpy as np

from v43.common import record
from v43_actual.current_ac import OriginalCurrentAC
from v43_actual.vendor.policy import digest
from v43_arms.current_ac import ArmCurrentAC


def probe_function(*,reuse):
    source=textwrap.dedent(inspect.getsource(OriginalCurrentAC._probe))
    original='source=authority.source()'
    if source.count(original)!=1:raise ValueError('AC_SOURCE_REUSE_BOUNDARY_DRIFT')
    source=source.replace(original,'source=self._instrumented_source(authority.source())')
    compile_line='odd,adapter,initial=authority.compile_verified()'
    source=source.replace(compile_line,compile_line+'\n    self.performance["engine_compiles"]+=1')
    loop='for slot,row in enumerate(rows):'
    source=source.replace(loop,loop+'\n                self.performance["slot_replays"]+=1\n'
        '                self.performance["past_slot_replays"]+=int(slot<len(rows)-1)\n'
        '                cached=None\n')
    boundary=next(line for line in source.splitlines(keepends=True)
        if "authority.assert_inventory(source['inventory'](odd))" in line)
    if source.count(boundary)!=2:raise ValueError('AC_INVENTORY_REUSE_BOUNDARY_DRIFT')
    indent=boundary[:len(boundary)-len(boundary.lstrip())]
    source=source.replace(boundary,indent+'self._apply_frozen_mess(odd,row)\n'+boundary,1)
    if reuse:
        source=source.replace('cached=None', 'cached=self._historical_cache.get(keys[slot]) if slot<len(rows)-1 else None')
        source=source.replace('backgrounds=[]','keys=self._keys_for_probe(rows)\n    backgrounds=[]')
        source=source.replace(boundary,indent+'if cached is None:\n    '+boundary)
        before='voltage=np.array(source[\'voltage_vector\'](odd,names))'
        source=source.replace(before,
            'if cached is not None:\n'
            '                    self._reuse_verified_history(odd,source,cached,converged)\n'
            '                    steps.append(cached)\n'
            '                    continue\n'
            '                '+before)
    old='checked_nodes=len(names),checked_branch_phases=len(branches)))'
    if source.count(old)!=1:raise ValueError('AC_MEASUREMENT_REUSE_BOUNDARY_DRIFT')
    source=source.replace(old,
        'checked_nodes=len(names),checked_branch_phases=len(branches),\n'
        '                        native_state=self._native_state(source["native_state"](odd)),\n'
        '                        voltage_vector_pu=voltage.tolist() if self.detailed else None,\n'
        '                        voltage_node_names=list(names) if self.detailed else None,\n'
        '                        branch_measurement_rows=self._measurements(measured) if self.detailed else None,\n'
        '                        maximum_line_phase=str(branches[np.flatnonzero(lines)[np.argmax(measured[lines,1])]].branch_id),\n'
        '                        maximum_line_phase_letter=str(branches[np.flatnonzero(lines)[np.argmax(measured[lines,1])]].phase),\n'
        '                        MESS_plan_sha=self.mess_sha))')
    if reuse:
        source=source.replace('if not converged:\n',
            'if slot<len(rows)-1:\n'
            '                    self._historical_cache[keys[slot]]=deepcopy(steps[-1])\n'
            '                if not converged:\n')
    ns=dict(OriginalCurrentAC._probe.__globals__,deepcopy=deepcopy)
    exec(compile(source,__file__,'exec'),ns)
    return ns['_probe']


class FullPrefixReferenceAC(ArmCurrentAC):
    """Independent exact original operations plus read-only detailed receipts."""
    _probe=probe_function(reuse=False)

    def __init__(self,*args,detailed=False,**kwargs):
        super().__init__(*args,**kwargs)
        self.detailed=detailed
        self.performance=dict(engine_compiles=0,slot_replays=0,past_slot_replays=0,
            branch_measurement_calls=0,inventory_calls=0,verified_history_reuses=0)

    def _instrumented_source(self,source):
        source=dict(source)
        for key,counter in [('branch_measurement','branch_measurement_calls'),('inventory','inventory_calls')]:
            original=source[key]
            def wrapped(*args,_original=original,_counter=counter,**kwargs):
                self.performance[_counter]+=1
                return _original(*args,**kwargs)
            source[key]=wrapped
        return source

    @staticmethod
    def _native_state(state):
        return dict(taps=np.asarray(state[0]).tolist(),caps=np.asarray(state[1]).tolist())

    @staticmethod
    def _measurements(rows):
        return [[float(v) if np.isfinite(v) else None for v in row] for row in rows]

    def full_fresh_probe(self,rows):
        # Explicitly execute the unoptimized original full measurement path.
        return FullPrefixReferenceAC._probe(self,rows)


class CertifiedPrefixAC(FullPrefixReferenceAC):
    """Skip only exactly bound, already verified historical measurements."""
    _probe=probe_function(reuse=True)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._historical_cache={};self._observed_hashes=[];self._observed_keys=[]
        self._authority=digest(dict(power=self.model.authority_sha,MESS=self.mess_sha,
            original=[record(inspect.getfile(OriginalCurrentAC)),record(inspect.getfile(ArmCurrentAC))],
            optimized=record(__file__),contract='ORIGINAL_7REG_STATIC_SEQUENTIAL_NO_TAP_SETTERS'))

    def observe(self,now,history):
        super().observe(now,history)
        hashes=[digest(row) for row in history]
        if hashes[:len(self._observed_hashes)]!=self._observed_hashes:
            raise ValueError('CERTIFIED_OBSERVED_PREFIX_MUTATED')
        chain=self._observed_keys[-1] if self._observed_keys else self._authority
        for value in hashes[len(self._observed_hashes):]:
            chain=digest([chain,value]);self._observed_keys.append(chain)
        self._observed_hashes=hashes

    def _keys_for_probe(self,rows):
        if (len(rows)==len(self.history)+1 and
                all(a is b for a,b in zip(rows[:-1],self.history))):
            chain=self._observed_keys[-1] if self._observed_keys else self._authority
            return self._observed_keys+[digest([chain,digest(rows[-1])])]
        keys=[];chain=self._authority
        for row in rows:
            chain=digest([chain,digest(row)]);keys.append(chain)
        return keys

    def _reuse_verified_history(self,odd,source,cached,converged):
        if not converged or not cached['converged']:
            raise ValueError('CACHED_HISTORY_CONTROL_CONVERGENCE_DRIFT')
        if self._native_state(source['native_state'](odd))!=cached['native_state']:
            raise ValueError('CACHED_HISTORY_TAP_OR_CAP_STATE_DRIFT')
        self.performance['verified_history_reuses']+=1

    def evaluate(self,*args,**kwargs):
        receipt=super().evaluate(*args,**kwargs)
        # Keep full prefix proofs once in the historical cache. Repeated JSON
        # copies of the same 120-slot proof do not certify additional physics.
        compact={k:v for k,v in receipt.items() if k!='physical_steps'}
        compact.update(verified_prefix_steps=max(0,len(receipt['physical_steps'])-1),
            verified_prefix_digest=digest(self._observed_keys),prefix_proof_reference='PREFIX_CERTIFICATES.json',
            current_candidate_fully_measured=True)
        self.audit[-1]=compact
        return receipt

    def certificates(self):
        return dict(authority=self._authority,Source_7Reg_and_solver_policy_unchanged=True,
            prefix_states=self._historical_cache,performance=self.performance,
            state_clone_claimed=False,conservative_full_SolveSnap_prefix_retained=True)


def assert_equivalent(reference,optimized):
    if len(reference['physical_steps'])!=len(optimized['physical_steps']):
        raise ValueError('PREFIX_EQUIVALENCE_SLOT_COUNT')
    for a,b in zip(reference['physical_steps'],optimized['physical_steps']):
        for key in ('PASS','converged','violations','native_state','voltage_min_pu',
                'voltage_max_pu','maximum_phase_line_loading'):
            if a[key]!=b[key]:raise ValueError('PREFIX_EQUIVALENCE_'+key)
        for key in ('voltage_vector_pu','branch_measurement_rows'):
            if a[key] is None or b[key] is None:raise ValueError('DETAILED_PREFIX_EQUIVALENCE_REQUIRED')
            if not np.array_equal(np.asarray(a[key],float),np.asarray(b[key],float),equal_nan=True):
                raise ValueError('PREFIX_EQUIVALENCE_'+key)
    if reference['PASS']!=optimized['PASS']:raise ValueError('PREFIX_EQUIVALENCE_CURRENT_PASS_FAIL')
    return dict(PASS=True,taps_caps_exact=True,all_node_voltages_exact=True,
        all_branch_phase_amps_and_loading_exact=True,all_candidate_PASS_FAIL_exact=True,
        original_solver_tolerance_changed=False)


class ShadowCertifiedPrefixAC(CertifiedPrefixAC):
    """Every canary candidate independently checked against full prefix."""
    def __init__(self,*args,**kwargs):
        kwargs['detailed']=True
        super().__init__(*args,**kwargs)
        self.equivalence=[]

    def _probe(self,rows):
        from time import perf_counter
        before=dict(self.performance);start=perf_counter()
        optimized=CertifiedPrefixAC._probe(self,rows)
        optimized_wall=perf_counter()-start
        middle=dict(self.performance);start=perf_counter()
        reference=FullPrefixReferenceAC._probe(self,rows)
        reference_wall=perf_counter()-start
        checked=assert_equivalent(reference,optimized)
        self.equivalence.append(dict(candidate_input_sha=digest(rows),slots=len(rows),**checked,
            optimized_wall_seconds=optimized_wall,reference_wall_seconds=reference_wall,
            optimized_counts={k:middle[k]-before[k] for k in before},
            reference_counts={k:self.performance[k]-middle[k] for k in middle}))
        return optimized
