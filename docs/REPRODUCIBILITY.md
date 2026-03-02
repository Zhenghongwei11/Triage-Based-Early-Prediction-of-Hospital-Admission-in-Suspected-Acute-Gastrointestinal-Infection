# Reproducibility (public)

This repository is a public reproducibility package for a triage-time clinical prediction model of hospital admission among adults with suspected acute gastrointestinal infection.

## What you can reproduce without restricted data

The repository includes derived result tables under `results/` that allow regeneration of the paper-facing figures/tables:

```bash
python3 scripts/run_all.py --mode quick
```

Outputs:
- Figures: `results/paper/figures/`
- Tables: `results/paper/tables/`

## What requires credentialed datasets

Some pipeline steps require credentialed access to PhysioNet (MIMIC-IV / MIMIC-IV-ED) and are not reproducible from public downloads alone. This repository does not redistribute any restricted datasets.

For NHAMCS ED public-use microdata download instructions and checksums, see:
- `data/manifest.tsv`

