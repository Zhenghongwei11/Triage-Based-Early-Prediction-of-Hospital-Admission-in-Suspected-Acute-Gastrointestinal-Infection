#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("results/phenotypes"))
    ap.add_argument("--out", type=Path, default=Path("results/tables/phenotype_performance_summary.tsv"))
    args = ap.parse_args()

    rows: list[pd.DataFrame] = []
    for pheno_dir in sorted(p for p in args.root.glob("*") if p.is_dir()):
        pheno = pheno_dir.name
        pred = pheno_dir / "benchmarks/prediction_eval.tsv"
        pred_ci = pheno_dir / "benchmarks/prediction_eval_ci.tsv"
        cohort = pheno_dir / "tables/cohort_summary.tsv"
        if not (pred.exists() and cohort.exists()):
            continue

        pred_df = pd.read_csv(pred, sep="\t")
        pred_df.insert(0, "phenotype", pheno)

        cohort_df = pd.read_csv(cohort, sep="\t")
        cohort_df.insert(0, "phenotype", pheno)

        merged = pred_df.merge(
            cohort_df[["phenotype", "dataset_id", "n", "n_events", "event_rate"]],
            on=["phenotype", "dataset_id"],
            how="left",
            suffixes=("", "_cohort"),
        )

        if pred_ci.exists():
            ci_df = pd.read_csv(pred_ci, sep="\t")
            ci_df.insert(0, "phenotype", pheno)
            merged = merged.merge(
                ci_df,
                on=["phenotype", "dataset_id", "split_or_cohort", "model_name"],
                how="left",
                suffixes=("", "_ci"),
            )

        rows.append(merged)

    if not rows:
        raise SystemExit(f"No phenotype results found under {args.root}")

    out = pd.concat(rows, ignore_index=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, sep="\t", index=False)
    print(f"Wrote {len(out)} rows -> {args.out}")


if __name__ == "__main__":
    main()

