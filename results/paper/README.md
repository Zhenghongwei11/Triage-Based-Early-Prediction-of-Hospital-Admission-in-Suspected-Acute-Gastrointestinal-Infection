# Paper Pack (auto-generated)

This folder contains manuscript-facing tables/figures produced from the reproducible pipeline.

## How to regenerate

1) Ensure raw datasets are present (MIMIC-IV core + MIMIC-IV-ED; NHAMCS 2016–2022).
2) Re-run the analysis:
- Phenotype + CIs (primary + sensitivity): `python3 scripts/run_sensitivity_phenotypes.py --bootstrap 200`
- Multi-year external validation: `python3 scripts/run_external_validation_nhamcs_years.py --phenotype primary --years 2016 2017 2018 2019 2020 2021 2022 --bootstrap 200`
- Summaries + paper tables/figures:
  - `python3 scripts/summarize_phenotype_results.py`
  - `python3 scripts/summarize_external_nhamcs_years.py`
  - `python3 scripts/make_table1.py --dev data/processed/mimic_iv_ed_adult_suspected_gi.parquet --ext data/processed/nhamcs_ed_2016_2022_adult_suspected_gi_primary_pooled.parquet --ext-id NHAMCS_ED_2016_2022_POOLED`
  - `python3 scripts/make_paper_tables.py --phenotype primary`
  - `python3 scripts/make_figures.py`
  - `python3 scripts/make_flow_diagram.py`

## Outputs

**Tables** (`results/paper/tables/`)
- `table1_baseline_primary_pooled.tsv`: baseline characteristics (development vs pooled external).
- `table2_external_performance_compact.tsv`: year-wise external performance + pooled summary.
- `external_nhamcs_years_unweighted.tsv`: full unweighted year-wise external results.
- `external_nhamcs_years_weighted.tsv`: survey-weighted external sensitivity results.
- `performance_primary_phenotype.tsv`: internal (OOF) + single-year external (NHAMCS 2019) pack.

**Figures** (`results/paper/figures/`)
- `auc_by_year.png`: external AUC with 95% CIs across NHAMCS years (2016–2022) + pooled reference.
- `calibration_binned_pooled.png`: binned calibration (internal OOF vs pooled external).
- `dca_external_pooled.png`: decision curve analysis (external pooled; model vs treat-all/none).

**Flow diagram inputs** (`results/paper/flow/`)
- `flow_counts_primary.tsv`: cohort flow counts.
- `flow_primary.mmd`: Mermaid flowchart source (convert later to SVG/PNG as needed).

