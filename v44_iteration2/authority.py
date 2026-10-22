from pathlib import Path
from . import config as c
from .io import read,record,verify,atomic,digest,now

def sources():return [record(p) for p in sorted(c.CODE.glob('*.py'))]+[record(c.REPO/p) for p in ('docs/V44_iteration2.md','scripts/launch_v44_iteration2.ps1')]

def parent_authority(request):
 stage=request['iteration_stage']
 if stage=='ACTUAL':return
 expected=c.PARENT[stage];reference=request['fixed_parent_receipt'];core=Path(request['fixed_parent_core'])
 if request['fixed_parent_stage']!=expected or reference['path']!=str(core):raise PermissionError('EXACT_PRECEDING_PUBLIC_STAGE_REQUIRED')
 if stage=='M2':
  row=next(r for r in read(c.DOC/'BASELINE_CATALOG.json')['days'] if r['day']==request['day'])
  original=next(r for r in row['evidence'] if Path(r['path'])==Path(row['A2'])/'RESULT.json')
  if reference!=original:raise PermissionError('M2_MUST_REUSE_EXACT_ORIGINAL_A2')
  return
 if not core.resolve().is_relative_to((c.ROOT/request['day']/'B3').resolve()):raise PermissionError('NEW_STAGE_CANNOT_CONSUME_OLD_CAMPAIGN_OPTIMUM')
 producer=read(core.parent/'request.json')
 if any(producer.get(k)!=v for k,v in dict(day=request['day'],arm='B3',iteration_stage=expected,equipment_version=c.EQUIPMENT,iteration2_authorization=request['iteration2_authorization']).items()):raise PermissionError('NEW_PRECEDING_STAGE_PRODUCER_REQUIRED')
 verify([reference]);publics=[core.parent.parent/n for n in ('RESULT.json','RECOVERED_COMPLETED_RESULT.json')]
 public=next((read(p) for p in publics if p.exists() and read(p).get('PASS') is True and read(p).get('core_result')==reference),None)
 if not public or public['stage']!=expected:raise PermissionError('NEW_PRECEDING_STAGE_FULL_PUBLIC_CERTIFICATE_REQUIRED')
 if expected.startswith('A') and public.get('new_AIDC_FULL_optimization') is not True:raise PermissionError('NEW_AIDC_FULL_OPTIMIZATION_REQUIRED')
def validate(request=None):
 auth=read(c.OPS/'AUTHORIZATION.json');verify(auth['sources']+auth['inputs']+[auth['validation'],auth['user_request']])
 if auth['sources']!=sources() or auth['MESS_units']!=list(c.FLEET):raise PermissionError('ITERATION2_SEALED_SOURCE_OR_FLEET_DRIFT')
 if request:
  root=Path(request['case_root'])
  if request['day'] not in c.DAYS or request['arm']!='B3' or Path(request['campaign_root'])!=c.ROOT or not root.resolve().is_relative_to((c.ROOT/request['day']/'B3').resolve()):raise PermissionError('ONLY_NEW_ITERATION2_31_B3_CASES')
  if request['iteration_stage'] not in c.STAGES+('ACTUAL',) or request['iteration2_authorization']!=record(c.OPS/'AUTHORIZATION.json'):raise PermissionError('EXACT_PUBLIC_STAGE_AUTHORITY_REQUIRED')
  if request.get('resume_of') or request.get('resume_parent'):raise PermissionError('RESUME_MUST_USE_CHECKED_STAGE_ADAPTER')
  verify(request['sources'])
  parent_authority(request)
 return auth

def authorize(commit):
 path=c.OPS/'AUTHORIZATION.json'
 if path.exists():raise FileExistsError('NEW_AUTHORIZATION_VERSION_REQUIRED')
 validation=c.DOC/'VALIDATION.json'
 if read(validation).get('PASS') is not True:raise PermissionError('LIGHT_TESTS_AND_PREFLIGHT_REQUIRED')
 user=c.DOC/'USER_REQUEST.txt'
 atomic(path,dict(schema='V44_ITERATION2_AUTHORITY_V1',UTC=now(),commit_sha=commit,
  sources=sources(),inputs=[record(c.DOC/n) for n in ('BASELINE_CATALOG.json','SEVEN_DAY_INPUT_MANIFEST.json')],
  validation=record(validation),user_request=record(user),MESS_units=list(c.FLEET),
  clarification='Human confirmed existing four MESS, not eight.',explicit_user_approved=True,
  reuse_only=['A1','M1','A2'],new_stages=list(c.STAGES),B1_new_run=False,
  B2_must_finish_and_release_all_resources=True,Actual_requires_31_verified_M4=True,max_Actual_workers=7,
  equipment_version=c.EQUIPMENT,algorithm='ORIGINAL_V44_R043',budgets=dict(K48=300,Joint=900,Joint_call=300,A=5400,A_PhaseI=1500),
  gaps=dict(M=.03,A=.005),threads=dict(A_Native=1,M_Native=4,Actual=1)))
