"""Compatibility entry for the existing r043 monitor; never starts a server."""
import json,urllib.request
URL='http://127.0.0.1:8795/'

def snapshot():
 with urllib.request.urlopen(URL+'api/status',timeout=15) as response:value=json.load(response)
 details=value.get('iteration2_details')
 if not details or not details.get('available'):raise RuntimeError('EXISTING_R043_MONITOR_ITERATION_DETAILS_NOT_CONNECTED')
 return details

def serve(port=8795):
 if port!=8795:raise ValueError('USE_EXISTING_R043_MONITOR_PORT_8795')
 value=snapshot();print(json.dumps(dict(URL=URL,existing_monitor=True,phase=value.get('phase'),rows=len(value.get('rows',[]))),ensure_ascii=False));return value
