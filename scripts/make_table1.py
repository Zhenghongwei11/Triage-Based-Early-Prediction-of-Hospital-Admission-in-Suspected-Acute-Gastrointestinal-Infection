#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


TABLE1_VARS: list[tuple[str, str]] = [
    ("age", "continuous"),
    ("sex", "binary_male"),
    ("arrems", "binary_ems"),
    ("immedr", "ordinal"),
    ("temp_f", "continuous"),
    ("pulse", "continuous"),
    ("resp", "continuous"),
    ("sbp", "continuous"),
    ("dbp", "continuous"),
    ("spo2", "continuous"),
    ("pain", "continuous"),
]


def describe_var(x: pd.Series, kind: str) -> dict[str, object]:
    x = pd.to_numeric(x, errors="coerce")
    n = int(len(x))
    missing_n = int(x.isna().sum())
    nonmiss = x.dropna()

    out: dict[str, object] = {
        "n": n,
        "missing_n": missing_n,
        "missing_pct": float(missing_n / n) if n else np.nan,
    }

    if kind.startswith("binary"):
        # Assumes 0/1; treat other values as missing.
        b = nonmiss.where(nonmiss.isin([0, 1])).dropna()
        n_nonmissing = int(len(b))
        out["n_nonmissing"] = n_nonmissing
        out["n_1"] = int((b == 1).sum())
        out["pct_1"] = float(out["n_1"] / n_nonmissing) if n_nonmissing else np.nan
        return out

    if len(nonmiss) == 0:
        out.update(
            {
                "n_nonmissing": 0,
                "mean": np.nan,
                "sd": np.nan,
                "median": np.nan,
                "p25": np.nan,
                "p75": np.nan,
            }
        )
        return out

    arr = nonmiss.to_numpy(dtype=float)
    out["n_nonmissing"] = int(len(arr))
    out["mean"] = float(np.mean(arr))
    out["sd"] = float(np.std(arr, ddof=1)) if len(arr) > 1 else np.nan
    out["median"] = float(np.median(arr))
    out["p25"] = float(np.quantile(arr, 0.25))
    out["p75"] = float(np.quantile(arr, 0.75))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", type=Path, required=True, help="Development cohort parquet.")
    ap.add_argument("--ext", type=Path, required=True, help="External validation cohort parquet.")
    ap.add_argument("--dev-id", type=str, default="MIMIC_IV_ED")
    ap.add_argument("--ext-id", type=str, default="NHAMCS_ED_POOLED")
    ap.add_argument("--out", type=Path, default=Path("results/paper/tables/table1_baseline.tsv"))
    args = ap.parse_args()

    dev = pd.read_parquet(args.dev)
    ext = pd.read_parquet(args.ext)

    rows: list[dict[str, object]] = []
    for dataset_id, df in [(args.dev_id, dev), (args.ext_id, ext)]:
        for var, kind in TABLE1_VARS:
            if var not in df.columns:
                s = pd.Series([np.nan] * len(df))
            else:
                s = df[var]
            d = describe_var(s, kind)
            d.update({"dataset_id": dataset_id, "variable": var, "kind": kind})
            rows.append(d)

    out = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, sep="\t", index=False)
    print(f"Wrote {len(out)} rows -> {args.out}")


if __name__ == "__main__":
    main()

