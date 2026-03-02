#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PHENOTYPES = ["primary", "infection_only", "intermediate", "symptom_excluded"]


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", type=int, default=200, help="Bootstrap replicates per phenotype (0 to disable).")
    ap.add_argument("--use-ext-weights", action="store_true", help="Use NHAMCS weights for external metrics (sensitivity).")
    ap.add_argument("--only", choices=PHENOTYPES, default=None, help="Run only one phenotype.")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    py = sys.executable

    phenos = [args.only] if args.only else PHENOTYPES
    for pheno in phenos:
        dev_out = root / f"data/processed/mimic_iv_ed_adult_suspected_gi_{pheno}.parquet"
        ext_out = root / f"data/processed/nhamcs_ed_2019_adult_suspected_gi_{pheno}.parquet"
        if pheno == "primary":
            dev_out = root / "data/processed/mimic_iv_ed_adult_suspected_gi.parquet"
            ext_out = root / "data/processed/nhamcs_ed_2019_adult_suspected_gi.parquet"

        outdir = root / f"results/phenotypes/{pheno}"

        run([py, str(root / "scripts/build_mimic_iv_ed_gi_cohort.py"), "--phenotype", pheno, "--out", str(dev_out)])
        run([py, str(root / "scripts/build_nhamcs_2019_gi_cohort.py"), "--phenotype", pheno, "--out", str(ext_out)])

        train_cmd = [
            py,
            str(root / "scripts/train_mimic_validate_nhamcs.py"),
            "--dev",
            str(dev_out),
            "--ext",
            str(ext_out),
            "--outdir",
            str(outdir),
        ]
        if args.bootstrap:
            train_cmd += ["--bootstrap", str(args.bootstrap)]
        if args.use_ext_weights:
            train_cmd += ["--use-ext-weights"]
        run(train_cmd)

        run(
            [
                py,
                str(root / "scripts/summarize_cohorts.py"),
                "--dev",
                str(dev_out),
                "--ext",
                str(ext_out),
                "--outdir",
                str(outdir / "tables"),
            ]
        )

    print("\nDone. See results under results/phenotypes/<phenotype>/")


if __name__ == "__main__":
    main()

