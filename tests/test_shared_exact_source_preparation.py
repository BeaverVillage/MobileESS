from pathlib import Path

from pfr.tools.run_pfr_matrix import _prepare_shared_exact_sources


class _FakeExact:
    def __init__(self) -> None:
        self.calls = 0

    def prepare_sources(
        self,
        authority_package_root: Path,
        work: Path,
        *,
        v2038_root: str,
        primary_root: str,
    ) -> dict[str, str]:
        self.calls += 1
        assets = work / "assets"
        tail = work / "tail"
        assets.mkdir()
        tail.mkdir()
        return {
            "assets": str(assets),
            "tail": str(tail),
            "primary": str(Path(primary_root)),
            "v2038_package": str(Path(v2038_root)),
            "authority_package": str(authority_package_root),
        }


def test_exact_sources_are_prepared_once_and_reused_by_day_workers(tmp_path: Path) -> None:
    campaign = tmp_path / "campaign"
    authority = tmp_path / "authority"
    exact_package = tmp_path / "exact"
    primary = tmp_path / "primary"
    for path in (authority, exact_package, primary):
        path.mkdir()
    exact = _FakeExact()

    first = _prepare_shared_exact_sources(
        exact=exact,
        campaign_root=campaign,
        authority_package_root=authority,
        exact_package_root=exact_package,
        primary_root=primary,
        source_commit_sha="a" * 40,
    )
    second = _prepare_shared_exact_sources(
        exact=exact,
        campaign_root=campaign,
        authority_package_root=authority,
        exact_package_root=exact_package,
        primary_root=primary,
        source_commit_sha="a" * 40,
    )

    assert first == second
    assert exact.calls == 1
    assert (campaign / "_SHARED_EXACT_SOURCE_WORK/PREPARED_PATHS.json").is_file()


def test_exact_source_cache_is_invalidated_by_source_identity(tmp_path: Path) -> None:
    campaign = tmp_path / "campaign"
    authority = tmp_path / "authority"
    exact_package = tmp_path / "exact"
    primary = tmp_path / "primary"
    for path in (authority, exact_package, primary):
        path.mkdir()
    exact = _FakeExact()

    for source_sha in ("a" * 40, "b" * 40):
        _prepare_shared_exact_sources(
            exact=exact,
            campaign_root=campaign,
            authority_package_root=authority,
            exact_package_root=exact_package,
            primary_root=primary,
            source_commit_sha=source_sha,
        )

    assert exact.calls == 2
