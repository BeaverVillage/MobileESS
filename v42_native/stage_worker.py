"""Private worker; launched only through the external stage supervisor."""
import json,sys,inspect
from pathlib import Path
from time import sleep,monotonic
from .contracts import require,file_sha
from .supervision import resolve,StageContext
from v42_a_stage_domain_v2.execution import require_action_authorized

def main():
    folder=Path(sys.argv[1]);request=json.loads((folder/'request.json').read_text())
    require_action_authorized(request,request.get('stage','OPTIMIZE'),require_day=False)
    while not (folder/'start.json').exists():
        if monotonic()>=request['deadline_monotonic']:raise TimeoutError('SUPERVISOR_START_TIMEOUT')
        sleep(.005)
    for name,h in request['sources'].items():require(file_sha(inspect.getsourcefile(resolve(name)))==h,'STAGE_SOURCE_DRIFT')
    context=StageContext(request,folder,resolve(request['validator']));context.check()
    resolve(request['worker'])(context,request['payload'])

if __name__=='__main__':main()
