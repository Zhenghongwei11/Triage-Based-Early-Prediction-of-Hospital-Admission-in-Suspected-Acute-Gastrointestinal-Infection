# MIMIC-IV-ED Access + Local Layout (development dataset)

We use MIMIC-IV-ED as the development dataset. This dataset typically requires:
- PhysioNet account
- CITI/required training (as specified by PhysioNet)
- Credentialing approval
- Click-through DUA (Data Use Agreement) for each project/version

## Expected local layout

Place raw files under:
- `data/raw/mimic-iv-ed/` (MIMIC-IV-ED)
- `data/raw/mimic-iv/` (MIMIC-IV core; required to derive age via `hosp/patients.csv*` anchor variables)

This project will NOT attempt to download MIMIC automatically (credentials required).

## Quick checklist (PhysioNet UI)

1. Confirm your PhysioNet account is **credentialed** (Profile → Credentialing).
2. Confirm your **training is approved** (Profile → Training).
   - PhysioNet commonly requires **CITI “Data or Specimens Only Research” including HIPAA**.
   - Upload the **Completion Report** (often named `citiCompletionReport_*.pdf`), not the “Certificate”.
3. On each dataset page, sign the DUA for the exact project/version you will download:
   - MIMIC-IV core: `mimiciv/<version>`
   - MIMIC-IV-ED: `mimic-iv-ed/<version>`

If step 2 or 3 is missing, `wget` will typically fail with `401 Unauthorized`.

## Download

We keep a helper script that downloads both projects (core + ED) and supports resume:
- `bash scripts/download_mimic_physionet_wget.sh <physionet_username>`

Notes:
- Resume is enabled via `wget -c`. If the connection drops, rerun the same command.
- If you are behind a proxy and see repeated `401` errors only for one project, retry with:
  - `PHYSIONET_WGET_NO_PROXY=1 bash scripts/download_mimic_physionet_wget.sh <physionet_username>`

## Smoke test

After downloading, run:
- `python3 scripts/smoke_test_mimic_presence.py`

If it fails, do not proceed to modeling on MIMIC; fix access/layout first.
