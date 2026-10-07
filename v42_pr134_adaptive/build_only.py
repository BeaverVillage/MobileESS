"""Static build is allowed while a different optimizer is active."""
import sys
from .common import *
from .restricted import build
day,selection,tag=sys.argv[1:]
folder=CASE/day/tag
if (folder/'CENSUS.json').exists():raise PermissionError('STATIC_BUILD_ALREADY_CAPTURED')
folder.mkdir(parents=True,exist_ok=True)
frozen_selection=folder/'SELECTED_DOMAIN_INPUT.json'
if frozen_selection.exists():raise PermissionError('IMMUTABLE_SELECTED_INPUT_ALREADY_EXISTS')
atomic(frozen_selection,read(selection))
m,*rest=build(day,read(frozen_selection),folder)
m.dispose()
atomic(folder/'STATIC_ONLY.json',dict(PASS=True,optimizer_calls=0,scientific_implementation_base_commit=BASE,
    producer_source_files=[record(Path(__file__)),record(ROOT/'v42_pr134_adaptive/restricted.py'),record(ROOT/'v42_pr134_adaptive/global_identity.py')],selected=record(frozen_selection),
    matrix=record(folder/'EXPANDED_MATRIX.npz'),attributes=record(folder/'EXPANDED_ATTRIBUTES.npz'),descriptor=record(folder/'SCIENTIFIC_INTERFACES.pkl.gz')))
print('STATIC_CAPTURE_PASS',day,tag,flush=True)
