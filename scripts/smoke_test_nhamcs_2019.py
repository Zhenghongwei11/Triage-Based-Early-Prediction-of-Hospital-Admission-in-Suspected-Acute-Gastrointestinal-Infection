#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SmokeTestConfig:
    dta_path: Path
    output_tsv: Path


CORE_COLUMNS = [
    "AGE",
    "SEX",
    "ARREMS",  # arrival by ambulance/EMS
    "IMMEDR",  # triage immediacy proxy
    "TEMPF",
    "PULSE",
    "RESPR",
    "BPSYS",
    "BPDIAS",
    "POPCT",  # oxygen saturation
    "PAINSCALE",
    "VMONTH",
    "VDAYR",
    "ARRTIME",
    "ADMITHOS",  # admission outcome
]

DIAG_COLUMNS = ["DIAG1", "DIAG2", "DIAG3"]


def _normalize_diag(code: object) -> str:
    if code is None:
        return ""
    return str(code).replace("-", "").strip()


def _cohort_mask(df: pd.DataFrame) -> pd.Series:
    adult = df["AGE"] >= 18
    diag_norm = pd.DataFrame({c: df[c].map(_normalize_diag) for c in DIAG_COLUMNS})
    prefixes = ["A08", "A09", "A04", "K52", "R11", "R19"]
    mask = pd.Series(False, index=df.index)
    for c in diag_norm.columns:
        s = diag_norm[c]
        for p in prefixes:
            mask = mask | s.str.startswith(p)
    return adult & mask


def _negatives_to_nan(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            continue
        if pd.api.types.is_numeric_dtype(out[col]):
            out.loc[out[col] < 0, col] = np.nan
        else:
            out.loc[out[col].astype(str).str.strip().isin(["-9", "-8", "-7"]), col] = np.nan
    return out


def run(cfg: SmokeTestConfig) -> pd.DataFrame:
    df_raw = pd.read_stata(cfg.dta_path.as_posix(), convert_categoricals=False)
    missing_cols = [c for c in CORE_COLUMNS if c not in df_raw.columns]
    if missing_cols:
        raise SystemExit(f"Missing expected columns: {missing_cols}")

    df = _negatives_to_nan(df_raw, CORE_COLUMNS)
    cohort = _cohort_mask(df_raw)

    cohort_df = df.loc[cohort].copy()
    admission_rate = float(cohort_df["ADMITHOS"].mean())

    def miss(col: str) -> float:
        return float(cohort_df[col].isna().mean())

    row = {
        "dataset_id": "NHAMCS_ED_2019",
        "n_total": int(len(df_raw)),
        "n_adult": int((df_raw["AGE"] >= 18).sum()),
        "n_cohort_adult_gi": int(cohort.sum()),
        "event_rate_admission": admission_rate,
        "missing_age": miss("AGE"),
        "missing_sex": miss("SEX"),
        "missing_arrems": miss("ARREMS"),
        "missing_immedr": miss("IMMEDR"),
        "missing_tempf": miss("TEMPF"),
        "missing_pulse": miss("PULSE"),
        "missing_respr": miss("RESPR"),
        "missing_bpsys": miss("BPSYS"),
        "missing_bpdias": miss("BPDIAS"),
        "missing_popct": miss("POPCT"),
        "missing_painscale": miss("PAINSCALE"),
        "missing_arrtime": miss("ARRTIME"),
    }
    out = pd.DataFrame([row])
    cfg.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(cfg.output_tsv, sep="\t", index=False)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dta",
        type=Path,
        default=Path("data/raw/nhamcs/2019/ED2019-stata.dta"),
        help="Path to ED2019 Stata dataset",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("results/dataset_summary.tsv"),
        help="Output TSV path",
    )
    args = ap.parse_args()
    out = run(SmokeTestConfig(dta_path=args.dta, output_tsv=args.out))
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()

