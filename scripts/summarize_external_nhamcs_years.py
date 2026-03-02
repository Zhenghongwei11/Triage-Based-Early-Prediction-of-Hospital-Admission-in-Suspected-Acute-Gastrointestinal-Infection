#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("results/external_nhamcs_years"))
    ap.add_argument("--out", type=Path, default=Path("results/tables/external_nhamcs_years_summary.tsv"))
    args = ap.parse_args()

    rows: list[pd.DataFrame] = []
    for pheno_dir in sorted(p for p in args.root.glob("*") if p.is_dir()):
        pheno = pheno_dir.name
        for run_dir in sorted(p for p in pheno_dir.glob("*") if p.is_dir()):
            pred = run_dir / "benchmarks/prediction_eval.tsv"
            pred_ci = run_dir / "benchmarks/prediction_eval_ci.tsv"
            if not pred.exists():
                continue
            pred_df = pd.read_csv(pred, sep="\t")
            pred_df.insert(0, "phenotype", pheno)
            pred_df.insert(1, "run_id", run_dir.name)
            pred_df = pred_df.loc[pred_df["split_or_cohort"] == "external_validation"].copy()

            if pred_ci.exists():
                ci_df = pd.read_csv(pred_ci, sep="\t")
                ci_df = ci_df.loc[ci_df["split_or_cohort"] == "external_validation"].copy()
                ci_df = ci_df.drop(columns=["split_or_cohort"], errors="ignore")
                pred_df = pred_df.merge(ci_df, on=["dataset_id", "model_name"], how="left", suffixes=("", "_ci"))

            rows.append(pred_df)

    if not rows:
        raise SystemExit(f"No runs found under {args.root}")

    out = pd.concat(rows, ignore_index=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, sep="\t", index=False)
    print(f"Wrote {len(out)} rows -> {args.out}")


if __name__ == "__main__":
    main()

