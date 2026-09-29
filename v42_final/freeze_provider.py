"""Assemble the explicitly approved matched fold5 study bundle; no fitting."""
import ast,shutil,subprocess
from .common import *


def extract(source,target,keep_functions,keep_classes):
    tree=ast.parse(source.read_text(encoding='utf8'));body=[]
    for node in tree.body:
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            # The copied inference routines need only these scientific imports.
            if isinstance(node,ast.ImportFrom) and node.module in ('scipy.optimize','sklearn.isotonic'):continue
            body.append(node)
        elif isinstance(node,ast.Assign):body.append(node)
        elif isinstance(node,ast.FunctionDef) and node.name in keep_functions:body.append(node)
        elif isinstance(node,ast.ClassDef) and node.name in keep_classes:
            node.body=[m for m in node.body if isinstance(m,ast.FunctionDef) and m.name in keep_classes[node.name]];body.append(node)
    text='"""Inference-only extraction from SHA-verified Runtime source. Training methods excluded."""\n'+ast.unparse(ast.Module(body=body,type_ignores=[]))+'\n'
    target.write_text(text,encoding='utf8')


def main():
    root=ROOT/'v42_final';bundle=root/'runtime_bundle';vendor=root/'inference'
    require(not bundle.exists(),'STUDY_BUNDLE_ALREADY_FROZEN')
    bundle.mkdir();vendor.mkdir(exist_ok=True);(vendor/'__init__.py').write_text('',encoding='utf8')
    sources=[]
    def verified(p):
        rel=p.relative_to(RUNTIME).as_posix()
        blob=subprocess.check_output(['git','show',RUNTIME_HEAD+':'+rel],cwd=RUNTIME)
        require(hashlib.sha256(blob).hexdigest()==sha(p),'PR95_TRACKED_SOURCE_IDENTITY:'+rel)
        sources.append(rec(p));return p
    for name in ('hazard.txt','model.json'):
        (bundle/'model').mkdir(exist_ok=True)
        shutil.copyfile(verified(V10/'FOLD_MODELS/fold5/G1'/name),bundle/'model'/name)
    shutil.copyfile(verified(V9/'FOLD_5_PREPROCESSING.json'),bundle/'preprocessing.json')
    states=read(verified(V10/'CALIBRATION_STATES/fold5_ISOTONIC_ROLLING14.json'))
    key='2025-03-31 00:00:00+00:00';state=states['states'][key]
    require(state['max_completion_used']=='2025-03-30 23:59:45+00:00','APPROVED_STATE_IDENTITY')
    (bundle/'calibration_state.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf8')
    extract(verified(V10/'hazard10.py'),vendor/'hazard.py',{'age_matrix'}, {'Hazard':{'__init__','parameters','tail_rates','cumulative','logsf','inverse_logsf','load'}})
    extract(verified(V10/'calibration10.py'),vendor/'calibration.py',{'maps_quantiles'},{'ProbabilityMap':{'__init__','logsf','inverse_logsf'}})
    extract(verified(RUNTIME/'docs/runtime_vnext8_trace_feature_total/features8.py'),vendor/'features.py',{'engineer'}, {})
    files=[dict(relative=p.relative_to(bundle).as_posix(),sha256=sha(p)) for p in bundle.rglob('*') if p.is_file()]
    integrity=dict(files=files,source_files=sources,study_provider=MODEL,fold=5,state_key=key,
        explicit_user_authorized=True,final_fit_model_used=False,calibration_recomputed=False,base_model_retrained=False,
        inference_source_extraction=[rec(p) for p in vendor.glob('*.py')])
    (bundle/'INTEGRITY.json').write_text(json.dumps(integrity,indent=2)+'\n',encoding='utf8')
    print('MATCHED_FOLD5_STUDY_BUNDLE_ASSEMBLED; reproduction still required')


if __name__=='__main__':main()
