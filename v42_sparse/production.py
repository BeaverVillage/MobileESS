"""One CPU full-May A1 after formulation and complete start policy freeze."""
from v42_root.common import *
from v42_root.data import prepare
from v42_root.native import build
from v42_root.start import validate_source
from v42_root.worker import optimize
from .performance import source_freeze,performance_gate

def main():
    source_freeze();gate=performance_gate();selection=read(OUT/'FORMULATION_SELECTION.json');kind=selection['selected'];data=prepare();context=Context()
    if (LOCAL/'PRIMARY_STARTED.json').exists() or (LOCAL/'START_VALIDATION_STARTED.json').exists():raise ValueError('NO_START_OR_PRIMARY_RETRY')
    m,units,levels,controls,bindings=build(context,data,kind);m.update()
    stats=read(LOCAL/'F2_MODEL_COMPLETE.json') if kind=='F2-BASE' else read(OUT/(kind+'_MODEL_STATS.json'))
    stats.update(columns=m.NumVars,full_jobs=len(data[1]),native_electrical_slots=96,build_excluded_from_A1_budget=True,canonical='WINDOWS',GPU_used=False)
    dump('MAY_SELECTED_MODEL_STATS.json',stats)
    if len(data[1])!=1499 or m.NumQConstrs or m.NumQNZs or m.NumSOS or m.NumGenConstrs:raise ValueError('FULL_NATIVE_MILP_REQUIRED')
    atomic(LOCAL/'START_VALIDATION_STARTED.json',dict(exactly_one_start_validation_policy=True,performance_gate=gate))
    start=validate_source(m,units,data,controls,bindings,levels[:6]);source_freeze()
    dump('MIP_START_GLOBAL_VALIDATION.json',read(OUT/'MIP_START_PHYSICAL_VALIDATION.json'))
    dump('PRODUCTION_FREEZE.json',dict(PASS=True,selected=kind,selection_sha256=sha(OUT/'FORMULATION_SELECTION.json'),start_receipt_sha256=sha(OUT/'MIP_START_RECEIPT.json'),start_validated=start['validated'],source_manifest_sha256=sha(OUT/'SOURCE_MANIFEST.json'),solver=read(OUT/'PREREGISTRATION.json')['solver'],performance_gate=performance_gate(),production_GPU=False,complete_original_domains=True))
    try:optimize(m,units,levels[:6],controls,bindings,data,start)
    finally:m.dispose()
if __name__=='__main__':main()
