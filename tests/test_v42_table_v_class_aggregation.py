from pathlib import Path
from dataclasses import replace,asdict
from fractions import Fraction
import copy
import json
import sys
import tempfile
import unittest
import numpy as np
import scipy.sparse as sp

from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_job_capability import Job
from v42_native.service import NativeServiceBoundary
from v42_integration.table_v_compression import (compress_lp,digest,semantic_identity,original_receipt_sha,
    redundant_rows,project_rational,lift_rational,exact_scale,file_record,checked_record)
from v42_integration.table_v_compression_verify import verify_sum,verify_redundancy


def fixture(n=2,upper=1.):
    A=sp.lil_matrix((1+n,1+n),dtype=float);A[0,0]=1
    for i in range(n):A[0,i+1]=-2;A[i+1,i+1]=1
    snapshot=LinearSnapshot(A.tocsr(),np.zeros(n+1),np.r_[10,np.full(n,upper)],
        np.asarray(['>']+['<']*n),np.r_[0,np.ones(n)],np.asarray(['C']+['B']*n),
        (Objective('rho',((0,Fraction(1)),),Fraction(0)),)).require()
    jobs={'u'+str(i):None for i in range(n)}
    classes={'k'+str(i):[uid] for i,uid in enumerate(jobs)}
    descriptor=dict(units=[dict(uid=uid,id=uid,class_key=key,v=dict(y={('site',24):('v',i+1)}))
        for i,(key,[uid]) in enumerate(classes.items())])
    data=({},jobs,{},{},{},{},{},dict(classes=classes))
    return snapshot,descriptor,data,dict(groups={'semantic':list(jobs)})


def public(uid):
    receipt=dict(uid=uid,policy_id='E1',hard_contract=dict(deadline=120),allowed_starts_seconds=[0,900])
    sha=original_receipt_sha(receipt)
    job=Job(uid,'PENDING',24,24,24,'site',2,1,initial_sites=('site',),checkpoint_authorized=True,
        qos_policy_id='E1',qos_receipt_sha=sha,qos_allowed_starts=(24,25),qos_budget_seconds=1800,duration_authority='FROZEN_Q50')
    bound=NativeServiceBoundary('V42_CONTINUOUS_SERVICE_INDEPENDENT_SNAPSHOT_V1',True,False,(24,25),122,sha,'d'*64)
    return job,bound,receipt


class ExactCompressionTests(unittest.TestCase):
    def test_receipt_lineage_does_not_split_equal_math(self):
        a,ab,ar=public('a');b,bb,br=public('b');bundle=dict(runtime_reserve_gamma=.5,runtime_survival_kernel=[1,.5])
        args=({},'resource',bundle,'graph')
        x=semantic_identity(a,ab,{},ar,'resource',bundle,'graph')
        y=semantic_identity(b,bb,{},br,'resource',bundle,'graph')
        self.assertEqual(digest(x),digest(y));self.assertNotEqual(ar['uid'],br['uid'])

    def test_receipt_tamper_rejected(self):
        a,b,r=public('a');r['hard_contract']['deadline']=130
        with self.assertRaisesRegex(ValueError,'AUTHORITY_DRIFT'):
            semantic_identity(a,b,{},r,'r',dict(runtime_reserve_gamma=1,runtime_survival_kernel=[]),'g')

    def test_gpu_site_service_window_deadline_runtime_are_separating(self):
        a,b,r=public('a');bundle=dict(runtime_reserve_gamma=.5,runtime_survival_kernel=[1,.5])
        base=semantic_identity(a,b,{},r,'r',bundle,'g')
        for field,value in [('gpu',2),('initial_sites',('other',)),('service_slots',3),('qos_budget_seconds',900),('state','RUNNING')]:
            if field=='state':changed=replace(a,state='RUNNING')
            else:changed=replace(a,**{field:value})
            self.assertNotEqual(digest(base),digest(semantic_identity(changed,b,{},r,'r',bundle,'g')))
        for boundary in (replace(b,latest_completion=123),replace(b,allowed_starts=(24,))):
            self.assertNotEqual(digest(base),digest(semantic_identity(a,boundary,{},r,'r',bundle,'g')))
        self.assertNotEqual(digest(base),digest(semantic_identity(a,b,dict(reference_end=27),r,'r',bundle,'g')))

    def test_real_matrix_sum_and_inverse(self):
        s,d,data,classes=fixture(3);before=s.fingerprint();result=compress_lp(s,d,data,classes)
        proof=verify_sum(s,result)
        self.assertTrue(proof['PASS']);self.assertEqual(result['snapshot'].matrix.shape,(2,2))
        x=(Fraction(6),Fraction(1),Fraction(1,2),Fraction(1,2))
        y=project_rational(result,x);self.assertEqual(y,(Fraction(6),Fraction(2)))
        lifted=lift_rational(result,y);self.assertEqual(project_rational(result,lifted),y)
        self.assertEqual(s.fingerprint(),before);self.assertFalse(proof['integer_decomposition_claimed'])

    def test_integer_decomposition_is_not_inferred_from_lp(self):
        s,d,data,c=fixture(2,.5);result=compress_lp(s,d,data,c)
        lifted=lift_rational(result,(Fraction(2),Fraction(1)))
        self.assertEqual(lifted[1:],(Fraction(1,2),Fraction(1,2)))
        self.assertTrue(np.all(result['snapshot'].vtypes=='C'))
        self.assertFalse(result['integer_compression'])

    def test_one_ulp_coupling_difference_is_rejected(self):
        s,d,data,c=fixture();A=s.matrix.copy();A[0,2]=np.nextafter(-2.,-np.inf)
        with self.assertRaisesRegex(ValueError,'ACTUAL_LOCAL_OR_COUPLING'):
            compress_lp(replace(s,matrix=A),d,data,c)

    def test_unequal_local_rhs_rejected(self):
        s,d,data,c=fixture();rhs=s.rhs.copy();rhs[2]=.5
        with self.assertRaisesRegex(ValueError,'ACTUAL_LOCAL_OR_COUPLING'):
            compress_lp(replace(s,rhs=rhs),d,data,c)

    def test_nonexact_multiplication_falls_back_without_loss(self):
        s,d,data,c=fixture(3,.1);result=compress_lp(s,d,data,c)
        self.assertEqual(len(result['records']),3)
        self.assertTrue(verify_sum(s,result)['PASS'])

    def test_nonexact_float_scale_is_rejected(self):
        with self.assertRaises(ValueError):exact_scale([.1],3)

    def test_independent_checker_rejects_altered_global_coefficient(self):
        s,d,data,c=fixture();result=compress_lp(s,d,data,c);A=result['snapshot'].matrix.copy();A[0,1]=-1
        altered=dict(result,snapshot=replace(result['snapshot'],matrix=A))
        with self.assertRaisesRegex(ValueError,'GLOBAL_COUPLING'):
            verify_sum(s,altered)

    def test_independent_checker_rejects_altered_inverse_multiplicity(self):
        s,d,data,c=fixture();result=compress_lp(s,d,data,c);result['scale'][1]=1
        with self.assertRaisesRegex(ValueError,'INVERSE_CARDINALITY'):
            verify_sum(s,result)

    def test_duplicate_and_tautology_proof(self):
        s,_,_,_=fixture();s=replace(s,matrix=sp.vstack([s.matrix,s.matrix[0],sp.csr_matrix((1,3))],format='csr'),
            senses=np.concatenate([s.senses,np.asarray(['>','='])]),rhs=np.r_[s.rhs,s.rhs[0],0.])
        reduced,proof=redundant_rows(s)
        self.assertEqual(len(proof['exact_duplicates']),1);self.assertEqual(len(proof['constant_tautologies']),1)
        self.assertTrue(verify_redundancy(s,reduced,proof)['PASS'])

    def test_infeasible_constant_cannot_be_deleted(self):
        s,_,_,_=fixture();s=replace(s,matrix=sp.vstack([s.matrix,sp.csr_matrix((1,3))],format='csr'),
            senses=np.concatenate([s.senses,np.asarray(['='])]),rhs=np.r_[s.rhs,1.])
        with self.assertRaisesRegex(ValueError,'INFEASIBLE_CONSTANT'):redundant_rows(s)

    def test_cache_mutation_and_missing_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'raw.npz';p.write_bytes(b'\x00NPZ\xff')
            record=file_record(p);self.assertEqual(checked_record(record),p)
            p.write_bytes(b'\x00NPZ\xfe')
            with self.assertRaises(ValueError):checked_record(record)
            p.unlink()
            with self.assertRaises(OSError):checked_record(record)


if __name__=='__main__':unittest.main()
