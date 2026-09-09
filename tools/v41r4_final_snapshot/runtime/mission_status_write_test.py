from mission_health import *
original=os.replace;calls=[]
def sharing_error(source,target):
    calls.append(str(source))
    if len(calls)<3:raise PermissionError(13,'simulated concurrent Windows reader')
    return original(source,target)
target=LOG/f'status_write_regression_{int(time.time())}.json'
try:
    os.replace=sharing_error;write(target,dict(status='PASS',writer='retry_test'))
finally:os.replace=original
assert len(calls)==3 and read(target)['status']=='PASS'
print('STATUS_WRITE_RETRY_PASS',len(calls))
