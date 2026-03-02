#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--flowdir", type=Path, default=Path("results/paper/flow"))
    ap.add_argument("--outdir", type=Path, default=Path("results/paper/flow"))
    ap.add_argument("--years", nargs="+", type=int, default=[2016, 2017, 2018, 2019, 2020, 2021, 2022])
    args = ap.parse_args()

    mimic = read_json(args.flowdir / "mimic_primary_counts.json")
    nh_rows = [read_json(args.flowdir / f"nhamcs_{y}_counts.json") for y in args.years]

    # Aggregate NHAMCS counts across years.
    agg = {
        "n_total": sum(int(r["n_total"]) for r in nh_rows),
        "n_adult": sum(int(r["n_adult"]) for r in nh_rows),
        "n_suspected_gi": sum(int(r["n_suspected_gi"]) for r in nh_rows),
        "n_adult_suspected_gi": sum(int(r["n_adult_suspected_gi"]) for r in nh_rows),
        "n_admitted": sum(int(r["n_admitted"]) for r in nh_rows),
    }

    args.outdir.mkdir(parents=True, exist_ok=True)

    # Write a simple TSV counts table (useful for manuscript flow diagram caption).
    counts_tbl = pd.DataFrame(
        [
            {
                "dataset": "MIMIC_IV_ED",
                "n_total": mimic["n_edstays_total"],
                "n_adult": mimic.get("n_adult_total", ""),
                "n_suspected_gi": mimic.get("n_gi_stays_in_edstays", mimic.get("n_gi_stays_total", "")),
                "n_adult_suspected_gi": mimic["n_adult_gi_stays"],
                "n_admitted": mimic["n_admitted"],
            },
            {
                "dataset": "NHAMCS_ED_2016_2022",
                "n_total": agg["n_total"],
                "n_adult": agg["n_adult"],
                "n_suspected_gi": agg["n_suspected_gi"],
                "n_adult_suspected_gi": agg["n_adult_suspected_gi"],
                "n_admitted": agg["n_admitted"],
            },
        ]
    )
    counts_tbl.to_csv(args.outdir / "flow_counts_primary.tsv", sep="\t", index=False)

    # Mermaid flow diagram (convert later to SVG/PNG if needed).
    mimic_gi = mimic.get("n_gi_stays_in_edstays", mimic.get("n_gi_stays_total", mimic["n_adult_gi_stays"]))
    mimic_adult_total = mimic.get("n_adult_total", mimic["n_edstays_total"])
    mmd = f"""flowchart TB
  subgraph DEV[Development cohort (MIMIC-IV-ED)]
    A[MIMIC-IV-ED ED stays\\n(n={mimic['n_edstays_total']:,})] --> A2[Adults (age ≥18)\\n(n={int(mimic_adult_total):,})]
    A2 --> B[Suspected acute GI infection by dx codes\\n(n={int(mimic_gi):,})]
    B --> C[Adult suspected GI infection\\n(n={mimic['n_adult_gi_stays']:,})]
  end

  subgraph EXT[External validation cohorts (NHAMCS ED)]
    D[NHAMCS ED visits 2016–2022\\n(n={agg['n_total']:,})] --> E[Adults (age ≥18)\\n(n={agg['n_adult']:,})]
    E --> F[Suspected acute GI infection by dx codes\\n(n={agg['n_adult_suspected_gi']:,})]
  end
"""
    (args.outdir / "flow_primary.mmd").write_text(mmd)
    print(f"Wrote: {args.outdir / 'flow_counts_primary.tsv'}")
    print(f"Wrote: {args.outdir / 'flow_primary.mmd'}")


if __name__ == "__main__":
    main()
