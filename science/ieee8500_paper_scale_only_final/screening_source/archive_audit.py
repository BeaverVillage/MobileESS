"""Stream selected paper evidence from the user's raw-results archive without extracting."""
import hashlib
import json
import tarfile
import time
from pathlib import Path

from forensic import HERE, ROOT, sha

ARCHIVE = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\IEEE8500_MAY01_MESS6_RAW_RESULTS_20260914_151641.tar.gz")
TARGET_SUFFIXES = (
    "independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913/actual/B0/FINAL_ACTUAL/AC_SUMMARY.json",
    "independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913/actual/B1/FINAL_ACTUAL/AC_SUMMARY.json",
    "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913/actual_B2/B2/ETA95_ACTUAL/AC_SUMMARY.json",
    "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913/actual_B3_energy_exception_20260914/B3/FINAL_ACTUAL/AC_SUMMARY.json",
    "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913/RESULT_WITH_ENERGY_EXCEPTION.json",
    "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913/PCC_OVERLAY_INVENTORY.json",
    "independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913/MAPPING_FREEZE.json",
)


def main():
    start = time.monotonic()
    targets = set(TARGET_SUFFIXES)
    found = []
    count = 0
    with tarfile.open(ARCHIVE, "r|gz") as archive:
        for member in archive:
            count += 1
            if member.name not in targets:
                continue
            stream = archive.extractfile(member)
            assert stream is not None
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
            disk = ROOT / member.name
            row = {"member": member.name, "archive_sha256": digest.hexdigest(),
                   "disk_sha256": sha(disk) if disk.is_file() else None,
                   "bytes": member.size}
            row["identical"] = row["archive_sha256"] == row["disk_sha256"]
            found.append(row)
            print("ARCHIVE_MATCH" if row["identical"] else "ARCHIVE_DIFF", member.name, flush=True)
            if len(found) == len(targets):
                break
    result = {"archive": str(ARCHIVE), "archive_bytes": ARCHIVE.stat().st_size,
              "members_examined": count, "seconds": time.monotonic() - start,
              "matched": len(found), "requested": len(targets),
              "all_identical": len(found) == len(targets) and all(r["identical"] for r in found),
              "files": found}
    (HERE / "RAW_ARCHIVE_AUDIT.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("ARCHIVE_AUDIT", result["all_identical"], count, flush=True)


if __name__ == "__main__":
    main()
