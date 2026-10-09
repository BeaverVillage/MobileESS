# 재현

Python3.11, numpy1.26.4, scipy1.14.1, pandas2.2.3, pyarrow, matplotlib, OpenDSSDirect0.9.4/DSS-Python0.15.7/DSS-CAPI0.14.5.
프로젝트root에서 다음을 실행한다. 기존외부캠페인에쓰는명령은없다.

```powershell
python -B -m ieee8500_v42_aemo.data_binding planning
python -B -m ieee8500_v42_aemo.data_binding actual
python -B -m ieee8500_v42_aemo.run_b0
python -B -m ieee8500_v42_aemo.emergency diagnose
python -B -m ieee8500_v42_aemo.emergency policies
python -B -m ieee8500_v42_aemo.emergency final
python -B -m ieee8500_v42_aemo.sensitivity --final
python -B -m ieee8500_v42_aemo.sensitivity --final --primary
python -B -m ieee8500_v42_aemo.sensitivity --final --peak
python -B -m ieee8500_v42_aemo.verify
python -B -m ieee8500_v42_aemo.report
python -B -m ieee8500_v42_aemo.figures
python -B -m unittest discover -s tests/ieee8500_v42_aemo -v
```

Fullbinding은동일SHA의원본forecastarchives와Kestrel731MBarchive및기존V42bundle경로가필요하다. raw경로는sourcefreezeJSON의content-hash resolver로찾는다. 선택된48/288행과private2498UID projection 및derivedNPZ는저장되어있어AC/CSV/그림/독립검산은그입력으로재현할수있다. 원본Kestrel전행join재실행없이sourceauthority검증을했다고주장하지말것.
OpenDSS sourceinit은매day/stage별독립,96snapshot은연속auto/static정착이다. 원본지연/deadtime을보존하지만각15분slot내정착후의quasi-staticAC이다. subslot전압과실제switch-cyclestress인증은아니다.
일일top20의양단/모든도체및endpoint전압complexphasor를보관하고모든원본노드/선로/CT하드제약배열은완전히보관한다. 나머지fullcomplexphasor는재실행으로생성한다.
현재CAMPAIGNBEFORE/AFTER는이실행의read-only스냅샷이다. 다른환경에서라이브캠페인보존실험을동일상태로재현한다고주장하지않는다.
