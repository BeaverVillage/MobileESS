"""Publish exact recovery source bytes and compact evidence to the existing PR checkout."""
from pathlib import Path
import shutil,json,hashlib

live=Path('D:/v44_r022_rowgen_20261017')
pr=Path('D:/v44_r043_pr_update_20261019')
campaign=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1')
home=campaign/'campaign005_may08_14/OPERATIONS/R049_MAY23_WEATHER'
week4=campaign/'campaign007_may22_31'
docs=pr/'docs/v44/r049_may23_weather_recovery_20261020'
docs.mkdir(parents=True,exist_ok=True)
records=[]
def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    assert source.read_bytes()==target.read_bytes()
    records.append(dict(source=str(source),repository_path=target.relative_to(pr).as_posix(),bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
for source in sorted((live/'v44_recovery_r049').glob('*.py')):copy(source,pr/source.relative_to(live))
for name in ('authorize_r049_weather.py','verify_r049_month.py','restart_r049_monitor.py','verify_r049_live.py','package_r049_pr.py'):
    source=live/'validation_tools/campaign_preparation'/name;copy(source,pr/source.relative_to(live))
copy(live/'tests/test_v44_recovery_r049.py',pr/'tests/test_v44_recovery_r049.py')
copy(Path('D:/MobileESS_V43/development/monitor_partial/monitor_binding.py'),pr/'v44_monitor_live_ui/monitor_binding.py')
for name in ('AUTHORIZATION.json','VALIDATION.json','USER_REQUEST.json','SAME_TIME_OBSERVATIONS.json','MONTH_INPUT_RECHECK.json','RUN_LAUNCH.json','STATE_BEFORE_RECOVERY.json','LIVE_REQUEUE_VERIFIED.json','MONITOR_VERIFIED.json'):
    copy(home/name,docs/name)
for name in ('MAY23_B0_RECOVERED_WEATHER_CERTIFICATION.json',):copy(week4/'DOCUMENTS'/name,docs/name)
copy(week4/'OPERATIONS/MAY23_B0_RECOVERED_WEATHER_PERMIT.json',docs/'MAY23_B0_RECOVERED_WEATHER_PERMIT.json')
copy(week4/'DOCUMENTS/input_metadata/2025-05-23/RECOVERED_WEATHER_BINDING.json',docs/'RECOVERED_WEATHER_BINDING.json')
copy(Path('D:/v44_r049_regression_20261020.xml'),docs/'v44_r049_regression_20261020.xml')
(docs/'SOURCE_SNAPSHOT.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
attributes=pr/'.gitattributes';rule=b'v44_recovery_r049/** -text whitespace=cr-at-eol\n'
if rule.rstrip() not in attributes.read_bytes():
    with attributes.open('ab') as stream:stream.write(b'\n'+rule)
(docs/'README.md').write_text('''# V44 r049: restore May23 weather and monthly B0 eligibility

May23's three stale weather lookups came from a decoder omission: the original NOAA rows have valid same-time MA1 altimeter observations, although station and sea-level pressure fields are missing. The recovery derives station pressure from the measured 1018 hPa altimeter and the source station elevation of 132.28 m using the standard-atmosphere Smithsonian/MetPy conversion. This pressure is explicitly **derived**, not a direct station-pressure measurement. It requires the standard-atmosphere conversion assumption.

At 2025-05-22 15:00 and 16:00 UTC (May23 in Melbourne), the valid FM-15/FM-16 duplicates agree on 13 C dry bulb, 11 C dew point and Q1018. The derived station pressure is 1002.4410849095201 hPa. The unchanged original psychrometric functions produce 87.6457107322462% RH and 11.856969099303287 C wet bulb at both instants. Raw rows, QC, hashes, timestamp provenance and the derivation are retained in SAME_TIME_OBSERVATIONS.json.

Only May23's scoped observation loader receives these two records. Raw CSV/parquet files remain byte-identical; demand/PV and all other dates retain their original observation hashes. There is no temporal interpolation or future observation read. The existing 7200-second weather age limit and physical acceptance thresholds are unchanged. Original finite wet-bulb calculations replay exactly: 13,877 values, maximum absolute difference zero.

Validation: 80 focused regressions pass; all May23 121 boundaries pass; all May22-31 1210 boundaries pass with zero failed queries. These are input and regression checks, not completed May23 scientific execution results. A separate May23 worker admission check passes with zero Native calls or control ticks and does not create its case directory.

The r048a monthly controller drained the current May17 B0 case normally, retaining its PASS result. The r049 controller then restored only May23 from EXCLUDED to BASELINE_QUEUED and resumed the same one-worker chronological queue. May15/16/17 PASS result hashes are preserved. May18 B0 entered real Actual/Fresh while the four remaining original B1/B3 Actual workers continued under their original PIDs. Only the existing monitor process was refreshed: its 31-date Fresh loading table and address remain, with May23 shown as recovered and waiting. No new future-date B1/B2/B3 execution is released. The existing main B2 follow-up and resource handover rules remain inherited.

Historical exclusion and failed-attempt evidence remain immutable. The dated recovery permit explicitly supersedes the May23 B0 exclusion; old historical snapshots still describe their original state. May23's Actual/Fresh result remains pending until its chronological turn.

Evidence: VALIDATION.json, MONTH_INPUT_RECHECK.json, LIVE_REQUEUE_VERIFIED.json, MONITOR_VERIFIED.json, the scoped certification/permit and SOURCE_SNAPSHOT.json. Runtime paths in receipts refer to the original live evidence; this directory retains compact snapshots and exact source bytes.

Conversion references: [MetPy API](https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.altimeter_to_station_pressure.html), [versioned implementation](https://github.com/Unidata/MetPy/blob/v1.7.1/src/metpy/calc/basic.py). Source format: [NOAA ISD](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database).
''',encoding='utf-8')
(docs/'PR_BODY.md').write_text('''V44 completes May01-07 with 28/28 official Actual and independent Fresh physical PASS results, preserves the running May08-14 campaign, and extends one additional B0 worker through May31. Completed May08-14 B0 results are preserved. Original B1/B3 Actual cases continue through natural completion, and the serial B2 follow-up remains armed after the main Actual wave drains.

May15-21's 28 cases and May22-31's 40 cases have separate dated input and initialization packs. Only B0 is released for these dates, one full Reference -> Actual -> independent Fresh case at a time. Future B1/B2/B3 remain held. The auxiliary lease, separate case/slot locks and natural global resource transfer retain the existing campaign.

May23's weather exclusion is now resolved. Original NOAA rows contain valid same-time altimeter observations that the old decoder ignored when direct pressure fields were missing. The scoped r049 loader derives station pressure from measured altimeter plus source station elevation using the documented standard-atmosphere conversion, then uses the unchanged psychrometric functions. Derived pressure is explicitly distinguished from direct measurement. Raw files, other dates, demand/PV, the 7200-second staleness limit and physical acceptance gates remain unchanged; no temporal interpolation or future observations are used.

**80 focused regressions pass. All 1210 May22-31 observation queries now pass**, including all 121 May23 boundaries. Replaying 13,877 original finite wet-bulb values gives zero difference. The existing monthly controller drained naturally, retained May15/16/17 PASS hashes, restored May23 to the same chronological B0 queue, and resumed real May18 execution. A separate May23 worker admission check passes with zero Native calls/control ticks. This does not claim that May23 Actual/Fresh has completed.

The earlier lazy reference-capture recursion is corrected in immutable r048a by importing the original reference helper before patching. Failed attempts and historical weather-exclusion records remain intact; new attempts and the May23-specific recovery permit preserve their provenance. Preparation still verifies daily native/windows, Planning/Actual bundles, R0 projection, power/traffic/electrical identities, initial Running/MESS contracts and exact event UID joins.

The existing monitor keeps its date x B0/B1/B2/B3 Fresh loading table and address, covers all 31 May dates, and now shows May23 as weather-recovered and waiting. Its refresh preserved all five then-live campaign worker identities. Keep Draft while campaign execution remains unfinished.

Latest evidence: `docs/v44/r049_may23_weather_recovery_20261020/README.md`, `VALIDATION.json`, `MONTH_INPUT_RECHECK.json`, `LIVE_REQUEUE_VERIFIED.json`, `MONITOR_VERIFIED.json`, `SAME_TIME_OBSERVATIONS.json` and `v44_r049_regression_20261020.xml`. Earlier campaign and recovery proof remain in their original directories.
''',encoding='utf-8')
print(json.dumps(dict(copied=len(records),documentation=str(docs)),ensure_ascii=False))
