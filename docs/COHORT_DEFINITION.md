# Cohort Definition: Adult suspected acute GI infection (ED)

Goal: define a portable cohort that can be implemented in both:
- MIMIC-IV-ED (development; ED EHR)
- NHAMCS ED public-use microdata (external validation; survey)

## Core inclusion criteria
- Adult: age >= 18 years at ED encounter.
- Suspected acute gastrointestinal infection / gastroenteritis-like presentation, using diagnosis codes available in each dataset.

## Diagnosis-code phenotype (portable “prefix” definition)

We use a conservative ICD-10-CM prefix set capturing:
- **A08*** (viral and other specified intestinal infections)
- **A09*** (infectious gastroenteritis and colitis; and/or presumed infectious diarrhea/gastroenteritis depending on coding)
- **A04*** (other bacterial intestinal infections)
- **K52*** (other/noninfective gastroenteritis and colitis; included to capture “presumed infectious” coding in practice; treated as lower-specificity)
- **R11*** (nausea and vomiting) and **R19*** (other digestive system symptoms; includes diarrhea), included to improve sensitivity in NHAMCS where strict infection codes may be underused

### Primary cohort (main analysis)
Adult ED encounters with any diagnosis code (primary or secondary, when available) whose normalized code starts with one of:
`A08`, `A09`, `A04`, `K52`, `R11`, `R19`.

## Sensitivity cohorts
To quantify phenotype specificity, we will run predeclared variants:

1) **High-specificity infection-only**: `A08|A09|A04` prefixes only.
2) **Intermediate**: `A08|A09|A04|K52` (adds presumed infectious gastroenteritis coding).
3) **Symptom-excluded (operationally identical to intermediate)**: exclude `R11|R19` symptom codes as inclusion criteria; i.e., require `A08|A09|A04|K52`.

Implementation note: because `R11|R19` are not included in the intermediate definition, “intermediate” and “symptom-excluded” are equivalent by design; we keep both labels to match the manuscript narrative.

## NHAMCS 2019 implementation notes
- Diagnosis fields are strings like `A09-` (padding); we normalize by stripping `-` and matching prefixes.
- Missing values are encoded as negative sentinel values for some numeric fields; these are converted to missing in processing scripts.
- For cross-dataset harmonization, we recode key triage covariates to match the MIMIC conventions:
  - `SEX`: 1=female, 2=male → `sex` as 0=female, 1=male.
  - `ARREMS`: 1=EMS, 2=other → `arrems` as 1=EMS, 0=not EMS.
  - `IMMEDR`: keep only 1..5; other codes treated as missing.
  - `VDAYR`: mapped to pandas `dayofweek` (0=Monday .. 6=Sunday) via `(VDAYR + 5) % 7`.

Current implementation:
- `scripts/smoke_test_nhamcs_2019.py` (counts + missingness)
- `scripts/build_nhamcs_2019_gi_cohort.py` (processed cohort dataset)

## MIMIC-IV-ED implementation notes
- We will identify GI encounters via `diagnosis.csv*` and match ICD-10 code prefixes after normalization (strip dots).
- Primary outcome is ED→hospital admission, using `hadm_id` presence (or disposition fallback if needed).

Planned/implemented script (requires local MIMIC files):
- `scripts/build_mimic_iv_ed_gi_cohort.py`
  - supports `--phenotype {primary,infection_only,intermediate,symptom_excluded}`
  - default output is the primary cohort file; non-primary phenotypes get a suffix in `data/processed/`.

## Reporting
Manuscript will:
- state the primary cohort definition,
- report sensitivity analyses across cohort variants,
- avoid overclaiming “confirmed infection” (phenotype is “suspected” based on codes).
