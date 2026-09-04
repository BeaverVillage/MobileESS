import zipfile
from pathlib import Path

from dayahead.aidc_preflight import zip_contract


def test_zip_contract_reports_hive_months_without_extracting(tmp_path: Path) -> None:
    archive = tmp_path / "jobs.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("jobs/year=2025/month=11/a.parquet", b"PAR1")
        output.writestr("jobs/year=2025/month=12/b.parquet", b"PAR1")
    contract = zip_contract(archive)
    assert contract["hive_year_month_partitions"] == ["2025-11", "2025-12"]
    assert contract["member_count"] == 2
