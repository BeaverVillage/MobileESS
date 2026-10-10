"""Read only saved Source32 state/metadata; writes this audit folder only."""
import hashlib,json,sys,time
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from scipy import sparse

HERE=Path(__file__).resolve().parent
BASE=Path(r'D:\v42_may_restart_20261010_02\dates\B2')
CODE=Path(r'D:\v42run32')
SOURCE='9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9'

def record(path):
    p=Path(path);h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=h.hexdigest())

def read(path):
    b=Path(path).read_bytes();return json.loads(b.decode('utf-8-sig')),record(path)

def array_sha(a):
    a=np.ascontiguousarray(a);h=hashlib.sha256();h.update(json.dumps(dict(dtype=a.dtype.str,shape=a.shape),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode());h.update(memoryview(a).cast('B'));return h.hexdigest()

def main():
    sys.path.insert(0,str(CODE))
    import gurobipy as gp
    model_attempts=[]
    def deny(*args,**kwargs):
        model_attempts.append('MODEL_OR_NATIVE_ENTRY');raise AssertionError('AUDIT_NATIVE_MODEL_DENIED')
    gp.Model.__init__=deny;gp.Model.optimize=deny;gp.Model=deny
    from v42_m1_research.lb import repair_affine_equality_duals
    rows=[]
    for day,slot in [('01',3),('02',1),('03',2)]:
        root=BASE/f'2025-05-{day}'/'attempts'/f'repair_b2_v32_01_s{slot}'
        out=root/'output';request,request_record=read(root/'request.json')
        manifest,manifest_record=read(request['manifest'])
        admission,admission_record=read(out/'F1_STATE_ADMISSION.json')
        selection,selection_record=read(out/'F1_FULL_DOMAIN_LB_SELECTION.json')
        coupling,coupling_record=read(out/'004_L1_00'/'COUPLING_DUAL_EXACT.json')
        packet=record(out/'F1_SAME_ATTEMPT_STATE.npz')
        data_record=record(out/'C3A_DATA.npz')
        matrix_record=record(out/'C3A_A.npz')
        assert request['implementation_SHA']==SOURCE==manifest['execution_SHA']
        assert manifest_record['sha256']==request['manifest_SHA']
        assert admission['status']=='ADMITTED_CURRENT_ATTEMPT_ONLY'
        bind=admission['binding'];assert bind['implementation_SHA']==SOURCE
        assert bind['identity']=={k:request[k] for k in ('run_id','arm','day','worker_slot','attempt_id')}
        assert bind['code_root']==str(CODE) and admission['state_packet']==packet
        assert bind['manifest']==manifest_record
        assert bind['case']['case_sha']==selection['case_sha']==coupling['case_sha']
        assert selection['selected']=='ORIGINAL_ZERO_SIGNED_DUAL' and selection['maximum_exact_bound']=='0'
        f1=next(x for x in selection['candidates'] if x['kind']=='CURRENT_ATTEMPT_F1_ORIGINAL_ROW_PI')
        assert f1['certificate']['PASS'] and f1['certificate']['case_sha']==selection['case_sha']
        native=admission['F1_completed_Native_receipt']
        ledger,ledger_record=read(root/'NATIVE_RUNTIME_LEDGER.json')
        assert native in ledger['calls'] and native['status']=='FINISHED' and native['entered_native'] is True
        assert native['label']=='CURRENT_DAY_STATIONARY_FULL_INTEGER_REPRESENTATIVE_BOUNDS'
        ids=np.asarray(coupling['original_rows'],dtype=np.int64);senses=np.asarray(coupling['original_senses'])
        with np.load(out/'F1_SAME_ATTEMPT_STATE.npz',allow_pickle=False) as z:
            pi=z['pi'].copy()
            assert array_sha(pi)==bind['arrays']['pi']
        with np.load(out/'C3A_DATA.npz',allow_pickle=False) as z:
            data={k:z[k].copy() for k in z.files}
        assert {k:array_sha(v) for k,v in sorted(data.items())}==bind['case']['domain']
        names=data['row_names'][ids]
        matrix=sparse.load_npz(out/'C3A_A.npz').tocsr()
        assert list(matrix.shape)==bind['case']['matrix_shape']
        assert {k:array_sha(getattr(matrix,k)) for k in ('indptr','indices','data')}==bind['case']['matrix']
        start=time.perf_counter();repaired,repair_receipt=repair_affine_equality_duals(matrix,data,pi)
        replay_seconds=time.perf_counter()-start
        raw='\n'.join(f'{i}:{repaired[str(i)]}' for i in sorted(map(int,repaired))).encode('ascii')
        dual_sha=hashlib.sha256(raw).hexdigest()
        assert dual_sha==f1['certificate']['dual_SHA256']
        repaired_coupling={str(int(i)):repaired[str(int(i))] for i in ids if str(int(i)) in repaired}
        assert matrix_record==record(out/'C3A_A.npz') and data_record==record(out/'C3A_DATA.npz')
        del matrix,data
        vals=pi[ids];active=vals!=0;wrong=((senses=='<')&(vals>0))|((senses=='>')&(vals<0))
        families=np.asarray([str(n).split('[',1)[0] for n in names])
        unaffected=active&~wrong&np.asarray([not n.endswith('_binding') for n in families])
        sample=[dict(original_row=int(i),name=str(n),sense=str(s),raw_pi=float(v),
                     unchanged_by_original_repair=True) for i,n,s,v in zip(ids[unaffected],names[unaffected],senses[unaffected],vals[unaffected])]
        results=[]
        for sub in ('005_L2_00_MASTER','006_L3_00_MASTER'):
            result,rec=read(out/sub/'RMP_RESULT.json')
            assert result['dual_status']=='NO_FINITE_PI_FOLLOWUP_PRICING_NOT_RUN' and not result.get('full_original_dual')
            results.append(dict(artifact=rec,dual_status=result['dual_status'],native=result['native']))
        l4,l4_record=read(out/'007_L4_00'/'COUPLING_DUAL_EXACT.json')
        assert not coupling['multipliers'] and not l4['multipliers']
        rows.append(dict(day=request['day'],identity=bind['identity'],request=request_record,manifest=manifest_record,
            admission=admission_record,state_packet=packet,current_full_row_metadata=data_record,current_matrix=matrix_record,selection=selection_record,
            f1_original_full_domain_certificate=f1['certificate'],selected_exact_bound='0',selected_dual='ORIGINAL_ZERO_SIGNED_DUAL',
            f1_completed_native_receipt=native,current_ledger=ledger_record,
            raw_pi_coupling_nonzero=int(active.sum()),raw_pi_sign_clipped_coupling=int((active&wrong).sum()),
            coupling_families=dict(Counter(families[active])),
            original_exact_repair=repair_receipt,repair_replay_seconds=replay_seconds,
            actual_repaired_dual_SHA256=dual_sha,actual_repaired_coupling_nonzero=len(repaired_coupling),
            actual_repaired_coupling=repaired_coupling,
            theorem='Stored current CSR/domain fingerprints and F1 Pi SHA match original admitted state. Unchanged original repair was replayed without models/Native; its complete original-row dual SHA equals the already independently certified full-domain candidate SHA.',
            unchanged_nonbinding_coupling_rows=sample,
            actual_L1_coupling=coupling_record,actual_L4_coupling=l4_record,actual_price_coupling_nonzero=0,rmp_no_pi=results))
    protected=['v42_autonomous_b2/f1_state.py','v42_m1_research/lb.py','v42_m1_anytime/algorithms.py','v42_m1_hybrid/pricing.py','v42_may_campaign_native90/m_stage.py']
    payload=dict(schema='SOURCE32_CURRENT_F1_PRICE_SEED_READONLY_EVIDENCE_V1',UTC=datetime.now(timezone.utc).isoformat(),
        status='PASS',PASS=True,evidence_verification_only=True,Native_optimize_calls=0,real_Native_model_constructions=0,
        production_files_modified=False,execution_SHA=SOURCE,rows=rows,source_files={p:record(CODE/p) for p in protected},
        model_attempts=model_attempts,
        limitations=['Existing signed full-domain F1 certificate was matched to complete Native0 repaired-vector replay; no new pricing solve or full certificate reevaluation.',
                    'No pricing improvement or final scientific PASS asserted. No raw Native objective promoted to Global LB.',
                    'Current ledger record is a live snapshot; completed F1 call was compared to it and historical Native0 was not asserted.'])
    b=json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8');h=hashlib.sha256(b).hexdigest()
    path=HERE/('SOURCE32_CURRENT_F1_PRICE_SEED_EVIDENCE_'+h[:16]+'.json');path.write_bytes(b)
    print(json.dumps(record(path)))

if __name__=='__main__':main()
