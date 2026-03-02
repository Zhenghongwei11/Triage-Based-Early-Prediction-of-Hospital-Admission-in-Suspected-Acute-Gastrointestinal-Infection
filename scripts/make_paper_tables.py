#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def load_tsv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t")


def format_ci_point(lo: float, hi: float) -> str:
    if pd.isna(lo) or pd.isna(hi):
        return ""
    return f"{lo:.3f}–{hi:.3f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phenotype", type=str, default="primary")
    ap.add_argument("--outdir", type=Path, default=Path("results/paper/tables"))
    args = ap.parse_args()

    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    # Internal + single external (primary phenotype pack)
    pred = Path(f"results/phenotypes/{args.phenotype}/benchmarks/prediction_eval.tsv")
    pred_ci = Path(f"results/phenotypes/{args.phenotype}/benchmarks/prediction_eval_ci.tsv")
    if pred.exists():
        pred_df = load_tsv(pred)
        if pred_ci.exists():
            ci_df = load_tsv(pred_ci)
            pred_df = pred_df.merge(ci_df, on=["dataset_id", "split_or_cohort", "model_name"], how="left")
        pred_df.to_csv(outdir / "performance_primary_phenotype.tsv", sep="\t", index=False)

    # Multi-year external validation (unweighted + weighted sensitivity)
    ext_sum = Path("results/tables/external_nhamcs_years_summary.tsv")
    if ext_sum.exists():
        df = load_tsv(ext_sum)
        df["event_rate"] = df["n_events"] / df["n"]
        df.to_csv(outdir / "external_nhamcs_years_unweighted.tsv", sep="\t", index=False)

        pooled = df.loc[df["run_id"].str.startswith("pooled_")].copy()
        pooled.to_csv(outdir / "external_nhamcs_pooled_unweighted.tsv", sep="\t", index=False)

    ext_w_sum = Path("results/tables/external_nhamcs_years_weighted_summary.tsv")
    if ext_w_sum.exists():
        dfw = load_tsv(ext_w_sum)
        dfw["event_rate"] = dfw["n_events"] / dfw["n"]
        dfw.to_csv(outdir / "external_nhamcs_years_weighted.tsv", sep="\t", index=False)
        pooledw = dfw.loc[dfw["run_id"].str.startswith("pooled_")].copy()
        pooledw.to_csv(outdir / "external_nhamcs_pooled_weighted.tsv", sep="\t", index=False)

    # Compact “Table 2” style summary (AUC + CI by year + pooled)
    if ext_sum.exists():
        df = load_tsv(ext_sum)
        df = df.sort_values(["run_id"])
        df["auc_ci"] = df.apply(lambda r: format_ci_point(r.get("auc_ci_low"), r.get("auc_ci_high")), axis=1)
        df["brier_ci"] = df.apply(lambda r: format_ci_point(r.get("brier_ci_low"), r.get("brier_ci_high")), axis=1)
        keep = [
            "run_id",
            "dataset_id",
            "n",
            "n_events",
            "auc",
            "auc_ci",
            "brier",
            "brier_ci",
            "calibration_slope",
            "calibration_intercept",
        ]
        df[keep].to_csv(outdir / "table2_external_performance_compact.tsv", sep="\t", index=False)

    print(f"Wrote paper tables under {outdir}/")


if __name__ == "__main__":
    main()

