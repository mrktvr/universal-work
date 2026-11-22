#!/usr/bin/env python3
"""Check the source ZIP claims in the Universal Work release QA example."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile


def check_archive(report_path, archive_path):
    with report_path.open("rb") as report_file:
        data = report_file.read(64 * 1024 + 1)
    if len(data) > 64 * 1024:
        raise ValueError("The QA report exceeds 64 KiB.")
    report = json.loads(data.decode("utf-8-sig"))
    if not isinstance(report, dict):
        raise ValueError("Expected a JSON report object.")
    digest = hashlib.sha256()
    with archive_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
        checks = {
            "archive_name": report.get("archive_name") == archive_path.name,
            "sha256": report.get("sha256") == digest.hexdigest(),
            "archive_files": None, "commit_comment": None, "archive_integrity": None,
        }
        if checks["archive_name"] and checks["sha256"]:
            source.seek(0)
            with ZipFile(source) as archive:
                entries = [entry for entry in archive.infolist() if not entry.is_dir()]
                if sum(entry.file_size for entry in entries) > 64 * 1024 * 1024:
                    raise ValueError("This example checks up to 64 MiB of uncompressed ZIP entries.")
                checks["archive_files"] = (
                    type(report.get("archive_files")) is int and report["archive_files"] == len(entries)
                )
                checks["commit_comment"] = report.get("commit") == archive.comment.decode("utf-8").strip()
                checks["archive_integrity"] = archive.testzip() is None and report.get("archive_integrity") == "pass"
    return {"ok": all(checks.values()), "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        result = check_archive(args.report, args.archive)
    except (OSError, ValueError, BadZipFile, RuntimeError, NotImplementedError) as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
