# CC4 forensic audit tools

`verify_package.py` is the portable, read-only verifier for the published audit.
It uses Python's standard library and does not import project execution code.

`original_run/` preserves the five original September 22 audit scripts without
modification. These are historical analysis provenance, not portable entry
points: they assume the original adjacent evidence tree, source checkout and
Windows archive location. Do not invoke them against the repository snapshot.
The analysis scripts used pandas/numpy/pyarrow for stored artifacts; they did
not import or execute the scheduling, OpenDSS, or ML models. Source inspection
and report construction were separate from that data analysis.

To repeat the original full audit, provision a separate audit workspace with
the hash-verified archive, matching execution source, and its original evidence
layout, then deliberately adapt the historical paths in working copies.
The raw archive and existing experiment artifacts must remain read-only.
The saved receipts are evidence of the completed original run; the package
verifier independently validates what is committed without claiming a new
full archive audit.
