# Compute plan

## Quick mode (recommended)

Regenerate paper-facing figures/tables from included derived results:

```bash
python3 scripts/run_all.py --mode quick
```

Expected resources: laptop-class CPU, <1 GB RAM, seconds to minutes.

## Recompute external validation (NHAMCS + credentialed development cohort)

Recomputing yearly + pooled external validation requires:
- NHAMCS ED raw public-use downloads (see `data/manifest.tsv`)
- A local processed development cohort file (MIMIC-IV-ED), which requires PhysioNet credentialing and data use agreements

Command:

```bash
python3 scripts/run_all.py --mode recompute_external --phenotype primary --bootstrap 200
```

Expected resources: laptop-class CPU; runtime depends on bootstrap replicates and I/O.

