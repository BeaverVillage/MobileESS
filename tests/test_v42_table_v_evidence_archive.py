"""Evidence archive checks verify contents, not only a ZIP container hash."""
import shutil
import zipfile

import pytest

from tools.package_v42_table_v_month_evidence import digest_bytes, record, verify, zip_info


def test_archive_verification_survives_relocation_and_checks_entry_bytes(tmp_path):
    archive = tmp_path / "old.zip"
    payload = b"public input proof"
    with zipfile.ZipFile(archive, "x") as stream:
        stream.writestr(zip_info("proof.json"), payload)
    manifest = dict(archive=record(archive), entries=[dict(archive_path="proof.json",
        sha256=digest_bytes(payload), bytes=len(payload))])
    relocated = tmp_path / "relocated.zip"
    shutil.copy2(archive, relocated)
    assert verify(relocated, manifest)["PASS"]
    with zipfile.ZipFile(relocated, "w") as stream:
        stream.writestr(zip_info("proof.json"), b"different proof")
    with pytest.raises(ValueError, match="ARCHIVE_SHA_OR_BYTES"):
        verify(relocated, manifest)
    manifest["archive"] = record(relocated)
    with pytest.raises(ValueError, match="ENTRY_SHA_OR_BYTES"):
        verify(relocated, manifest)


def test_archive_rejects_extra_or_missing_evidence_entries(tmp_path):
    archive = tmp_path / "test.zip"
    with zipfile.ZipFile(archive, "x") as stream:
        stream.writestr(zip_info("unexpected.json"), b"{}")
    with pytest.raises(ValueError, match="ENTRY_MEMBERSHIP"):
        verify(archive, dict(archive=record(archive), entries=[]))
