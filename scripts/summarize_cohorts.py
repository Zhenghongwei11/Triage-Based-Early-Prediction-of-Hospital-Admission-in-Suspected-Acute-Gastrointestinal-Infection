#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


FEATURES = [
    "age",
    "sex",
    "arrems",
    "immedr",
    "temp_f",
    "pulse",
    "resp",
    "sbp",
    "dbp",
    "spo2",
    "pain",
    "month",
    "day_of_week",
    "arr_hour_sin",
    "arr_hour_cos",
]


def _describe_numeric(x: pd.Series) -> dict[str, float]:
    x = pd.to_numeric(x, errors="coerce")
    return {
        "mean": float(np.nanmean(x.to_numpy(dtype=float))),
        "sd": float(np.nanstd(x.to_numpy(dtype=float), ddof=1)),
        "median": float(np.nanmedian(x.to_numpy(dtype=float))),
        "p25": float(np.nanquantile(x.to_numpy(dtype=float), 0.25)),
        "p75": float(np.nanquantile(x.to_numpy(dtype=float), 0.75)),
        "missing_rate": float(x.isna().mean()),
    }


def cohort_row(dataset_id: str, df: pd.DataFrame) -> dict[str, object]:
    y = df["admission"].astype(int)
    out: dict[str, object] = {
        "dataset_id": dataset_id,
        "n": int(len(df)),
        "n_events": int(y.sum()),
        "event_rate": float(y.mean()),
    }
    out["age_mean"] = _describe_numeric(df["age"])["mean"]
    out["age_sd"] = _describe_numeric(df["age"])["sd"]
    out["male_rate"] = float(pd.to_numeric(df["sex"], errors="coerce").mean())
    out["ems_rate"] = float(pd.to_numeric(df["arrems"], errors="coerce").mean())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", type=Path, default=Path("data/processed/mimic_iv_ed_adult_suspected_gi.parquet"))
    ap.add_argument("--ext", type=Path, default=Path("data/processed/nhamcs_ed_2019_adult_suspected_gi.parquet"))
    ap.add_argument("--dev-id", type=str, default="MIMIC_IV_ED")
    ap.add_argument("--ext-id", type=str, default="NHAMCS_ED")
    ap.add_argument("--outdir", type=Path, default=Path("results/tables"))
    args = ap.parse_args()

    dev = pd.read_parquet(args.dev)
    ext = pd.read_parquet(args.ext)

    for name, df in [("dev", dev), ("ext", ext)]:
        if "admission" not in df.columns:
            raise SystemExit(f"{name} dataset missing admission")
        for f in FEATURES:
            if f not in df.columns:
                df[f] = np.nan

    args.outdir.mkdir(parents=True, exist_ok=True)

    summary = pd.DataFrame(
        [
            cohort_row(args.dev_id, dev),
            cohort_row(args.ext_id, ext),
        ]
    )
    summary.to_csv(args.outdir / "cohort_summary.tsv", sep="\t", index=False)

    miss_rows = []
    for dataset_id, df in [("MIMIC_IV_ED", dev), ("NHAMCS_ED_2019", ext)]:
        for f in FEATURES:
            miss_rows.append(
                {
                    "dataset_id": dataset_id,
                    "feature": f,
                    "missing_rate": float(pd.to_numeric(df[f], errors="coerce").isna().mean()),
                }
            )
    pd.DataFrame(miss_rows).to_csv(args.outdir / "feature_missingness.tsv", sep="\t", index=False)

    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
