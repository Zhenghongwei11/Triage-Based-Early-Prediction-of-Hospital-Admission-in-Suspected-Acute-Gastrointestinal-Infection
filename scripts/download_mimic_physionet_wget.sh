#!/usr/bin/env bash
set -euo pipefail

# Downloads MIMIC-IV (core) and MIMIC-IV-ED from PhysioNet using wget.
# Requirements:
# - Your PhysioNet account is credentialed
# - You have signed the DUA for BOTH projects:
#   - https://physionet.org/content/mimiciv/ (MIMIC-IV core)
#   - https://physionet.org/content/mimic-iv-ed/ (MIMIC-IV-ED)
#
# This script will prompt for your PhysioNet password. Do not share passwords in plaintext.

PHYSIONET_USER="${1:-}"

if [[ -z "${PHYSIONET_USER}" ]]; then
  echo "Usage: $0 <physionet_username>"
  exit 2
fi

MIMICIV_VERSION="${MIMICIV_VERSION:-3.1}"
MIMICIV_ED_VERSION="${MIMICIV_ED_VERSION:-2.2}"

mkdir -p data/raw/mimic-iv data/raw/mimic-iv-ed

WGET_EXTRA_ARGS=()
# If you are behind a proxy and seeing repeated 401s only for certain projects,
# try disabling proxy just for wget:
#   PHYSIONET_WGET_NO_PROXY=1 bash scripts/download_mimic_physionet_wget.sh <user>
if [[ "${PHYSIONET_WGET_NO_PROXY:-0}" == "1" ]]; then
  WGET_EXTRA_ARGS+=(--no-proxy)
fi

# Some proxy setups behave better if credentials are sent pre-emptively.
WGET_EXTRA_ARGS+=(--auth-no-challenge)

echo "Downloading MIMIC-IV core v${MIMICIV_VERSION} -> data/raw/mimic-iv/"
wget -r -N -c -np -nH --cut-dirs=2 \
  -P data/raw/mimic-iv \
  --user "${PHYSIONET_USER}" --ask-password \
  "${WGET_EXTRA_ARGS[@]}" \
  "https://physionet.org/files/mimiciv/${MIMICIV_VERSION}/" \
  --reject "index.html*"

echo "Downloading MIMIC-IV-ED v${MIMICIV_ED_VERSION} -> data/raw/mimic-iv-ed/"
wget -r -N -c -np -nH --cut-dirs=2 \
  -P data/raw/mimic-iv-ed \
  --user "${PHYSIONET_USER}" --ask-password \
  "${WGET_EXTRA_ARGS[@]}" \
  "https://physionet.org/files/mimic-iv-ed/${MIMICIV_ED_VERSION}/" \
  --reject "index.html*"

echo "Done. Next:"
echo "  python3 scripts/smoke_test_mimic_presence.py"
