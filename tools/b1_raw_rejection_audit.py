"""Read-only qualification of a rejected numerical Phase-I point; Native=0.

The original failure, tolerance, raw point and scientific classification are
never changed. This only distinguishes a correctly rejected solver point
from a broken source, model compiler or verifier for date-dispatch purposes.
"""
from pathlib import Path
import sys, json, math
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_pr134_b1.common import read,record,atomic,digest,now
from v42_common_campaign.authority import source_files

SCIENCE='146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8'

def audit(result_path):
    result_path=Path(result_path);result=read(result_path);science=result['scientific']
    assert not result.get('source_global_integrity_block')
    assert science['classification']=='IMPLEMENTATION_FAILURE'
    assert science['error']=="ValueError('PHASE_I_RAW_REPLAY_FAIL')"
    assert result['source_SHA']==SCIENCE==digest(source_files())
    assert result['PASS'] is False and result['Native_Runtime_uncertain'] is False
    assert science['native_calls']==1
    request=read(result['request']['path']);assert record(result['request']['path'])==result['request']
    assert request['arm']=='B1' and request['day']==result['day']
    output=Path(request['output']);folder=output/'PHASE_I/S0'
    compiled=read(folder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json')
    assert compiled['PASS'] and compiled['differing_matrix_coefficients']==0
    prepared=read(output/'A_PREPARE_RECEIPT.json');assert prepared['PASS'] and prepared['verification']['PASS']
    identity=read(folder/'MODEL_IDENTITY.json');native=read(folder/'NATIVE_RESULT.json')
    assert native['status']==2 and native['native_error'] is None
    assert record(native['raw_attributes']['path'])==native['raw_attributes']
    assert record(native['model_identity']['path'])==native['model_identity']
    for name in ('matrix','attributes'):assert record(identity[name]['path'])==identity[name]
    assert identity['original_snapshot_sha256']==compiled['original_snapshot_sha256']
    assert identity['solver_policy_unchanged'] and not identity['bound_variables_relaxed']
    a=sp.load_npz(identity['matrix']['path']);attrs=np.load(identity['attributes']['path'])
    raw=np.load(native['raw_attributes']['path']);x=raw['X'];pi=raw['Pi'];rc=raw['RC']
    assert a.shape==(identity['rows'],identity['cols'])
    assert x.shape==(a.shape[1],) and pi.shape==(a.shape[0],) and rc.shape==x.shape
    assert all(np.all(np.isfinite(v)) for v in (x,pi,rc))
    activity=a@x;rhs=attrs['rhs'];senses=attrs['senses'];tol=1e-6
    residual=np.maximum(0,np.where(senses=='<',activity-rhs,np.where(senses=='>',rhs-activity,abs(activity-rhs))))
    bounds=np.maximum(0,np.maximum(attrs['lower']-x,x-attrs['upper']))
    bad=np.flatnonzero(residual>tol)
    assert 0<len(bad)<=32 and bounds.max(initial=0)<=tol
    rebuilt=attrs['objective']-a.T@pi
    assert np.all(abs(rebuilt-rc)<=1e-7+1e-10*np.maximum(abs(rebuilt),abs(rc)))
    witnesses=[]
    for i in bad:
        lo,hi=a.indptr[i:i+2];coeff=a.data[lo:hi];values=x[a.indices[lo:hi]]
        exact=sum((Fraction(float(c))*Fraction(float(v)) for c,v in zip(coeff,values)),Fraction(0))-Fraction(float(rhs[i]))
        violation=max(Fraction(0),exact if senses[i]=='<' else -exact if senses[i]=='>' else abs(exact))
        # Correct original verifier rejection, independently in rational arithmetic.
        assert violation>Fraction(1,1000000)
        assert max(abs(float(c)*float(v)) for c,v in zip(coeff,values))>1e9
        assert abs(float(raw['Slack'][i]))<=tol
        witnesses.append(dict(row=int(i),sense=str(senses[i]),exact_residual=str(exact),
            exact_violation=float(violation),original_tolerance=tol,
            maximum_term=max(abs(float(c)*float(v)) for c,v in zip(coeff,values))))
    ledger=read(result_path.parent/'NATIVE_RUNTIME_LEDGER.json')
    assert ledger['inflight'] is None and len(ledger['calls'])==1
    call=ledger['calls'][0]
    assert call['entered_native'] and call['status']=='FINISHED' and not call['runtime_unavailable']
    assert math.isclose(call['Native_Runtime'],result['Native_Runtime'],abs_tol=1e-12)
    return dict(PASS=True,disposition='DATE_LOCAL_REJECTED_NATIVE_NUMERICAL_POINT',
        original_scientific_classification=science['classification'],original_result=record(result_path),
        original_reason=result['reason'],source_SHA=SCIENCE,compiler=record(folder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'),
        native_raw=native['raw_attributes'],matrix=identity['matrix'],attributes=identity['attributes'],
        primal_original_tolerance=tol,primal_PASS=False,dual_PASS=True,exact_witnesses=witnesses,
        Native_Runtime=result['Native_Runtime'],additional_Native_calls=0,
        source_model_and_verifier_integrity=True,raw_point_modified=False,
        original_FAIL_preserved=True,Planning_Freeze_allowed=False,Actual_executed=False,UTC=now())

if __name__=='__main__':
    outcome=audit(sys.argv[1]);atomic(sys.argv[2],outcome);print(json.dumps(outcome))
