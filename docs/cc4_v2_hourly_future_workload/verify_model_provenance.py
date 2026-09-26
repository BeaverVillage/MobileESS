"""Supplemental read-only model/checkpoint and original Git-authority validation."""
from common import *
import subprocess
import torch


def main():
    z=np.load(ROOT/'DATA.npz');l=pd.read_csv(ROOT/'DAY_LEDGER.csv')
    tr=np.flatnonzero(l.split.eq('TRAIN')&l.eligible)
    freeze=json.loads((ROOT/'MODEL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))
    checks=[]
    p=z['past'].copy();x=z['X'].copy()
    for j in [0,1,3]:p[:,:,j]=np.log1p(np.maximum(p[:,:,j],0))
    x=np.sign(x)*np.log1p(abs(x))
    expected=dict(pm=p[tr].mean((0,1)),ps=np.maximum(p[tr].std((0,1)),.1),
                  xm=x[tr].mean((0,1)),xs=np.maximum(x[tr].std((0,1)),.1))
    for run in freeze['runs']:
        folder=ROOT/'fits'/run['tag']
        if run['family']=='SEASONAL':continue
        receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
        require(receipt['N_training_days']==len(tr),'training membership count')
        if run['family']=='LGBM':
            for name,digest in receipt['model_hashes'].items():require(sha(folder/name)==digest,'model file drift')
            require(receipt['training_dates']==z['days'][tr].tolist(),'LGBM train dates')
        else:
            require(sha(folder/'model.pt')==receipt['model_sha256'],'neural checkpoint drift')
            saved=torch.load(folder/'model.pt',map_location='cpu',weights_only=False)
            for key,val in expected.items():
                require(np.array_equal(val,saved['config']['normalizer'][key]),'non-TRAIN normalizer '+key)
            positive=z['y'][tr][z['y'][tr]>0]
            require(np.isclose(saved['config']['center'],np.log(positive).mean(),rtol=0,atol=1e-12),'non-TRAIN target scaler')
            require(all(h['finite_gradients'] for h in receipt['history']),'nonfinite training gradient')
            best=min(receipt['history'],key=lambda h:h['dev_Q90_pinball_GPUh'])['epoch']
            require(best==receipt['selected_epoch'],'early stopping did not follow DEVELOPMENT')
        checks.append(dict(tag=run['tag'],status='PASS',N_train_days=len(tr),training_seconds=receipt['training_seconds'],
                           gpu_peak_memory_bytes=receipt.get('gpu_peak_memory_bytes',0)))
    authority=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    bindings=[]
    mapping={'PR42 eligibility code':('04f9c738ad80786b3860638304043b06129c04ef','dayahead/v41/data.py'),
             'PR42 causal feature code':('04f9c738ad80786b3860638304043b06129c04ef','dayahead/v41/workload.py'),
             'PR59 TFT/DeepAR code':('659a0a66a76d28d1f8103a2f2976ec4cda410136','docs/cc4_replacement_ml_offline/models_offline.py'),
             'PR59 LightGBM settings and workflow':('659a0a66a76d28d1f8103a2f2976ec4cda410136','docs/cc4_replacement_ml_offline/run_experiment.py')}
    for source in authority['sources']:
        if source['purpose'] not in mapping:continue
        commit,path=mapping[source['purpose']]
        blob=subprocess.check_output(['git','show',f'{commit}:{path}'],cwd=ROOT)
        digest=hashlib.sha256(blob).hexdigest()
        require(digest==source['sha256'],'Git authority bytes differ '+path)
        bindings.append(dict(commit=commit,path=path,sha256=digest,status='PASS'))
    dump('MODEL_PROVENANCE_VALIDATION.json',dict(status='PASS',time=now(),models=checks,Git_bindings=bindings,
         neural_scalers_exact_TRAIN_only=True,optimizers_imported=False,grid_campaign_executions=0))
    print('MODEL PROVENANCE PASS',len(checks),'models;',len(bindings),'Git source bindings')


if __name__=='__main__':main()
