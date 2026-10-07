"""Volatile arithmetic-result cache restricted to independent proof audits.

No persisted PASS flag is trusted. Every exact mathematical input is hashed.
This adapter returns certificates only; audit callers discard vector outputs.
It must not wrap the oracle's first certificate computation.
"""
import copy, hashlib, json
from contextlib import contextmanager
import numpy as np

class CertificateAuditCache:
    def __init__(self,compute):
        self.compute=compute;self.results={};self.hits=0;self.misses=0
    @staticmethod
    def key(A,d,pi):
        h=hashlib.sha256()
        h.update(b'original-bounded-lagrangian-audit-cache-v1')
        h.update(json.dumps(list(A.shape)).encode())
        for tag,values in [('A.data',A.data),('A.indices',A.indices),('A.indptr',A.indptr),*((k,d[k]) for k in ['objective','constant','rhs','sense','lower','upper']),('Pi',pi)]:
            a=np.asarray(values)
            h.update(tag.encode());h.update(a.dtype.str.encode())
            h.update(json.dumps(list(a.shape)).encode());h.update(a.tobytes(order='C'))
        return h.hexdigest()
    def certificate_only(self,A,d,pi):
        key=self.key(A,d,pi)
        if key not in self.results:
            certificate,_,_,_=self.compute(A,d,pi)
            self.results[key]=copy.deepcopy(certificate);self.misses+=1
        else:self.hits+=1
        return copy.deepcopy(self.results[key]),None,None,None
    @contextmanager
    def audit_scope(self,module):
        prior=module.exact_bounded_lagrangian
        assert prior is self.compute,'ARITHMETIC_CACHE_SCOPE_ALREADY_ACTIVE'
        module.exact_bounded_lagrangian=self.certificate_only
        try:yield
        finally:module.exact_bounded_lagrangian=prior
    def stats(self):
        return dict(hits=self.hits,independent_exact_recomputations=self.misses,entries=len(self.results),volatile_only=True,empty_on_every_process_restart=True,oracle_first_computation_cached=False,every_arithmetic_input_rehashed=True,certificate_arrays_not_cached=True)
