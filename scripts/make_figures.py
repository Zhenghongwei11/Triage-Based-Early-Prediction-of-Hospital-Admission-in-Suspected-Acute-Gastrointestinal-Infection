#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def make_auc_by_year(summary_tsv: Path, out_png: Path, *, pooled_label: str | None = None) -> None:
    df = pd.read_csv(summary_tsv, sep="\t")
    df = df.loc[df["phenotype"] == "primary"].copy()
    df["is_pooled"] = df["run_id"].astype(str).str.startswith("pooled_")
    by_year = df.loc[~df["is_pooled"]].copy()
    pooled = df.loc[df["is_pooled"]].copy()

    by_year["year"] = by_year["run_id"].astype(int)
    by_year = by_year.sort_values("year")

    y = by_year["auc"].astype(float).to_numpy()
    yerr_lo = y - by_year["auc_ci_low"].astype(float).to_numpy()
    yerr_hi = by_year["auc_ci_high"].astype(float).to_numpy() - y

    plt.figure(figsize=(7.5, 4.5))
    plt.errorbar(by_year["year"], y, yerr=[yerr_lo, yerr_hi], fmt="o-", capsize=3, label="NHAMCS yearly external AUC")

    if len(pooled):
        p = pooled.iloc[0]
        label = pooled_label if pooled_label is not None else f"Pooled {p['run_id']} AUC"
        plt.axhline(float(p["auc"]), linestyle="--", linewidth=1.5, label=label)

    plt.ylim(0.5, 0.95)
    plt.xlabel("NHAMCS year")
    plt.ylabel("AUC (95% CI)")
    plt.title("External validation discrimination across NHAMCS years")
    plt.grid(True, alpha=0.3)
    plt.legend(frameon=False)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()


def make_calibration_plot(
    calib_bins_tsv: Path,
    *,
    dev_id: str,
    ext_id: str,
    dev_label: str | None,
    ext_label: str | None,
    out_png: Path,
) -> None:
    df = pd.read_csv(calib_bins_tsv, sep="\t")

    def plot_one(dataset_id: str, label: str) -> None:
        sub = df.loc[df["dataset_id"] == dataset_id].copy()
        sub = sub.sort_values("bin")
        plt.plot(sub["mean_pred"], sub["event_rate"], marker="o", linewidth=1.5, label=label)

    plt.figure(figsize=(5.5, 5.5))
    xs = [0, 1]
    plt.plot(xs, xs, color="black", linewidth=1, alpha=0.6, label="Ideal")
    plot_one(dev_id, dev_label if dev_label is not None else f"{dev_id} (internal OOF)")
    plot_one(ext_id, ext_label if ext_label is not None else f"{ext_id} (external)")
    plt.xlim(0, 1)
    plt.ylim(0, 1)
    plt.xlabel("Mean predicted probability (by decile)")
    plt.ylabel("Observed event rate (by decile)")
    plt.title("Calibration (binned)")
    plt.grid(True, alpha=0.3)
    plt.legend(frameon=False, fontsize=8)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()


def make_dca_plot(decision_curve_tsv: Path, *, dataset_id: str, title: str | None, out_png: Path) -> None:
    df = pd.read_csv(decision_curve_tsv, sep="\t")
    df = df.loc[(df["dataset_id"] == dataset_id) & (df["split_or_cohort"] == "external_validation")].copy()

    plt.figure(figsize=(7.0, 4.5))
    for model_name, label, style in [
        ("elasticnet_logistic_cv", "Model", "-"),
        ("treat_all", "Treat all", "--"),
        ("treat_none", "Treat none", ":"),
    ]:
        sub = df.loc[df["model_name"] == model_name].sort_values("threshold")
        if len(sub) == 0:
            continue
        plt.plot(sub["threshold"], sub["net_benefit"], style, linewidth=2 if model_name == "elasticnet_logistic_cv" else 1.5, label=label)

    plt.axhline(0, color="black", linewidth=0.8, alpha=0.5)
    plt.xlabel("Threshold probability")
    plt.ylabel("Net benefit")
    plt.title(title if title is not None else f"Decision curve analysis (external): {dataset_id}")
    plt.grid(True, alpha=0.3)
    plt.legend(frameon=False)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=Path, default=Path("results/paper/figures"))
    ap.add_argument("--summary", type=Path, default=Path("results/tables/external_nhamcs_years_summary.tsv"))
    ap.add_argument(
        "--pooled-run-dir",
        type=Path,
        default=Path("results/external_nhamcs_years/primary/pooled_2016_2022"),
        help="Folder containing pooled benchmarks (calibration_bins.tsv, decision_curve.tsv).",
    )
    ap.add_argument("--dev-id", type=str, default="MIMIC_IV_ED")
    ap.add_argument("--ext-id", type=str, default="NHAMCS_ED_2016_2022")
    ap.add_argument("--dev-label", type=str, default=None, help="Optional plot label for development cohort.")
    ap.add_argument("--ext-label", type=str, default=None, help="Optional plot label for external cohort.")
    ap.add_argument("--pooled-label", type=str, default=None, help="Optional plot label for pooled AUC reference line.")
    ap.add_argument("--dca-title", type=str, default=None, help="Optional plot title for decision curve analysis figure.")
    args = ap.parse_args()

    ensure_dir(args.outdir)
    make_auc_by_year(args.summary, args.outdir / "auc_by_year.png", pooled_label=args.pooled_label)

    calib_bins = args.pooled_run_dir / "benchmarks/calibration_bins.tsv"
    if calib_bins.exists():
        make_calibration_plot(
            calib_bins,
            dev_id=args.dev_id,
            ext_id=args.ext_id,
            dev_label=args.dev_label,
            ext_label=args.ext_label,
            out_png=args.outdir / "calibration_binned_pooled.png",
        )

    dca = args.pooled_run_dir / "benchmarks/decision_curve.tsv"
    if dca.exists():
        make_dca_plot(dca, dataset_id=args.ext_id, title=args.dca_title, out_png=args.outdir / "dca_external_pooled.png")

    print(f"Wrote figures under {args.outdir}/")


if __name__ == "__main__":
    main()
