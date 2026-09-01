# V28R2 local April execution commands

Frozen worktree: `/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend`

## 로컬 실행 명령

### 1. April source preparation / verification

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend'
./tools/final_campaign/prepare_2025_april_sources.sh
```

### 2. April full-month execution

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend'
./tools/final_campaign/run_2025_april_preflight.sh
```

### 3. April audit

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend'
./tools/final_campaign/audit_2025_april_preflight.sh
```

### 4. April one-time status check

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend'
./tools/final_campaign/monitor_2025_april_preflight.sh --once
```

## 로컬 모니터링 명령

### 5. April continuous monitoring

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend'
./tools/final_campaign/monitor_2025_april_preflight.sh --watch-seconds 30
```
