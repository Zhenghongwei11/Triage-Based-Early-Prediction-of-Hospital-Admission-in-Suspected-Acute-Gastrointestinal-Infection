#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


DATA_DEFAULT = Path("data/processed/nhamcs_ed_2019_adult_suspected_gi.parquet")
OUT_DIR_DEFAULT = Path("results")

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


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def calibration_slope_intercept(y: np.ndarray, p: np.ndarray, sample_weight: np.ndarray | None) -> tuple[float, float]:
    x = _logit(p).reshape(-1, 1)
    lr = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000)
    lr.fit(x, y, sample_weight=sample_weight)
    slope = float(lr.coef_.ravel()[0])
    intercept = float(lr.intercept_.ravel()[0])
    return slope, intercept


def decision_curve(y: np.ndarray, p: np.ndarray, thresholds: np.ndarray, sample_weight: np.ndarray | None) -> pd.DataFrame:
    if sample_weight is None:
        w = np.ones_like(y, dtype=float)
    else:
        w = sample_weight.astype(float)
    w = w / w.mean()

    out_rows: list[dict[str, float]] = []
    n = float(w.sum())
    for t in thresholds:
        pred_pos = p >= t
        tp = float(w[(pred_pos) & (y == 1)].sum())
        fp = float(w[(pred_pos) & (y == 0)].sum())
        nb = (tp / n) - (fp / n) * (t / (1 - t))
        out_rows.append({"threshold": float(t), "net_benefit": nb})
    return pd.DataFrame(out_rows)


def calibration_bins(
    y: np.ndarray,
    p: np.ndarray,
    *,
    n_bins: int = 10,
    sample_weight: np.ndarray | None,
) -> pd.DataFrame:
    if sample_weight is None:
        w = np.ones_like(y, dtype=float)
    else:
        w = sample_weight.astype(float)
    w = w / w.mean()

    # Unweighted quantile bins (portable + deterministic).
    edges = np.quantile(p, np.linspace(0.0, 1.0, n_bins + 1))
    edges[0] = -np.inf
    edges[-1] = np.inf
    bin_id = np.digitize(p, edges[1:-1], right=True) + 1

    rows: list[dict[str, float]] = []
    for b in range(1, n_bins + 1):
        m = bin_id == b
        if not np.any(m):
            continue
        wb = w[m]
        rows.append(
            {
                "bin": float(b),
                "n": float(m.sum()),
                "mean_pred": float(np.average(p[m], weights=wb)),
                "event_rate": float(np.average(y[m], weights=wb)),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DATA_DEFAULT)
    ap.add_argument("--outdir", type=Path, default=OUT_DIR_DEFAULT)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--use-weights",
        action="store_true",
        help="Use NHAMCS survey weights during model fitting (sensitivity mode; default is unweighted fitting).",
    )
    args = ap.parse_args()

    df = pd.read_parquet(args.data)
    for c in FEATURES + ["admission", "sample_weight"]:
        if c not in df.columns:
            raise SystemExit(f"Missing column in processed data: {c}")

    X = df[FEATURES].copy()
    y = df["admission"].astype(int).to_numpy()
    w = df["sample_weight"].astype(float).to_numpy()
    fit_w = w if args.use_weights else None

    # Main model: elastic-net logistic regression with CV (TRIPOD: include baseline comparator separately).
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=args.seed)
    model = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            (
                "clf",
                LogisticRegressionCV(
                    Cs=6,
                    cv=cv,
                    penalty="elasticnet",
                    solver="saga",
                    l1_ratios=[0.0, 0.5, 1.0],
                    scoring="roc_auc",
                    max_iter=2000,
                    tol=1e-3,
                    n_jobs=None,
                    refit=True,
                ),
            ),
        ]
    )
    if fit_w is None:
        model.fit(X, y)
    else:
        model.fit(X, y, clf__sample_weight=fit_w)
    p = model.predict_proba(X)[:, 1]

    auc = float(roc_auc_score(y, p, sample_weight=fit_w))
    brier = float(brier_score_loss(y, p, sample_weight=fit_w))
    slope, intercept = calibration_slope_intercept(y, p, sample_weight=fit_w)

    outdir = args.outdir
    (outdir / "benchmarks").mkdir(parents=True, exist_ok=True)
    (outdir / "models").mkdir(parents=True, exist_ok=True)

    eval_row = pd.DataFrame(
        [
            {
                "dataset_id": "NHAMCS_ED_2019",
                "split_or_cohort": "internal_cv_fit_all",
                "model_name": "elasticnet_logistic_cv",
                "fit_weighting": "survey_weights" if args.use_weights else "none",
                "auc": auc,
                "brier": brier,
                "calibration_slope": slope,
                "calibration_intercept": intercept,
                "n": int(len(df)),
                "n_events": int(y.sum()),
            }
        ]
    )
    eval_row.to_csv(outdir / "benchmarks" / "prediction_eval.tsv", sep="\t", index=False)

    calib = calibration_bins(y, p, n_bins=10, sample_weight=fit_w)
    calib.insert(0, "model_name", "elasticnet_logistic_cv")
    calib.insert(0, "dataset_id", "NHAMCS_ED_2019")
    calib.to_csv(outdir / "benchmarks" / "calibration_bins.tsv", sep="\t", index=False)

    thresholds = np.linspace(0.05, 0.50, 46)
    dca = decision_curve(y, p, thresholds=thresholds, sample_weight=fit_w)
    dca.insert(0, "dataset_id", "NHAMCS_ED_2019")
    dca.insert(1, "model_name", "elasticnet_logistic_cv")
    dca.to_csv(outdir / "benchmarks" / "decision_curve.tsv", sep="\t", index=False)

    clf: LogisticRegressionCV = model.named_steps["clf"]
    coefs = pd.DataFrame({"feature": FEATURES, "coef_standardized": clf.coef_.ravel()})
    coefs.insert(0, "model_name", "elasticnet_logistic_cv")
    coefs.to_csv(outdir / "models" / "model_coefficients.tsv", sep="\t", index=False)

    print(eval_row.to_string(index=False))


if __name__ == "__main__":
    main()
