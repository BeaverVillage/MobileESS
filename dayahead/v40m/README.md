# V40M authority investigation

This package reads local evidence and writes only
`dayahead/artifacts/v40m_authority72_closure/`. It never imports or executes a
science model, physical replay, electrical generator, or optimizer.

The source worktree is read-only. V40L names are rejected before directory
descent or file reads. The case domain is the existing date/baseline AIDC
execution domain, so a historical Kestrel timestamp or physical node is not
automatically a current-case admission or AIDC allocation authority.

From the isolated worktree at the specified starting commit:

```powershell
python -B -X utf8 -m dayahead.v40m.forensic init
python -B -X utf8 -m dayahead.v40m.forensic census
python -B -X utf8 -m dayahead.v40m.search
python -B -X utf8 -m dayahead.v40m.repair_search
python -B -X utf8 -m dayahead.v40m.inventory_recovery
python -B -X utf8 -m dayahead.v40m.closeout
python -B -X utf8 -m dayahead.v40m.verify
```

The census freezes file paths, sizes and timestamps in a SHA256-bound Parquet
inventory. Every file has a parsed/not-parsed disposition; archive members have
their own census. Content deduplication retains aliases, and case-scoped aliases
are rebound before adjudication. Raw Parquet row numbers are zero-based;
JSON records use JSON pointers. Text hits are navigation evidence only.

`V40M_TYPED_UID_SIGHTINGS.parquet` is the complete typed search result for parsed
content. `V40M_SOURCE_SEARCH_RESULTS.parquet` records source hashes, canonical
aliases and exclusions. The 72-case Parquet ledger has native scalar columns;
its `UID`, `required_authority_type`, `source_SHA256`, `searched_sources` and
`uid_evidence` columns are canonical JSON strings, preserving the nested JSON
ledger without lossy Arrow type coercion.

Search results are bounded to the available local roots. Broken links,
unavailable LFS objects, unsupported formats and excluded unrelated campaigns
are disclosed, not treated as proof that no external authority exists.

The final receipt references the immutable research commit. A subsequent receipt
commit may contain that file; a commit cannot contain its own hash. All science
holds remain in force regardless of closure counts.
