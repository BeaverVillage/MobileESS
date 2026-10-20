"""Reuse the verified preparation pipeline with ten explicit daily bindings."""
from pathlib import Path
from contextlib import contextmanager
from types import FunctionType
import inspect,textwrap,linecache
from v44_week3 import preparation as base
from v44.common import record

DAYS=tuple(f'2025-05-{n:02d}' for n in range(22,32))
ARMS=base.ARMS
CAMPAIGN=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign007_may22_31')
DOC,OPS=CAMPAIGN/'DOCUMENTS',CAMPAIGN/'OPERATIONS'
AUTH,STATE,VALIDATION=OPS/'PREPARATION_AUTHORIZATION.json',OPS/'BATCH_STATE.json',OPS/'PREPARATION_VALIDATION.json'


def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]+base.sources()


def functions():
    ns=dict(base.__dict__,DAYS=DAYS,ARMS=ARMS,CAMPAIGN=CAMPAIGN,DOC=DOC,OPS=OPS,AUTH=AUTH,STATE=STATE,
        VALIDATION=VALIDATION,sources=sources,__name__=__name__,__file__=__file__)
    names=('bindings','init_day','reference_fixture','validate_actual_adapter','template','validate_templates',
        'assert_unstarted','prepare','record_list','verify_prepared','main')
    for name in names:
        fn=getattr(base,name);body=textwrap.dedent(inspect.getsource(fn.__wrapped__ if name=='bindings' else fn))
        body=body.replace('len(values)!=28','len(values)!=40').replace("len(state['jobs'])!=28","len(state['jobs'])!=40")
        body=body.replace('cases=28','cases=40').replace('all_28_templates','all_case_templates').replace('ALL_28','ALL_40')
        body=body.replace('WEEK3_','WEEK4_').replace('5/15~5/21 캠페인 준비. 아직 실행하지 말고 준비. 5/8~5/14 끝나면 실행 예정. 오류 없이 날짜별 데이터 연결.',
            '5월 22~31 캠페인 준비. B1/B2/B3 실행 보류. B0만 별도 실행 권한으로 현재 캠페인과 추가 1-worker 날짜순 실행.')
        path=__file__+'.'+name+'.generated';linecache.cache[path]=(len(body),None,body.splitlines(True),path)
        exec(compile(body,path,'exec'),ns)
    return ns


_functions=functions()
for _name in ('bindings','no_execution','init_day','reference_fixture','validate_actual_adapter','template','validate_templates',
    'assert_unstarted','prepare','record_list','verify_prepared','main'):
    globals()[_name]=_functions[_name]

if __name__=='__main__':main()
