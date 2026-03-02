#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phenotype", type=str, default="primary", help="Phenotype name (must be supported by cohort builders).")
    ap.add_argument("--years", nargs="+", type=int, default=list(range(2016, 2023)))
    ap.add_argument("--bootstrap", type=int, default=200)
    ap.add_argument("--use-ext-weights", action="store_true")
    ap.add_argument("--mimic-dev", type=Path, default=Path("data/processed/mimic_iv_ed_adult_suspected_gi.parquet"))
    ap.add_argument("--outroot", type=Path, default=Path("results/external_nhamcs_years"))
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    py = sys.executable

    # Ensure dev cohort exists (rebuild if phenotype != primary).
    dev_path = args.mimic_dev
    if args.phenotype != "primary":
        dev_path = root / f"data/processed/mimic_iv_ed_adult_suspected_gi_{args.phenotype}.parquet"
        run([py, str(root / "scripts/build_mimic_iv_ed_gi_cohort.py"), "--phenotype", args.phenotype, "--out", str(dev_path)])
    if not dev_path.exists():
        run([py, str(root / "scripts/build_mimic_iv_ed_gi_cohort.py"), "--phenotype", "primary", "--out", str(dev_path)])

    ext_paths: list[Path] = []
    for year in args.years:
        raw_dta = root / f"data/raw/nhamcs/{year}/ED{year}-stata.dta"
        if not raw_dta.exists():
            raise SystemExit(f"Missing raw NHAMCS year {year}: {raw_dta}. Download first via scripts/download_nhamcs_ed_years.py")

        ext_path = root / f"data/processed/nhamcs_ed_{year}_adult_suspected_gi_{args.phenotype}.parquet"
        if args.phenotype == "primary":
            ext_path = root / f"data/processed/nhamcs_ed_{year}_adult_suspected_gi.parquet"
        run(
            [
                py,
                str(root / "scripts/build_nhamcs_2019_gi_cohort.py"),
                "--raw",
                str(raw_dta),
                "--phenotype",
                args.phenotype,
                "--out",
                str(ext_path),
            ]
        )
        ext_paths.append(ext_path)

        outdir = root / args.outroot / args.phenotype / str(year)
        train_cmd = [
            py,
            str(root / "scripts/train_mimic_validate_nhamcs.py"),
            "--dev",
            str(dev_path),
            "--ext",
            str(ext_path),
            "--dev-id",
            "MIMIC_IV_ED",
            "--ext-id",
            f"NHAMCS_ED_{year}",
            "--outdir",
            str(outdir),
            "--bootstrap",
            str(args.bootstrap),
        ]
        if args.use_ext_weights:
            train_cmd.append("--use-ext-weights")
        run(train_cmd)

    # Pooled external validation (stack all years)
    pooled = pd.concat([pd.read_parquet(p) for p in ext_paths], ignore_index=True)
    pooled_years = f"{min(args.years)}_{max(args.years)}"
    pooled_path = root / f"data/processed/nhamcs_ed_{pooled_years}_adult_suspected_gi_{args.phenotype}_pooled.parquet"
    pooled.to_parquet(pooled_path, index=False)

    pooled_outdir = root / args.outroot / args.phenotype / f"pooled_{pooled_years}"
    train_cmd = [
        py,
        str(root / "scripts/train_mimic_validate_nhamcs.py"),
        "--dev",
        str(dev_path),
        "--ext",
        str(pooled_path),
        "--dev-id",
        "MIMIC_IV_ED",
        "--ext-id",
        f"NHAMCS_ED_{pooled_years}",
        "--outdir",
        str(pooled_outdir),
        "--bootstrap",
        str(args.bootstrap),
    ]
    if args.use_ext_weights:
        train_cmd.append("--use-ext-weights")
    run(train_cmd)

    print("\nDone.")
    print(f"- Year-specific results: {args.outroot}/{args.phenotype}/<year>/benchmarks/")
    print(f"- Pooled results: {args.outroot}/{args.phenotype}/pooled_{pooled_years}/benchmarks/")


if __name__ == "__main__":
    main()

