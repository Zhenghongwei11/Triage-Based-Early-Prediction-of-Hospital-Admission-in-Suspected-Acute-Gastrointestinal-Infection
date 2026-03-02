#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


FEATURES_OUT = [
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

PHENOTYPES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # (icd10_prefixes, icd9_prefixes)
    "primary": (("A08", "A09", "A04", "K52", "R11", "R19"), ("008", "009", "558", "7870", "7879", "78791")),
    "infection_only": (("A08", "A09", "A04"), ("008", "009")),
    "intermediate": (("A08", "A09", "A04", "K52"), ("008", "009", "558")),
    "symptom_excluded": (("A08", "A09", "A04", "K52"), ("008", "009", "558")),
}


def _find_one(root: Path, pattern: str) -> Path:
    matches = sorted(root.glob(pattern))
    if not matches:
        raise SystemExit(f"Could not find file matching {pattern!r} under {root}")
    return matches[0]


def _normalize_icd(code: object) -> str:
    if code is None:
        return ""
    return str(code).replace(".", "").replace("-", "").strip().upper()


def _gi_prefix_mask(icd: pd.Series, prefixes: tuple[str, ...]) -> pd.Series:
    s = icd.map(_normalize_icd)
    m = pd.Series(False, index=s.index)
    for p in prefixes:
        m = m | s.str.startswith(p)
    return m


def _gi_icd9_prefix_mask(icd: pd.Series, prefixes: tuple[str, ...]) -> pd.Series:
    s = icd.map(_normalize_icd)
    m = pd.Series(False, index=s.index)
    for p in prefixes:
        m = m | s.str.startswith(p)
    return m


def _map_sex(x: object) -> float:
    if x is None:
        return np.nan
    s = str(x).strip().upper()
    if s in {"M", "MALE", "1"}:
        return 1.0
    if s in {"F", "FEMALE", "0"}:
        return 0.0
    return np.nan


def _safe_col(df: pd.DataFrame, *names: str) -> str | None:
    for n in names:
        if n in df.columns:
            return n
    return None


def _time_features(dt: pd.Series) -> pd.DataFrame:
    dt = pd.to_datetime(dt, errors="coerce")
    minutes = (dt.dt.hour * 60 + dt.dt.minute).astype(float)
    out = pd.DataFrame(
        {
            "month": dt.dt.month.astype(float),
            "day_of_week": dt.dt.dayofweek.astype(float),
            "arr_minutes": minutes,
        }
    )
    out["arr_hour_sin"] = np.sin(2 * np.pi * out["arr_minutes"] / (24.0 * 60.0))
    out["arr_hour_cos"] = np.cos(2 * np.pi * out["arr_minutes"] / (24.0 * 60.0))
    return out


def _range_to_nan(x: pd.Series, *, lo: float, hi: float) -> pd.Series:
    s = pd.to_numeric(x, errors="coerce")
    return s.where(s.between(lo, hi), np.nan)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data/raw/mimic-iv-ed"))
    ap.add_argument(
        "--mimic-core-root",
        type=Path,
        default=Path("data/raw/mimic-iv"),
        help="Root folder for MIMIC-IV (core) to derive age from hosp/patients.csv.gz (anchor_age/year).",
    )
    ap.add_argument("--phenotype", choices=sorted(PHENOTYPES.keys()), default="primary")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--counts-out", type=Path, default=None, help="Optional JSON output with cohort flow counts.")
    ap.add_argument("--chunksize", type=int, default=1_000_000)
    args = ap.parse_args()

    if args.out is None:
        if args.phenotype == "primary":
            args.out = Path("data/processed/mimic_iv_ed_adult_suspected_gi.parquet")
        else:
            args.out = Path(f"data/processed/mimic_iv_ed_adult_suspected_gi_{args.phenotype}.parquet")

    root: Path = args.root
    edstays_path = _find_one(root, "**/edstays.csv*")
    triage_path = _find_one(root, "**/triage.csv*")
    diagnosis_path = _find_one(root, "**/diagnosis.csv*")

    edstays_cols = ["stay_id", "subject_id", "intime", "hadm_id", "disposition", "arrival_transport", "gender"]
    edstays = pd.read_csv(edstays_path, usecols=lambda c: c in edstays_cols)
    if "stay_id" not in edstays.columns:
        raise SystemExit("edstays is missing stay_id")
    if "intime" not in edstays.columns:
        raise SystemExit("edstays is missing intime")

    # Derive age from MIMIC-IV core patients table (anchor_age + anchor_year).
    # This avoids relying on age-in-triage, which is not present in MIMIC-IV-ED.
    try:
        patients_path = _find_one(args.mimic_core_root, "**/hosp/patients.csv*")
    except SystemExit as e:
        raise SystemExit(
            f"{e}\n\nTo build an adult cohort, download MIMIC-IV (core) and place it under {args.mimic_core_root}.\n"
            "For a dry-run using open demos, pass --mimic-core-root data/raw/mimic-iv-demo/2.2/mimic-iv-clinical-database-demo-2.2"
        )
    patients = pd.read_csv(patients_path, usecols=["subject_id", "anchor_age", "anchor_year"])

    triage = pd.read_csv(triage_path)
    stay_col = _safe_col(triage, "stay_id", "ed_stay_id")
    if stay_col is None:
        raise SystemExit("triage file has no stay_id-like column")
    if stay_col != "stay_id":
        triage = triage.rename(columns={stay_col: "stay_id"})

    # Identify adult suspected GI stays via diagnosis codes (chunked for memory safety).
    icd10_prefixes, icd9_prefixes = PHENOTYPES[args.phenotype]
    gi_stays: set[int] = set()
    for chunk in pd.read_csv(diagnosis_path, chunksize=args.chunksize):
        stay_id_col = _safe_col(chunk, "stay_id", "ed_stay_id")
        icd_col = _safe_col(chunk, "icd_code", "icd10_code", "icd")
        ver_col = _safe_col(chunk, "icd_version", "icd_ver", "version")
        if stay_id_col is None or icd_col is None:
            raise SystemExit("diagnosis file missing stay_id or icd_code column")
        if stay_id_col != "stay_id":
            chunk = chunk.rename(columns={stay_id_col: "stay_id"})
        if ver_col is None:
            m = _gi_prefix_mask(chunk[icd_col], icd10_prefixes)
        else:
            ver = pd.to_numeric(chunk[ver_col], errors="coerce")
            m10 = (ver == 10) & _gi_prefix_mask(chunk[icd_col], icd10_prefixes)
            m9 = (ver == 9) & _gi_icd9_prefix_mask(chunk[icd_col], icd9_prefixes)
            m = m10 | m9
        gi_stays.update(chunk.loc[m, "stay_id"].astype(int).tolist())

    # Merge + filter
    merged0 = triage.merge(edstays, on="stay_id", how="left", suffixes=("_triage", "_ed"))
    if "subject_id" not in merged0.columns:
        if "subject_id_ed" in merged0.columns:
            merged0["subject_id"] = merged0["subject_id_ed"]
        elif "subject_id_triage" in merged0.columns:
            merged0["subject_id"] = merged0["subject_id_triage"]
        else:
            raise SystemExit("Could not determine subject_id after merging triage and edstays")
    merged0 = merged0.merge(patients, on="subject_id", how="left")
    intime = pd.to_datetime(merged0["intime"], errors="coerce")
    year = intime.dt.year.astype(float)
    merged0["age"] = merged0["anchor_age"].astype(float) + (year - merged0["anchor_year"].astype(float))
    adult = merged0["age"] >= 18
    n_adult_total = int(adult.sum())
    adult_mask = adult & merged0["stay_id"].astype(int).isin(gi_stays)
    merged0 = merged0.loc[adult_mask].copy()

    tfeat = _time_features(merged0["intime"])

    # Outcome: admission if hadm_id present; fallback to disposition if needed.
    if "hadm_id" in merged0.columns:
        admission = merged0["hadm_id"].notna().astype(int)
    else:
        disp_col = _safe_col(merged0, "disposition")
        if disp_col is None:
            raise SystemExit("Cannot determine admission outcome (no hadm_id or disposition)")
        admission = merged0[disp_col].astype(str).str.contains("admit", case=False, na=False).astype(int)

    # Arrival mode proxy from ED stays (portable to NHAMCS core set).
    arrems = merged0.get("arrival_transport", pd.Series(np.nan, index=merged0.index)).astype(str)
    arrems = arrems.str.contains("AMBUL", case=False, na=False).astype(float)

    # Map common triage vitals (best-effort; missing columns become NaN and will be imputed later).
    def get_numeric(colnames: list[str]) -> pd.Series:
        for c in colnames:
            if c in merged0.columns:
                return pd.to_numeric(merged0[c], errors="coerce")
        return pd.Series(np.nan, index=merged0.index)

    out = pd.DataFrame(
        {
            "age": merged0["age"].astype(float),
            "sex": merged0.get(_safe_col(merged0, "gender", "sex"), pd.Series(np.nan, index=merged0.index)).map(_map_sex),
            "arrems": arrems,
            "immedr": get_numeric(["acuity", "immedr", "esi"]),
            "temp_f": get_numeric(["temperature", "temp_f", "temp"]),
            "pulse": get_numeric(["heartrate", "heart_rate", "pulse"]),
            "resp": get_numeric(["resprate", "resp_rate", "resp"]),
            "sbp": get_numeric(["sbp", "systolic", "systolic_bp"]),
            "dbp": get_numeric(["dbp", "diastolic", "diastolic_bp"]),
            "spo2": get_numeric(["o2sat", "spo2", "oxygen_saturation"]),
            "pain": get_numeric(["pain", "pain_score"]),
            "month": tfeat["month"],
            "day_of_week": tfeat["day_of_week"],
            "arr_hour_sin": tfeat["arr_hour_sin"],
            "arr_hour_cos": tfeat["arr_hour_cos"],
            "admission": admission.astype(int),
        }
    )

    # Basic physiologic plausibility cleaning (set obvious outliers to missing; imputed later).
    out["temp_f"] = _range_to_nan(out["temp_f"], lo=80.0, hi=110.0)
    out["pulse"] = _range_to_nan(out["pulse"], lo=20.0, hi=250.0)
    out["resp"] = _range_to_nan(out["resp"], lo=4.0, hi=60.0)
    out["sbp"] = _range_to_nan(out["sbp"], lo=50.0, hi=250.0)
    out["dbp"] = _range_to_nan(out["dbp"], lo=20.0, hi=150.0)
    out["spo2"] = _range_to_nan(out["spo2"], lo=50.0, hi=100.0)
    out["pain"] = _range_to_nan(out["pain"], lo=0.0, hi=10.0)

    # Ensure consistent columns
    for c in FEATURES_OUT + ["admission"]:
        if c not in out.columns:
            out[c] = np.nan

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    print(f"Phenotype: {args.phenotype} (icd10_prefixes={list(icd10_prefixes)})")
    print(f"Wrote {len(out):,} rows -> {args.out}")
    print("Admission rate:", out["admission"].mean())

    if args.counts_out is not None:
        n_gi_in_edstays = int(edstays["stay_id"].astype(int).isin(gi_stays).sum())
        counts = {
            "dataset": "MIMIC_IV_ED",
            "root": str(args.root),
            "mimic_core_root": str(args.mimic_core_root),
            "phenotype": args.phenotype,
            "icd10_prefixes": list(icd10_prefixes),
            "icd9_prefixes": list(icd9_prefixes),
            "n_edstays_total": int(len(edstays)),
            "n_adult_total": n_adult_total,
            "n_gi_stays_total": int(len(gi_stays)),
            "n_gi_stays_in_edstays": n_gi_in_edstays,
            "n_adult_gi_stays": int(adult_mask.sum()),
            "n_admitted": int(out["admission"].sum()),
        }
        # (Optional) diagnosis row count is expensive to compute precisely without re-reading; omit for speed.
        args.counts_out.parent.mkdir(parents=True, exist_ok=True)
        args.counts_out.write_text(json.dumps(counts, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
