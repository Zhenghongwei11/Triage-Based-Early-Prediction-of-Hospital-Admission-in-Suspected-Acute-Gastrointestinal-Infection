#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mode",
        choices=["quick", "recompute_external"],
        default="quick",
        help=(
            "quick: regenerate paper tables/figures from existing derived results only. "
            "recompute_external: re-run NHAMCS yearly + pooled external validation (requires NHAMCS raw downloads and MIMIC dev cohort)."
        ),
    )
    ap.add_argument("--phenotype", type=str, default="primary")
    ap.add_argument("--bootstrap", type=int, default=200, help="Bootstrap replicates for external validation (recompute_external mode only).")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    py = sys.executable

    if args.mode == "recompute_external":
        run(
            [
                py,
                str(root / "scripts/run_external_validation_nhamcs_years.py"),
                "--phenotype",
                args.phenotype,
                "--bootstrap",
                str(args.bootstrap),
            ]
        )

    # Paper-facing tables/figures (from results/*)
    run([py, str(root / "scripts/make_paper_tables.py"), "--phenotype", args.phenotype])
    run([py, str(root / "scripts/make_figures.py")])

    print("\nDone.")
    print("- Figures: results/paper/figures/")
    print("- Tables: results/paper/tables/")


if __name__ == "__main__":
    main()

