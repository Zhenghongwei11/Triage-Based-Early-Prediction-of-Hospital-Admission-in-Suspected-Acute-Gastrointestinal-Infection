#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path


NHAMCS_STATA_BASE = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/dataset_documentation/nhamcs/stata"
NHAMCS_DOC_BASE = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/dataset_documentation/nhamcs"


@dataclass(frozen=True)
class DownloadResult:
    year: int
    zip_path: Path
    dta_path: Path
    doc_path: Path | None


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def http_status(url: str) -> int:
    # Use curl for a fast HEAD check (works consistently for ftp.cdc.gov https directory listings).
    p = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "-I", url],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        return int(p.stdout.strip() or "0")
    except ValueError:
        return 0


def pick_doc_url(year: int) -> str | None:
    yy = str(year)[2:]
    candidates = [
        f"{NHAMCS_DOC_BASE}/doc{yy}-ed-508.pdf",
        f"{NHAMCS_DOC_BASE}/doc{yy}_ed-508.pdf",
        f"{NHAMCS_DOC_BASE}/doc{yy}_ed.pdf",
        f"{NHAMCS_DOC_BASE}/doc{yy}-ed.pdf",
        # Known historical naming
        f"{NHAMCS_DOC_BASE}/doc{yy}_ed.pdf",  # e.g., doc16_ed.pdf
    ]
    for url in candidates:
        if http_status(url) == 200:
            return url
    return None


def download_year(year: int, *, raw_root: Path) -> DownloadResult:
    out_dir = raw_root / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    zip_name = f"ED{year}-stata.zip"
    zip_url = f"{NHAMCS_STATA_BASE}/{zip_name}"
    zip_path = out_dir / zip_name

    # Resume-safe download.
    run(["curl", "-L", "--fail", "--retry", "3", "--retry-delay", "2", "-C", "-", "-o", str(zip_path), zip_url])

    # Extract.
    run(["unzip", "-q", "-o", str(zip_path), "-d", str(out_dir)])
    dta_path = out_dir / f"ED{year}-stata.dta"
    if not dta_path.exists():
        raise SystemExit(f"Expected extracted file not found: {dta_path}")

    doc_url = pick_doc_url(year)
    doc_path = None
    if doc_url:
        doc_name = doc_url.split("/")[-1]
        doc_path = out_dir / doc_name
        run(["curl", "-L", "--fail", "--retry", "3", "--retry-delay", "2", "-C", "-", "-o", str(doc_path), doc_url])

    return DownloadResult(year=year, zip_path=zip_path, dta_path=dta_path, doc_path=doc_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=list(range(2016, 2023)),
        help="NHAMCS ED years to download (default: 2016..2022).",
    )
    ap.add_argument("--raw-root", type=Path, default=Path("data/raw/nhamcs"))
    args = ap.parse_args()

    results: list[DownloadResult] = []
    for y in args.years:
        print(f"Downloading NHAMCS ED {y} ...")
        results.append(download_year(y, raw_root=args.raw_root))

    print("\nDone.")
    for r in results:
        doc = r.doc_path.name if r.doc_path else "(no doc found)"
        print(f"- {r.year}: {r.dta_path} (doc={doc})")


if __name__ == "__main__":
    main()

