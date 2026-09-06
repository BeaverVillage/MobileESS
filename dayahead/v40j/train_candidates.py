"""Deterministic candidate fits, independent of baseline fold compute latency."""
import hashlib
import json
import pickle
from .contracts import OUT, SPLIT, CANDIDATES
from .data import read_frame, train_mask, block_mask
from .firewall import ReadFirewall, write
from .methods import CausalModel, raw_features

def main():
    fw=ReadFirewall('candidate_training').install()
    try:
        assert json.loads((OUT/'V40J_CURRENT_RUNTIME_BASELINE.json').read_text())['status']=='PASS'
        f=read_frame(OUT/'DEVELOPMENT_GPU_ROWS.parquet')
        (OUT/'models').mkdir(exist_ok=True)
        records=[]
        for fold in SPLIT['folds']:
            train=f.loc[train_mask(f,fold['fit_before'])]
            val=f.loc[block_mask(f,fold['validation'],SPLIT['validation_label_deadline'])]
            x=raw_features(train); xv=raw_features(val)
            y=train.runtime_seconds.to_numpy()
            early=(train.job_state.to_numpy()=='FAILED')|(y<=300)
            for entry in CANDIDATES:
                cid=entry['id']
                if cid in ['C0','C4']: continue
                print(fold['id'],cid,'training and independent deterministic refit',flush=True)
                m=CausalModel(cid).fit(x,y,early_target=early)
                p=m.predict(xv)
                m2=CausalModel(cid).fit(x,y,early_target=early)
                p2=m2.predict(xv)
                assert p.tobytes()==p2.tobytes(),'NONDETERMINISTIC_TRAINING'
                encoded=pickle.dumps(m,protocol=5)
                path=OUT/'models'/f"{fold['id']}_{cid}.pkl"
                path.write_bytes(encoded)
                records.append({'fold':fold['id'],'candidate':cid,'training_rows':len(train),
                    'same_seed_input_independent_refit_prediction_bytes_identical':True,
                    'prediction_sha256':hashlib.sha256(p.tobytes()).hexdigest(),
                    'model_sha256':hashlib.sha256(encoded).hexdigest()})
                write('V40J_TRAINING_DETERMINISM.json',records)
        print('CANDIDATE_TRAINING_COMPLETE',flush=True)
    finally: fw.close()

if __name__=='__main__': main()
