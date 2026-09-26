# Research workspace storage cleanup, September 23–24, 2026

The D: research workspace was running out of space. The completed cleanup removed verified duplicate deliverables, selected obsolete intermediate files, Python bytecode, and downloaded package archives while retaining research inputs, runtime code, installed environments, and final raw results.

This directory archives the cleanup evidence. The cleanup happened locally before this PR; merging this documentation does not delete files. Recorded paths and free-space measurements describe that machine at the recorded time, not its current state. Do not use the historical candidate lists as a new deletion plan.

## Completed work

| Phase | Files removed | Logical bytes removed | Evidence |
| --- | ---: | ---: | --- |
| Initial Windows cleanup | 41,611 | 27,960,616,140 | `evidence/cleanup_verification.json` |
| WSL duplicate archive and pip downloads | 243 | 2,277,908,645 | `evidence/wsl_compaction_summary.json` |
| Selected RESITING/ALIGNED full/bounds intermediates | 384 | 6,911,520,296 | `evidence/additional_cleanup_result_20260924.json` |
| Conda downloaded package archives | 91 | 322,883,821 | `evidence/additional_conda_cleanup_result_20260924.json` |

The initial Windows cleanup comprised 10 verified C: backup duplicates, 770 obsolete matrix files, 4,422 obsolete candidate-cache files, 36,408 regenerable Python bytecode files, and one superseded incomplete archive.

WSL compaction reduced the VHDX from 590,898,790,400 to 588,572,000,256 bytes after restart: 2.17 GiB. WSL logical deletion and VHDX reduction must not be added together. The preserved delivery-archive path became a hard link to the identical original; writes through either path affect the same file.

The final September 24 measurement was **124,849,741,824 bytes (116.28 GiB) free on D:**. The last Windows phase increased measured free space by 6.44 GiB. Conda cleanup freed approximately 0.30 GiB inside WSL; a second VHDX compaction was not performed. Free-space measurements include effects of concurrent filesystem activity and differ from logical file-size sums.

## Preservation evidence and limits

- Initial Windows verification compared existence, size, and modification times for 32,243 final-source files and 3,412 retained staging files. These were metadata comparisons, not full-content hashes.
- The final IEEE8500 May01 BG0552/AIDC240/MESS200 and IEEE123 B3 second-round raw archives were retained under the C: results folder. Earlier SHA256 verification records are included; the September 24 follow-up checked their existence and sizes without rehashing the archives.
- WSL restart verification passed 14 protected-file SHA256 checks and eight large-input path/size checks.
- The additional matrix cleanup retained 670 files with matching before/after SHA256 values. Each of its two directories retained 194 solver runtime files: `active_*.npz`, `active_data_*.npz`, `PCC_IMPLIED_BOUNDS.npz`, and `CERTIFICATE.json`. Other retained files included `rhs_*.npy` and Python source.
- Source inspection found that `prepare()` creates the removed full/bounds matrices and derives the retained active matrices; `add_grid()` loads the retained runtime matrices. Direct reinspection of removed intermediate proof data requires regeneration. The broader old-matrix inventory was not deleted because other experiments still reference it.
- Conda cleanup preserved 367 extracted package directories and the hashes of 379 installed-package metadata files. Research-environment imports of NumPy, pandas, SciPy, and PyTorch passed; CUDA availability was true.
- No full research simulation was rerun. These checks establish the documented file preservation and environment probes, not an end-to-end guarantee for every future experiment.

Runtime inputs, weather caches, frozen research artifacts, compatibility paths, and the final IEEE8500 campaign were excluded. The 12.75 GiB temporary solver-model candidate and remaining referenced candidate caches were deferred. `D:\ChatGPT` and the Codex workspace are research workspaces, not merely chat transcripts.

## Included records

`evidence/` contains selected original reports, deletion records, preservation hashes, and verification summaries. `evidence_manifest.json` records the size and SHA256 of each copied record, relative to this directory. The manifest verifies the archived records themselves; it does not revalidate research files on another machine.

The complete local audit remains at `D:\ChatGPT\Mobile ESS 2\storage_audit_20260923`. Broad inventories, the large initial per-file snapshots, and machine-specific deletion/compaction executables are not included. The initial phase is represented by its verification summary and duplicate-deliverable log; the later 384-file matrix phase includes its complete deletion log and 670-file preservation snapshot.
