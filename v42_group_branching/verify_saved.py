"""Portable independent checks of committed evidence; native optimize is blocked."""
from .common import *
from .domain import child_data
from v42_b2_root_validation.certificate import verify_certificate
from fractions import Fraction

def verify():
    prior.forbid_optimize();dest=ROOT/NAMESPACE;m=read(dest/'SHA256_MANIFEST.json')
    assert all(sha(dest/n)==v['sha256'] for n,v in m['files'].items())
    assert all(sha(ROOT/n)==v['sha256'] for n,v in m['source_modules'].items())
    inherited=read(SOURCE187/'SHA256_MANIFEST.json')
    assert all(sha(SOURCE187/n)==v['sha256'] for n,v in inherited['files'].items())
    assert all(sha(hc.PARENT/n)==v for n,v in inherited['scientific_source_hashes'].items())
    A,d,T,AA,full=model_inputs();assert prior.objective_identity(A,d)['PASS']
    final=read(dest/'FINAL_DECISION.json');selection=read(dest/'SELECTED_BRANCH_VARIABLES.json')['selected']
    checks=[];pairs=[]
    allresults=[read(p) for p in (dest/'children').glob('*/z*/RESULT.json')]
    calls=sum(r['native_calls'] for r in allresults);runtime=sum(r.get('Runtime',0) for r in allresults);work=sum(r.get('Work',0) for r in allresults)
    continuation=(dest/'Z0_CONTINUATION_CONTROLLER_RESULT.json').exists()
    for k,candidate in enumerate(selection,1):
        label=f'C{k:02d}';bound=[]
        for value in (0,1):
            folder=dest/'children'/label/f'z{value}'
            if continuation and label=='C01' and value==0:folder=dest/'children/C01_CONTINUATION/z0'
            result=folder/'RESULT.json'
            if not result.exists():continue
            r=read(result)
            identity=read(folder/'MODEL_IDENTITY.json');expected=dict(CHILD_SETTINGS,TimeLimit=1800) if folder.parent.name=='C01_CONTINUATION' else CHILD_SETTINGS
            assert identity['PASS'] and identity['parameters']==expected
            assert identity['selected_column']==candidate['column'] and identity['selected_value']==value
            assert r['native_calls']==1 and (folder/'NATIVE_CALL_STARTED.json').exists()
            if not r['certificate_PASS']:continue
            assert r['Status']==2,'Infeasibility witness needs a separate checked mathematical functional'
            proof=read(folder/'EXACT_CERTIFICATE.json');accepted=dict(proof['accepted'])
            accepted.update(exact_path=str(folder/Path(accepted['exact_path']).name),npz_path=str(folder/Path(accepted['npz_path']).name))
            independent=verify_certificate(AA,child_data(full,candidate['column'],value),accepted)
            assert independent['PASS'] and independent['certified_LB']==r['exact_LB']
            assert independent['exact_payload_SHA256']==proof['independent']['exact_payload_SHA256']
            assert independent['multiplier_payload_SHA256']==proof['independent']['multiplier_payload_SHA256']
            with np.load(folder/'RAW.npz') as f:
                raw=f['pi'];assert f['x'].shape==(306040,) and f['slack'].shape==(583459,)
                assert all(np.isfinite(f[n]).all() for n in f.files)
            bad=((full['sense']=='<')&(raw>0))|((full['sense']=='>')&(raw<0))
            native=proof['base']['raw_native_multiplier_certificate']
            assert native['PASS']==bool(not bad.any())
            if bad.any():assert native['count']==int(bad.sum())
            bound.append(Fraction(independent['exact_alpha']));checks.append(dict(candidate=label,value=value,**independent))
        if len(bound)==2:
            rational=min(bound);safe=float(rational)
            if Fraction.from_float(safe)>rational:safe=float(np.nextafter(safe,-np.inf))
            pair=read(dest/('C01_CONTINUED_PAIR_RESULT.json' if continuation and label=='C01' else f'{label}_PAIR_RESULT.json'))
            assert pair['pair_certificate_PASS'] and safe==pair['LB_pair']
            pairs.append(dict(candidate=label,certified_LB=safe))
    global_lb=max([LB,*[p['certified_LB'] for p in pairs]])
    assert calls==final['native_optimize_calls']<=6 and runtime==final['Native_Runtime_sum']<=2880 and work==final['Work_sum']
    assert global_lb==final['new_valid_global_LB'] and final['old_UB']==final['new_UB']==UB
    assert final['Delta_LB']==global_lb-LB and final['new_global_gap_percent']==100*(UB-global_lb)/UB
    assert not final['production_calls'] and not final['P2_calls'] and not final['downstream_calls']
    return dict(PASS=True,new_native_calls=0,completed_native_calls=calls,Runtime_sum=runtime,Work_sum=work,
        pairs=pairs,global_LB=global_lb,global_gap_percent=final['new_global_gap_percent'],checks=checks,
        evidence_hashes_PASS=True,source_hashes_PASS=True,scientific_objective_PASS=True,
        raw_sign_failures_explicit=True,restricted_child_to_global_min_rule_PASS=True,
        all_finite_box_support_terms_checked=True,UB_unchanged=True)

if __name__=='__main__':
    result=verify();write(REPORTS/'COMMITTED_EVIDENCE_REPLAY.json',result)
    print('COMMITTED_GROUP_EVIDENCE_PASS',result['completed_native_calls'],result['global_LB'],flush=True)
