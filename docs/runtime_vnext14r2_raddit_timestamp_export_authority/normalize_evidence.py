"""Preserve verbatim extracts locally before normalizing quoted line-tail spaces."""
from common import *
for name in ['LOCAL_INTERMEDIATE_ARTIFACT_SEARCH.csv', 'NOTEBOOK_PROVENANCE_EVIDENCE.csv']:
    original = LOCAL/(name+'.verbatim.csv')
    if not original.exists():
        original.write_bytes((ROOT/name).read_bytes())
    rows = pd.read_csv(original, dtype=str, keep_default_na=False).to_dict('records')
    table(name, rows)
write('EVIDENCE_FORMATTING_RECEIPT.json', dict(
    operation='Strip spaces/tabs only at each quoted-text line end; no content or source file mutation',
    verbatim_extracts=[rec(LOCAL/(name+'.verbatim.csv')) for name in
                      ['LOCAL_INTERMEDIATE_ARTIFACT_SEARCH.csv', 'NOTEBOOK_PROVENANCE_EVIDENCE.csv']],
    original_sources_unchanged=True))
