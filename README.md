# Triage-time Admission Prediction (Suspected Acute GI Infection)

This project develops a **triage-time clinical prediction model** for **hospital admission** among **adults with suspected acute gastrointestinal infection**, using **MIMIC-IV-ED** for development and **NHAMCS ED (2016–2022)** for multi-year external validation.

## Data

- **MIMIC-IV / MIMIC-IV-ED (PhysioNet)**: credentialed access + data use agreement required.
- **NHAMCS ED public-use (CDC/NCHS)**: publicly downloadable.

This repository does **not** redistribute any restricted datasets.

## Quickstart (reproduce key outputs)

Prerequisites:
- `python3`
- (recommended) create a clean env and install `requirements.txt`

Reproduce the key paper figures/tables from the included derived results:

```bash
python3 scripts/run_all.py --mode quick
```

Outputs:
- `results/paper/figures/`
- `results/paper/tables/`

## Reproduce analysis outputs (high level)

1) Acquire/download raw datasets:
- NHAMCS: `python3 scripts/download_nhamcs_ed_years.py --years 2016 2017 2018 2019 2020 2021 2022 --out data/raw/nhamcs/`
- MIMIC: follow PhysioNet instructions and place files under `data/raw/mimic-iv/` and `data/raw/mimic-iv-ed/` (see `docs/MIMIC_ACCESS.md` if present).

2) Build processed cohorts and run model training + validation (primary phenotype):
- Build MIMIC-IV-ED cohort: `python3 scripts/build_mimic_iv_ed_gi_cohort.py ...`
- Build NHAMCS yearly + pooled external cohorts and validate: `python3 scripts/run_external_validation_nhamcs_years.py --phenotype primary`

3) Generate paper-facing tables/figures:
- `python3 scripts/make_paper_tables.py --phenotype primary`
- `python3 scripts/make_figures.py`

## Citation integrity workflow

- Reference verification log: `docs/CITATION_VERIFICATION.tsv`
- DOI registry evidence (Crossref first, DataCite fallback): `docs/doi_evidence/doi_evidence.tsv` (build via `python3 scripts/verify_reference_dois.py --strict`)

## License

See `LICENSE`.
