# V28R2 local April execution commands

Frozen worktree: `/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend`

## 1. 실행 — 터미널 1

아래 한 명령이 전용 WSL 환경 생성, 패키지 설치, source 검증, 30일 실행, 최종 audit를 순서대로 처리합니다.

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend'
./tools/final_campaign/start_2025_april_preflight.sh
```

## 2. 모니터 — 터미널 2

10초마다 같은 화면을 갱신하며 현재 날짜, issue 진행률, 전체 진행률, FAIL 여부만 표시합니다.

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend'
./tools/final_campaign/monitor_2025_april_preflight.sh
```
