#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


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

def guess_dataset_id(path: Path, *, default: str) -> str:
    s = path.as_posix().lower()
    # Try to infer year for NHAMCS processed files like nhamcs_ed_2019_...
    year = None
    for token in s.replace("-", "_").split("_"):
        if token.isdigit() and len(token) == 4 and token.startswith("20"):
            year = token
            break
    if "nhamcs" in s and year:
        return f"NHAMCS_ED_{year}"
    if "mimic" in s and "ed" in s:
        return "MIMIC_IV_ED"
    return default


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def calibration_slope_intercept(
    y: np.ndarray,
    p: np.ndarray,
    sample_weight: np.ndarray | None,
) -> tuple[float, float]:
    x = _logit(p).reshape(-1, 1)
    lr = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000)
    lr.fit(x, y, sample_weight=sample_weight)
    slope = float(lr.coef_.ravel()[0])
    intercept = float(lr.intercept_.ravel()[0])
    return slope, intercept


def ensure_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for f in FEATURES:
        if f not in out.columns:
            out[f] = np.nan
    return out


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


def decision_curve_baselines(y: np.ndarray, thresholds: np.ndarray, sample_weight: np.ndarray | None) -> pd.DataFrame:
    if sample_weight is None:
        w = np.ones_like(y, dtype=float)
    else:
        w = sample_weight.astype(float)
    w = w / w.mean()

    prev = float(np.average(y.astype(float), weights=w))
    rows: list[dict[str, float]] = []
    for t in thresholds:
        nb_all = prev - (1 - prev) * (t / (1 - t))
        rows.append({"threshold": float(t), "net_benefit": float(nb_all), "model_name": "treat_all"})
        rows.append({"threshold": float(t), "net_benefit": 0.0, "model_name": "treat_none"})
    return pd.DataFrame(rows)


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


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def recalibrate_intercept_only(p: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None) -> float:
    """
    Finds delta such that mean(sigmoid(logit(p) + delta)) matches the observed event rate.
    Uses a robust bisection search; returns delta (log-odds shift).
    """
    z = _logit(p)

    if sample_weight is None:
        w = np.ones_like(y, dtype=float)
    else:
        w = sample_weight.astype(float)
    w = w / w.mean()

    target = float(np.average(y.astype(float), weights=w))

    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        pmid = sigmoid(z + mid)
        cur = float(np.average(pmid, weights=w))
        if cur < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def bootstrap_ci(
    *,
    y: np.ndarray,
    p: np.ndarray,
    sample_weight: np.ndarray | None,
    n_boot: int,
    seed: int,
) -> dict[str, tuple[float, float]]:
    """
    Percentile bootstrap CIs for AUC/Brier/calibration slope/intercept.
    """
    rng = np.random.default_rng(seed)
    n = int(len(y))
    aucs: list[float] = []
    briers: list[float] = []
    slopes: list[float] = []
    intercepts: list[float] = []

    attempts = 0
    max_attempts = max(n_boot * 10, n_boot + 20)
    while len(aucs) < n_boot and attempts < max_attempts:
        attempts += 1
        idx = rng.integers(0, n, size=n, endpoint=False)
        yb = y[idx]
        pb = p[idx]
        wb = None if sample_weight is None else sample_weight[idx]

        # Skip degenerate samples (AUC undefined).
        if len(np.unique(yb)) < 2:
            continue

        try:
            aucs.append(float(roc_auc_score(yb, pb, sample_weight=wb)))
            briers.append(float(brier_score_loss(yb, pb, sample_weight=wb)))
            s, itc = calibration_slope_intercept(yb, pb, sample_weight=wb)
            slopes.append(float(s))
            intercepts.append(float(itc))
        except Exception:
            continue

    if len(aucs) < max(30, n_boot // 2):
        raise SystemExit(f"Bootstrap produced too few valid replicates: {len(aucs)} / {n_boot}")

    def pct(x: list[float], q: float) -> float:
        return float(np.nanquantile(np.asarray(x, dtype=float), q))

    return {
        "auc": (pct(aucs, 0.025), pct(aucs, 0.975)),
        "brier": (pct(briers, 0.025), pct(briers, 0.975)),
        "calibration_slope": (pct(slopes, 0.025), pct(slopes, 0.975)),
        "calibration_intercept": (pct(intercepts, 0.025), pct(intercepts, 0.975)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", type=Path, default=Path("data/processed/mimic_iv_ed_adult_suspected_gi.parquet"))
    ap.add_argument("--ext", type=Path, default=Path("data/processed/nhamcs_ed_2019_adult_suspected_gi.parquet"))
    ap.add_argument("--dev-id", type=str, default=None, help="Dataset ID label for the development cohort.")
    ap.add_argument("--ext-id", type=str, default=None, help="Dataset ID label for the external-validation cohort.")
    ap.add_argument("--outdir", type=Path, default=Path("results"))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--use-ext-weights",
        action="store_true",
        help="Use NHAMCS survey weights during external validation metric calculation (sensitivity mode).",
    )
    ap.add_argument(
        "--bootstrap",
        type=int,
        default=0,
        help="If >0, compute percentile bootstrap 95 percent CIs for key metrics using fixed predictions.",
    )
    args = ap.parse_args()

    if not args.dev.exists():
        raise SystemExit(f"Missing development dataset: {args.dev}. Build it via scripts/build_mimic_iv_ed_gi_cohort.py after MIMIC is downloaded.")
    if not args.ext.exists():
        raise SystemExit(f"Missing external dataset: {args.ext}. Build it via scripts/build_nhamcs_2019_gi_cohort.py.")

    dev_id = args.dev_id or guess_dataset_id(args.dev, default="DEV")
    ext_id = args.ext_id or guess_dataset_id(args.ext, default="EXT")

    dev = ensure_features(pd.read_parquet(args.dev))
    ext = ensure_features(pd.read_parquet(args.ext))

    for name, df in [("dev", dev), ("ext", ext)]:
        if "admission" not in df.columns:
            raise SystemExit(f"{name} dataset missing 'admission' outcome")

    X_dev = dev[FEATURES].copy()
    y_dev = dev["admission"].astype(int).to_numpy()

    X_ext = ext[FEATURES].copy()
    y_ext = ext["admission"].astype(int).to_numpy()
    w_ext = None
    if args.use_ext_weights:
        if "sample_weight" not in ext.columns:
            raise SystemExit("External dataset is missing sample_weight; rebuild NHAMCS processed file.")
        w_ext = ext["sample_weight"].astype(float).to_numpy()

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=args.seed)
    pipe = Pipeline(
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

    # TRIPOD-friendly: use out-of-fold predictions for internal validation.
    p_oof = cross_val_predict(pipe, X_dev, y_dev, cv=cv, method="predict_proba")[:, 1]
    auc_oof = float(roc_auc_score(y_dev, p_oof))
    brier_oof = float(brier_score_loss(y_dev, p_oof))
    slope_oof, intercept_oof = calibration_slope_intercept(y_dev, p_oof, sample_weight=None)

    # Fit on full dev, evaluate on external.
    pipe.fit(X_dev, y_dev)
    p_ext = pipe.predict_proba(X_ext)[:, 1]
    auc_ext = float(roc_auc_score(y_ext, p_ext, sample_weight=w_ext))
    brier_ext = float(brier_score_loss(y_ext, p_ext, sample_weight=w_ext))
    slope_ext, intercept_ext = calibration_slope_intercept(y_ext, p_ext, sample_weight=w_ext)

    outdir = args.outdir
    (outdir / "benchmarks").mkdir(parents=True, exist_ok=True)
    (outdir / "models").mkdir(parents=True, exist_ok=True)

    eval_df = pd.DataFrame(
        [
            {
                "dataset_id": dev_id,
                "split_or_cohort": "internal_oof_cv",
                "model_name": "elasticnet_logistic_cv",
                "auc": auc_oof,
                "brier": brier_oof,
                "calibration_slope": slope_oof,
                "calibration_intercept": intercept_oof,
                "n": int(len(dev)),
                "n_events": int(y_dev.sum()),
            },
            {
                "dataset_id": ext_id,
                "split_or_cohort": "external_validation",
                "model_name": "elasticnet_logistic_cv",
                "auc": auc_ext,
                "brier": brier_ext,
                "calibration_slope": slope_ext,
                "calibration_intercept": intercept_ext,
                "n": int(len(ext)),
                "n_events": int(y_ext.sum()),
            },
        ]
    )
    eval_df.to_csv(outdir / "benchmarks" / "prediction_eval.tsv", sep="\t", index=False)

    if args.bootstrap > 0:
        ci_rows: list[dict[str, object]] = []
        dev_ci = bootstrap_ci(y=y_dev, p=p_oof, sample_weight=None, n_boot=args.bootstrap, seed=args.seed + 101)
        ext_ci = bootstrap_ci(y=y_ext, p=p_ext, sample_weight=w_ext, n_boot=args.bootstrap, seed=args.seed + 202)
        for dataset_id, split, ci in [
            (dev_id, "internal_oof_cv", dev_ci),
            (ext_id, "external_validation", ext_ci),
        ]:
            row = {
                "dataset_id": dataset_id,
                "split_or_cohort": split,
                "model_name": "elasticnet_logistic_cv",
                "n_bootstrap": int(args.bootstrap),
                "seed": int(args.seed),
            }
            for k, (lo, hi) in ci.items():
                row[f"{k}_ci_low"] = float(lo)
                row[f"{k}_ci_high"] = float(hi)
            ci_rows.append(row)
        pd.DataFrame(ci_rows).to_csv(outdir / "benchmarks" / "prediction_eval_ci.tsv", sep="\t", index=False)

    # Calibration (binned) + decision curves for both cohorts
    calib_rows = []
    calib_dev = calibration_bins(y_dev, p_oof, n_bins=10, sample_weight=None)
    calib_dev.insert(0, "split_or_cohort", "internal_oof_cv")
    calib_dev.insert(0, "model_name", "elasticnet_logistic_cv")
    calib_dev.insert(0, "dataset_id", dev_id)
    calib_rows.append(calib_dev)

    calib_ext = calibration_bins(y_ext, p_ext, n_bins=10, sample_weight=w_ext)
    calib_ext.insert(0, "split_or_cohort", "external_validation")
    calib_ext.insert(0, "model_name", "elasticnet_logistic_cv")
    calib_ext.insert(0, "dataset_id", ext_id)
    calib_rows.append(calib_ext)

    pd.concat(calib_rows, ignore_index=True).to_csv(outdir / "benchmarks" / "calibration_bins.tsv", sep="\t", index=False)

    thresholds = np.linspace(0.05, 0.50, 46)
    dca_rows = []
    dca_dev = decision_curve(y_dev, p_oof, thresholds=thresholds, sample_weight=None)
    dca_dev.insert(0, "split_or_cohort", "internal_oof_cv")
    dca_dev.insert(0, "model_name", "elasticnet_logistic_cv")
    dca_dev.insert(0, "dataset_id", dev_id)
    dca_rows.append(dca_dev)

    dca_dev_base = decision_curve_baselines(y_dev, thresholds=thresholds, sample_weight=None)
    dca_dev_base.insert(0, "split_or_cohort", "internal_oof_cv")
    dca_dev_base.insert(0, "dataset_id", dev_id)
    dca_rows.append(dca_dev_base)

    dca_ext = decision_curve(y_ext, p_ext, thresholds=thresholds, sample_weight=w_ext)
    dca_ext.insert(0, "split_or_cohort", "external_validation")
    dca_ext.insert(0, "model_name", "elasticnet_logistic_cv")
    dca_ext.insert(0, "dataset_id", ext_id)
    dca_rows.append(dca_ext)

    dca_ext_base = decision_curve_baselines(y_ext, thresholds=thresholds, sample_weight=w_ext)
    dca_ext_base.insert(0, "split_or_cohort", "external_validation")
    dca_ext_base.insert(0, "dataset_id", ext_id)
    dca_rows.append(dca_ext_base)

    pd.concat(dca_rows, ignore_index=True).to_csv(outdir / "benchmarks" / "decision_curve.tsv", sep="\t", index=False)

    # External recalibration (secondary analysis for transport)
    delta = recalibrate_intercept_only(p_ext, y_ext, sample_weight=w_ext)
    p_ext_recal_int = sigmoid(_logit(p_ext) + delta)
    slope_int, intercept_int = calibration_slope_intercept(y_ext, p_ext_recal_int, sample_weight=w_ext)

    p_ext_recal_full = sigmoid(intercept_ext + slope_ext * _logit(p_ext))
    slope_full, intercept_full = calibration_slope_intercept(y_ext, p_ext_recal_full, sample_weight=w_ext)

    recal_df = pd.DataFrame(
        [
            {
                "dataset_id": ext_id,
                "split_or_cohort": "external_validation",
                "model_name": "elasticnet_logistic_cv",
                "update_type": "none",
                "auc": auc_ext,
                "brier": brier_ext,
                "calibration_slope": slope_ext,
                "calibration_intercept": intercept_ext,
                "n": int(len(ext)),
                "n_events": int(y_ext.sum()),
            },
            {
                "dataset_id": ext_id,
                "split_or_cohort": "external_validation",
                "model_name": "elasticnet_logistic_cv",
                "update_type": "recalibrate_intercept_only",
                "auc": auc_ext,
                "brier": float(brier_score_loss(y_ext, p_ext_recal_int, sample_weight=w_ext)),
                "calibration_slope": slope_int,
                "calibration_intercept": intercept_int,
                "n": int(len(ext)),
                "n_events": int(y_ext.sum()),
            },
            {
                "dataset_id": ext_id,
                "split_or_cohort": "external_validation",
                "model_name": "elasticnet_logistic_cv",
                "update_type": "recalibrate_slope_and_intercept",
                "auc": auc_ext,
                "brier": float(brier_score_loss(y_ext, p_ext_recal_full, sample_weight=w_ext)),
                "calibration_slope": slope_full,
                "calibration_intercept": intercept_full,
                "n": int(len(ext)),
                "n_events": int(y_ext.sum()),
            },
        ]
    )
    recal_df.to_csv(outdir / "benchmarks" / "recalibration_eval.tsv", sep="\t", index=False)

    clf: LogisticRegressionCV = pipe.named_steps["clf"]
    coefs = pd.DataFrame({"feature": FEATURES, "coef_standardized": clf.coef_.ravel()})
    coefs.insert(0, "model_name", "elasticnet_logistic_cv")
    coefs.to_csv(outdir / "models" / "model_coefficients.tsv", sep="\t", index=False)

    # Export model equation in original feature units (undo standardization).
    imputer: SimpleImputer = pipe.named_steps["impute"]
    scaler: StandardScaler = pipe.named_steps["scale"]
    beta_scaled = clf.coef_.ravel().astype(float)
    intercept_scaled = float(clf.intercept_.ravel()[0])
    mean_ = scaler.mean_.astype(float)
    scale_ = scaler.scale_.astype(float)
    scale_[scale_ == 0] = 1.0

    beta_original = beta_scaled / scale_
    intercept_original = intercept_scaled - float((beta_scaled * mean_ / scale_).sum())

    equation_rows: list[dict[str, object]] = [
        {
            "feature": "__intercept__",
            "beta_original": intercept_original,
            "beta_scaled": intercept_scaled,
            "impute_median": "",
            "scaler_mean": "",
            "scaler_scale": "",
        }
    ]
    for f, b0, bs, med, mu, sc in zip(
        FEATURES,
        beta_original.tolist(),
        beta_scaled.tolist(),
        imputer.statistics_.astype(float).tolist(),
        mean_.tolist(),
        scale_.tolist(),
        strict=True,
    ):
        equation_rows.append(
            {
                "feature": f,
                "beta_original": float(b0),
                "beta_scaled": float(bs),
                "impute_median": float(med),
                "scaler_mean": float(mu),
                "scaler_scale": float(sc),
            }
        )
    pd.DataFrame(equation_rows).to_csv(outdir / "models" / "model_equation.tsv", sep="\t", index=False)

    print(eval_df.to_string(index=False))


if __name__ == "__main__":
    main()
