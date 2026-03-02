# Data Access Smoke Test (must-pass gate)

Goal: prevent midstream failure by verifying dataset access and minimum field availability **before** any modeling.

## Candidate datasets
1) Development: MIMIC-IV-ED (via PhysioNet account + training + click-through license)
2) External validation: NHAMCS ED public-use microdata (CDC/NCHS; direct download)

## Must-pass checks (per dataset)

### A) Access + integrity
- Download completes end-to-end without manual approvals beyond click-through license.
- Files have stable checksums recorded in `data/manifest.tsv`.
- A minimal “read” script can load the raw files and print:
  - row counts,
  - unique encounter identifiers (if applicable),
  - date ranges.

### B) Cohort definition feasibility (adult GI infection)
- We can define an ED cohort for adults (>=18 years).
- We can identify “acute gastrointestinal infection/gastroenteritis” encounters using diagnosis codes or equivalent fields.
- The cohort definition is portable: the same high-level logic can be applied to both datasets (allowing coding-system differences).

### C) Outcome feasibility (primary)
- Hospital admission disposition exists and is interpretable:
  - **Outcome**: ED visit results in hospital admission vs discharge.
- Event rate is non-trivial (target >=5% in the defined cohort; otherwise revise cohort/outcome).

### D) Predictor feasibility (core set; must exist in both datasets)
Minimum core predictors:
- Age
- Sex
- Arrival mode (if present)
- Triage acuity (or close proxy; if absent, document)
- Initial vital signs: HR, RR, SBP, temperature (and SpO2 if present)
- Calendar/time features: month, day-of-week, time-of-day (if present)

### E) Missingness envelope
- For each core predictor, compute:
  - missingness %
  - plausible range checks (e.g., SBP 50–250)
- If any core predictor has >40% missingness in the validation dataset, we either:
  - drop it from the core model, or
  - redesign the validation strategy (predeclared).

## Pass/Fail decision
- **PASS**: both datasets meet A–E → proceed to cohort definition + modeling.
- **CONDITIONAL PASS**: validation dataset lacks 1–2 predictors but still supports a meaningful core model → proceed with reduced core set and document transportability limits.
- **FAIL**: external validation cannot be performed meaningfully → pivot dataset or adjust the clinical question.

## Current status (2026-03-01)

### NHAMCS ED 2019 (external validation)
- **Access**: PASS (downloadable from CDC FTP; Stata `.dta` extracted)
- **Outcome**: PASS (`ADMITHOS` exists; binary)
- **Cohort feasibility**: PASS (adult + diagnosis-code prefixes; see smoke-test script)
- **Core predictors**: PASS (AGE/SEX/ARREMS/IMMEDR/vitals exist; negative codes used for missingness)
- **Missingness snapshot (in cohort)**:
  - IMMEDR ~22.8%, PAINSCALE ~32.0%, other vitals mostly ~3–5%
- **Cohort size snapshot**: adult suspected GI cohort `n=806`, admission rate ~10.9%

Repro:
- Run `python3 scripts/smoke_test_nhamcs_2019.py` to regenerate `results/dataset_summary.tsv`.
