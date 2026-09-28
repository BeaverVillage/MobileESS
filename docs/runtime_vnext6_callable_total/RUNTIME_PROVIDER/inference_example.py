from provider import RuntimeProvider, running_proxy
p=RuntimeProvider(allow_research=True)
r=p.predict_total({'job_uid':'COMPLETELY_NEW_ID'}, '2025-04-01T00:00:00Z')
print(r)
print(running_proxy(r['planned_runtime_seconds'], r['planned_runtime_seconds']+1, True))
