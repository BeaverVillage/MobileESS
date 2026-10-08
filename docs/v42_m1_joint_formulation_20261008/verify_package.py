"""Independent publication audit of bytes, receipts and inherited authority."""
from common import *

def run():
    gp,old=forbid_optimize()
    try:
        manifest=read(OUT/'SHA256_MANIFEST.json');files=manifest['files']
        assert all(sha(OUT/name)==expected for name,expected in files.items())
        expected={'C3A_A.npz':'45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8','C3A_DATA.npz':'20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467'}
        for name,value in expected.items():
            path=hc.PARENT/name;assert sha(path)==value
            blob=subprocess.check_output(['git','show',BASE+':'+path.relative_to(ROOT).as_posix()],cwd=ROOT);assert hashlib.sha256(blob).hexdigest()==value
        A,d,_=load();identity=objective_identity(A,d);assert identity['PASS']
        original=read(OUT/'runs/ORIGINAL/RESULT.json');assert original['optimal_certificate_PASS']
        assert original['valid_LB']==read(OUT/'runs/ORIGINAL/EXACT_LB_CERTIFICATE.json')['lower_bound']
        for label in ['A','B']:
            p=read(OUT/f'{label}_EXACTNESS_VERIFICATION.json');assert p['PASS']
            for key,name in [('matrix_SHA256',f'{label}_ADDED_MATRIX.npz'),('data_SHA256',f'{label}_DATA.npz'),('spec_SHA256',f'{label}_SPEC.json')]:assert p[key]==sha(OUT/name)
            r=read(OUT/f'runs/{label}/RESULT.json');assert r['native_status']==9 and r['valid_LB'] is None and r['optimize_calls']==1
            assert read(OUT/f'{label}_MATERIALITY_GATE.json')['PASS'] is False
        markers=list((OUT/'runs').glob('*/OPTIMIZE_ONCE.json'));assert len(markers)==3
        for p in markers:
            marker=read(p);params=read(p.parent/'SOLVER_PARAMETERS.json');assert marker['optimize_calls']==1
            assert sha(p.parent/'RUNNER_SOURCE.py')==marker['runner_source_SHA256']
            for k,v in SETTINGS.items():assert params[k]==v
            assert read(p.parent/'MODEL_IDENTITY.json')['objective']['source_objective_SHA256']==identity['source_objective_SHA256']
        result=read(OUT/'RESULT.json');assert result['classification']=='JOINT_FORMULATION_TRACTABILITY_FAIL'
        assert result['valid_LB']==LB and result['valid_UB']==UB and result['native_total_optimize_calls']==3
        assert result['canary']['optimize_calls']==0 and not result['point5_percent_achieved']
        assert read(OUT/'CENTER_FULL_REPLAY.json')['PASS'] and read(OUT/'BOUNDED_EXACTNESS_TESTS.json')['PASS']
        scope=git('diff','--name-only',BASE);assert all(p.startswith('docs/v42_m1_joint_formulation_20261008/') for p in scope.splitlines())
        print(json.dumps(dict(PASS=True,manifest_verified_files=len(files),scientific_git_blob_identity=True,objective_identity=True,native_calls=3,canary_calls=0,bounds_unchanged=True,scope_only_new_directory=True,optimize_calls=0)),flush=True)
    finally:gp.Model.optimize=old

if __name__=='__main__':run()
