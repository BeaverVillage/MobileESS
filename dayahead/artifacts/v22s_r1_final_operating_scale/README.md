# V22S-R1 final operating-load scale artifacts

이 디렉터리는 `MELBOURNE_INFORMED_EQUIVALENT_12SITE_OPERATING_LOAD_CASE`의 출처 재검증, 사전등록 산술, 형상 정규화, unique-host 분모, IEEE123 등가 PCC scale, site weight 및 interface sizing을 보존한다.

이 case는 실제 2025년 4월 Melbourne 계량부하 전수조사가 아니다. 허용 표현은 **Melbourne-informed equivalent AIDC operating-load scale**이다.

재현:

```text
python dayahead/tools/build_v22sr1_final_operating_scale.py
python dayahead/tools/finalize_v22sr1_final_operating_scale.py
```

ML, forecast, GPU-h, B0–B3, OpenDSS, grid science는 호출하지 않는다.
