#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path


REQUIRED_DIRS = [
    Path("data/raw/mimic-iv-ed"),
    Path("data/raw/mimic-iv"),
]


def main() -> None:
    missing = [p for p in REQUIRED_DIRS if not p.exists()]
    if missing:
        raise SystemExit(
            "Missing required MIMIC directory(ies). Expected:\n"
            + "\n".join(f"- {p}" for p in missing)
            + "\n\nSee docs/MIMIC_ACCESS.md for the required layout."
        )

    print("MIMIC presence check:")
    for p in REQUIRED_DIRS:
        entries = sorted(p.glob("*"))
        print(f"- {p}: {len(entries)} entries")

    # Minimal file presence checks (best-effort; supports nested versioned folders).
    need = [
        ("MIMIC-IV-ED", "edstays.csv", "data/raw/mimic-iv-ed", "**/edstays.csv*"),
        ("MIMIC-IV-ED", "triage.csv", "data/raw/mimic-iv-ed", "**/triage.csv*"),
        ("MIMIC-IV-ED", "diagnosis.csv", "data/raw/mimic-iv-ed", "**/diagnosis.csv*"),
        ("MIMIC-IV", "patients.csv", "data/raw/mimic-iv", "**/hosp/patients.csv*"),
    ]
    for ds, label, root, pattern in need:
        rootp = Path(root)
        matches = sorted(rootp.glob(pattern))
        if not matches:
            raise SystemExit(f"Missing required file for {ds}: {label} (pattern {pattern!r} under {rootp})")
    print("Key files: OK")
    print("MIMIC presence: OK")


if __name__ == "__main__":
    main()
