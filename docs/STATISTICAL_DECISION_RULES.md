# Statistical decision rules

This document summarizes the key prespecified statistical rules implemented in `scripts/` for reproducible evaluation.

## Prediction model type

- Model family: elastic-net logistic regression (implemented via scikit-learn).
- Predictors: triage-time variables only (demographics, arrival mode, acuity/immediacy proxy, vital signs, time-of-arrival encoding).
- Missing data: median imputation within the pipeline.

## Performance metrics

- Discrimination: AUC.
- Overall accuracy: Brier score.
- Calibration: calibration slope and intercept (logit recalibration).
- Clinical utility: decision curve analysis (net benefit across threshold probabilities).

## Uncertainty quantification

- Confidence intervals: percentile bootstrap CIs for AUC, Brier, calibration slope, and calibration intercept.
- Bootstrap replicates: controlled by `--bootstrap` in `scripts/train_mimic_validate_nhamcs.py` and `scripts/run_external_validation_nhamcs_years.py`.

## Reproducible regeneration of figures/tables

- Figures are generated from lightweight anchor tables under `results/` (see `docs/FIGURE_PROVENANCE.tsv`).

