#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


RAW_DTA_DEFAULT = Path("data/raw/nhamcs/2019/ED2019-stata.dta")
OUT_PARQUET_PRIMARY = Path("data/processed/nhamcs_ed_2019_adult_suspected_gi.parquet")

DIAG_COLUMNS = ["DIAG1", "DIAG2", "DIAG3"]

PHENOTYPES: dict[str, list[str]] = {
    # Primary (main analysis): balances sensitivity + portability; do not call "confirmed infection".
    "primary": ["A08", "A09", "A04", "K52", "R11", "R19"],
    # Infection-only (high specificity)
    "infection_only": ["A08", "A09", "A04"],
    # Intermediate: add presumed infectious GE coding
    "intermediate": ["A08", "A09", "A04", "K52"],
    # Symptom-excluded: exclude R11/R19 symptom codes (same prefixes as intermediate)
    "symptom_excluded": ["A08", "A09", "A04", "K52"],
}


def normalize_diag(code: object) -> str:
    if code is None:
        return ""
    return str(code).replace("-", "").strip().upper()


def any_diag_prefix(df: pd.DataFrame, prefixes: list[str]) -> pd.Series:
    diag_norm = pd.DataFrame({c: df[c].map(normalize_diag) for c in DIAG_COLUMNS})
    mask = pd.Series(False, index=df.index)
    for c in diag_norm.columns:
        s = diag_norm[c]
        for p in prefixes:
            mask = mask | s.str.startswith(p)
    return mask


def parse_arrtime(value: object) -> float:
    if value is None:
        return np.nan
    s = str(value).strip()
    if s in {"-9", "-8", "-7", ""}:
        return np.nan
    if not s.isdigit():
        return np.nan
    s = s.zfill(4)
    hh = int(s[:2])
    mm = int(s[2:])
    if hh > 23 or mm > 59:
        return np.nan
    return float(hh * 60 + mm)


def negatives_to_nan(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series.where(series >= 0, np.nan)
    s = series.astype(str).str.strip()
    return series.where(~s.isin(["-9", "-8", "-7"]), np.nan)


def map_sex_to_binary_male(series: pd.Series) -> pd.Series:
    """
    NHAMCS SEX is commonly coded as:
      1 = Female
      2 = Male
    Map to a portable binary aligned to the MIMIC processing:
      0 = Female, 1 = Male
    Unknown/other values -> NaN.
    """
    s = pd.to_numeric(series, errors="coerce")
    out = pd.Series(np.nan, index=s.index, dtype=float)
    out = out.where(~(s == 1), 0.0)
    out = out.where(~(s == 2), 1.0)
    return out


def map_arrems_to_binary_ems(series: pd.Series) -> pd.Series:
    """
    NHAMCS ARREMS is commonly coded as:
      1 = Arrival by ambulance/EMS
      2 = Other
    Map to a portable binary aligned to the MIMIC processing:
      1 = EMS, 0 = not EMS
    Unknown values -> NaN.
    """
    s = pd.to_numeric(series, errors="coerce")
    out = pd.Series(np.nan, index=s.index, dtype=float)
    out = out.where(~(s == 1), 1.0)
    out = out.where(~(s == 2), 0.0)
    return out


def clean_immediacy(series: pd.Series) -> pd.Series:
    """
    NHAMCS IMMEDR is typically a triage immediacy category in the range 1..5.
    Values outside 1..5 are treated as missing for portability.
    """
    s = pd.to_numeric(series, errors="coerce")
    return s.where(s.between(1, 5), np.nan)


def map_vdayr_to_pandas_dayofweek(series: pd.Series) -> pd.Series:
    """
    NHAMCS VDAYR is commonly coded as:
      1 = Sunday, 2 = Monday, ..., 7 = Saturday
    Pandas dayofweek is:
      0 = Monday, ..., 6 = Sunday
    Mapping: pandas = (VDAYR + 5) % 7
    """
    s = pd.to_numeric(series, errors="coerce")
    s = s.where(s.between(1, 7), np.nan)
    return ((s + 5) % 7).astype(float)


def range_to_nan(x: pd.Series, *, lo: float, hi: float) -> pd.Series:
    s = pd.to_numeric(x, errors="coerce")
    return s.where(s.between(lo, hi), np.nan)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=RAW_DTA_DEFAULT)
    ap.add_argument("--phenotype", choices=sorted(PHENOTYPES.keys()), default="primary")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--counts-out", type=Path, default=None, help="Optional JSON output with cohort flow counts.")
    args = ap.parse_args()

    if args.out is None:
        if args.phenotype == "primary":
            args.out = OUT_PARQUET_PRIMARY
        else:
            args.out = Path(f"data/processed/nhamcs_ed_2019_adult_suspected_gi_{args.phenotype}.parquet")

    df = pd.read_stata(args.raw.as_posix(), convert_categoricals=False)

    required = ["AGE", "SEX", "ADMITHOS", "PATWT", "ARREMS", "IMMEDR", "TEMPF", "PULSE", "RESPR", "BPSYS", "BPDIAS", "POPCT", "PAINSCALE", "VMONTH", "VDAYR", "ARRTIME"] + DIAG_COLUMNS
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing columns in raw file: {missing}")

    adult = df["AGE"] >= 18
    prefixes = PHENOTYPES[args.phenotype]
    suspected_gi = any_diag_prefix(df, prefixes=prefixes)
    cohort = adult & suspected_gi

    out = pd.DataFrame(
        {
            "age": df.loc[cohort, "AGE"].astype(float),
            "sex": map_sex_to_binary_male(df.loc[cohort, "SEX"]),
            "arrems": map_arrems_to_binary_ems(df.loc[cohort, "ARREMS"]),
            "immedr": clean_immediacy(df.loc[cohort, "IMMEDR"]),
            "temp_f_raw": df.loc[cohort, "TEMPF"].astype(float),
            "pulse": df.loc[cohort, "PULSE"].astype(float),
            "resp": df.loc[cohort, "RESPR"].astype(float),
            "sbp": df.loc[cohort, "BPSYS"].astype(float),
            "dbp": df.loc[cohort, "BPDIAS"].astype(float),
            "spo2": df.loc[cohort, "POPCT"].astype(float),
            "pain": df.loc[cohort, "PAINSCALE"].astype(float),
            "month": df.loc[cohort, "VMONTH"].astype(float),
            "day_of_week": map_vdayr_to_pandas_dayofweek(df.loc[cohort, "VDAYR"]),
            "arr_minutes": df.loc[cohort, "ARRTIME"].map(parse_arrtime),
            "admission": df.loc[cohort, "ADMITHOS"].astype(int),
            "sample_weight": df.loc[cohort, "PATWT"].astype(float),
        }
    )

    for col in [
        "age",
        "temp_f_raw",
        "pulse",
        "resp",
        "sbp",
        "dbp",
        "spo2",
        "pain",
        "month",
    ]:
        out[col] = negatives_to_nan(out[col])

    # Temperature is recorded as tenths of degrees Fahrenheit in this file (e.g., 981 == 98.1F).
    # Keep a conservative transform: only scale values that look like tenths.
    out["temp_f"] = out["temp_f_raw"].where(out["temp_f_raw"] < 200, out["temp_f_raw"] / 10.0)

    # Basic physiologic plausibility cleaning (set obvious outliers to missing; imputed later).
    out["temp_f"] = range_to_nan(out["temp_f"], lo=80.0, hi=110.0)
    out["pulse"] = range_to_nan(out["pulse"], lo=20.0, hi=250.0)
    out["resp"] = range_to_nan(out["resp"], lo=4.0, hi=60.0)
    out["sbp"] = range_to_nan(out["sbp"], lo=50.0, hi=250.0)
    out["dbp"] = range_to_nan(out["dbp"], lo=20.0, hi=150.0)
    out["spo2"] = range_to_nan(out["spo2"], lo=50.0, hi=100.0)
    out["pain"] = range_to_nan(out["pain"], lo=0.0, hi=10.0)

    # Simple time-of-day encodings (hour + cyclic)
    out["arr_hour"] = np.floor(out["arr_minutes"] / 60.0)
    out["arr_hour_sin"] = np.sin(2 * np.pi * out["arr_minutes"] / (24.0 * 60.0))
    out["arr_hour_cos"] = np.cos(2 * np.pi * out["arr_minutes"] / (24.0 * 60.0))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    print(f"Phenotype: {args.phenotype} (prefixes={prefixes})")
    print(f"Wrote {len(out):,} rows -> {args.out}")
    print("Admission rate:", out["admission"].mean())

    if args.counts_out is not None:
        counts = {
            "dataset": "NHAMCS_ED",
            "raw_path": str(args.raw),
            "phenotype": args.phenotype,
            "prefixes": prefixes,
            "n_total": int(len(df)),
            "n_adult": int(adult.sum()),
            "n_suspected_gi": int(suspected_gi.sum()),
            "n_adult_suspected_gi": int(cohort.sum()),
            "n_admitted": int(out["admission"].sum()),
        }
        args.counts_out.parent.mkdir(parents=True, exist_ok=True)
        args.counts_out.write_text(json.dumps(counts, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
