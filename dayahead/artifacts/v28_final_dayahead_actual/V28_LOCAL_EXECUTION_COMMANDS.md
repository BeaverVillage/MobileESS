# V28 local execution commands

Actual WSL worktree: `/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28_final_dayahead_actual`

## A. 로컬 실행 명령

### 1. April execution

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28_final_dayahead_actual'
bash tools/final_campaign/run_2025_april_preflight.sh
```

### 2. April audit

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28_final_dayahead_actual'
bash tools/final_campaign/audit_2025_april_preflight.sh
```

### 3. May freeze

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28_final_dayahead_actual'
bash tools/final_campaign/freeze_2025_may_final.sh
```

### 4. May execution

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28_final_dayahead_actual'
bash tools/final_campaign/run_2025_may_final.sh
```

### 5. May finalization

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28_final_dayahead_actual'
bash tools/final_campaign/finalize_2025_may_science.sh
```

## B. 로컬 모니터링 명령

### 1. April monitoring

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28_final_dayahead_actual'
bash tools/final_campaign/monitor_2025_april_preflight.sh --watch-seconds 10
```

### 2. May monitoring

```bash
cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28_final_dayahead_actual'
bash tools/final_campaign/monitor_2025_may_final.sh --watch-seconds 10
```
