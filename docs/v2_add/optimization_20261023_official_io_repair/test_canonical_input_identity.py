import hashlib
from pathlib import Path
import pytest
from canonical_input_identity import canonical_inputs

def test_alias_is_resolved_and_original_lineage_unchanged(tmp_path):
    folder=tmp_path/'folder';folder.mkdir();path=tmp_path/'input';path.write_bytes(b'fixed')
    alias=folder/'..'/'input'
    old=dict(path=str(alias),sha256=hashlib.sha256(b'fixed').hexdigest(),bytes=5)
    def record(p):
        actual=Path(p).resolve();return dict(path=str(actual),sha256=hashlib.sha256(actual.read_bytes()).hexdigest(),bytes=actual.stat().st_size)
    new=canonical_inputs({'x':old},record)
    assert new['x']['path']==str(path.resolve()) and old['path']==str(alias)

@pytest.mark.parametrize('change',['hash','size','resolved_path'])
def test_alias_never_hides_content_or_file_replacement(tmp_path,change):
    path=tmp_path/'input';path.write_bytes(b'fixed')
    expected=dict(path=str(path),sha256='a'*64,bytes=5)
    actual=dict(expected)
    actual[{'hash':'sha256','size':'bytes','resolved_path':'path'}[change]]={'hash':'b'*64,'size':6,'resolved_path':str(tmp_path/'other')}[change]
    with pytest.raises(ValueError,match='INPUT_CONTENT_OR_RESOLVED_PATH_DRIFT'):
        canonical_inputs({'x':expected},lambda p:actual)
