#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def doi_to_url(doi: str) -> str:
    doi = doi.strip()
    return "https://doi.org/" + urllib.parse.quote(doi, safe="/")


def slugify_doi(doi: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", doi.lower()).strip("_")


def http_get_json(url: str, *, user_agent: str, timeout_s: int = 30) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = int(resp.status)
            data = resp.read().decode("utf-8")
            return status, json.loads(data)
    except urllib.error.HTTPError as e:
        status = int(e.code)
        try:
            data = e.read().decode("utf-8", errors="replace")
            # Crossref may return plain text on 404; keep JSON empty.
            return status, json.loads(data)
        except Exception:
            return status, {}


def extract_references_with_dois(manuscript_md: Path) -> list[dict]:
    text = manuscript_md.read_text()
    if "# References" not in text:
        raise SystemExit(f"Could not find '# References' section in {manuscript_md}")
    refs_text = text.split("# References", 1)[1]

    refs: list[dict] = []
    for raw_line in refs_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\.\s+", line)
        if not m:
            # stop when leaving reference list
            if refs:
                break
            continue
        ref_n = int(m.group(1))
        doi_m = re.search(r"\bdoi:([^\s]+)", line, flags=re.IGNORECASE)
        if not doi_m:
            raise SystemExit(f"Missing DOI on reference {ref_n}: {line}")
        doi = doi_m.group(1).strip().rstrip(".")
        if not re.fullmatch(r"10\.[0-9]{4,9}/\S+", doi):
            raise SystemExit(f"Invalid DOI format on reference {ref_n}: {doi!r}")
        refs.append({"ref_n": ref_n, "doi": doi, "line": line})

    if not refs:
        raise SystemExit(f"No numbered references found after '# References' in {manuscript_md}")
    return refs


def extract_dois_from_citation_tsv(tsv_path: Path, *, ref_col: str = "ref_num", doi_col: str = "doi") -> list[dict]:
    if not tsv_path.exists():
        raise SystemExit(f"Missing citation TSV: {tsv_path}")

    refs: list[dict] = []
    with tsv_path.open("r", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        if r.fieldnames is None:
            raise SystemExit(f"Empty TSV (no header): {tsv_path}")
        if doi_col not in r.fieldnames:
            raise SystemExit(f"Missing DOI column {doi_col!r} in {tsv_path} (cols={r.fieldnames})")
        if ref_col not in r.fieldnames:
            raise SystemExit(f"Missing ref column {ref_col!r} in {tsv_path} (cols={r.fieldnames})")

        for row in r:
            ref_raw = (row.get(ref_col) or "").strip()
            doi = (row.get(doi_col) or "").strip().rstrip(".")
            if not ref_raw:
                continue
            try:
                ref_n = int(ref_raw)
            except Exception:
                raise SystemExit(f"Invalid {ref_col} value {ref_raw!r} in {tsv_path}")
            if not doi:
                raise SystemExit(f"Missing DOI for reference {ref_n} in {tsv_path}")
            if not re.fullmatch(r"10\.[0-9]{4,9}/\S+", doi):
                raise SystemExit(f"Invalid DOI format for reference {ref_n}: {doi!r}")
            refs.append({"ref_n": ref_n, "doi": doi, "line": ""})

    if not refs:
        raise SystemExit(f"No DOIs found in {tsv_path}")
    refs = sorted(refs, key=lambda x: int(x["ref_n"]))
    return refs


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=False)
    src.add_argument("--citation-tsv", type=Path, default=Path("docs/CITATION_VERIFICATION.tsv"))
    src.add_argument("--manuscript", type=Path, default=None, help="Optional: extract DOIs from a markdown reference list.")
    ap.add_argument("--citation-ref-col", type=str, default="ref_num")
    ap.add_argument("--citation-doi-col", type=str, default="doi")
    ap.add_argument("--out", type=Path, default=Path("docs/doi_evidence/doi_evidence.tsv"))
    ap.add_argument("--raw-dir", type=Path, default=Path("docs/doi_evidence/raw"))
    ap.add_argument("--mailto", type=str, default="2008001@qzmc.edu.cn")
    ap.add_argument("--sleep-s", type=float, default=0.25)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero if any DOI cannot be verified.")
    args = ap.parse_args()

    user_agent = f"doi-evidence/0.1 (mailto:{args.mailto})"
    if args.manuscript is not None:
        refs = extract_references_with_dois(Path(args.manuscript))
    else:
        refs = extract_dois_from_citation_tsv(
            Path(args.citation_tsv),
            ref_col=str(args.citation_ref_col),
            doi_col=str(args.citation_doi_col),
        )

    crossref_dir = args.raw_dir / "crossref"
    datacite_dir = args.raw_dir / "datacite"
    crossref_dir.mkdir(parents=True, exist_ok=True)
    datacite_dir.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    missing: list[dict] = []

    for ref in refs:
        ref_n = ref["ref_n"]
        doi = ref["doi"]
        doi_url = doi_to_url(doi)
        slug = slugify_doi(doi)

        crossref_api_url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
        datacite_api_url = "https://api.datacite.org/dois/" + urllib.parse.quote(doi, safe="")

        crossref_path = crossref_dir / f"{slug}.json"
        datacite_path = datacite_dir / f"{slug}.json"

        crossref_status = ""
        datacite_status = ""
        crossref_found = False
        datacite_found = False

        title = ""
        publisher = ""
        year = ""
        registry = ""
        notes = ""

        # Crossref evidence (attempt for every DOI, even if DataCite-registered).
        if (not crossref_path.exists()) or args.force:
            last_status = None
            last_json: dict = {}
            for attempt in range(args.retries):
                status, data = http_get_json(crossref_api_url, user_agent=user_agent)
                last_status, last_json = status, data
                if status in (429, 500, 502, 503, 504):
                    time.sleep(1.0 + attempt)
                    continue
                break
            crossref_status = str(last_status)
            crossref_path.write_text(json.dumps(last_json, ensure_ascii=False, indent=2))
        else:
            crossref_status = "cached"

        # Interpret Crossref result
        try:
            crossref_json = json.loads(crossref_path.read_text())
        except Exception:
            crossref_json = {}
        if crossref_json.get("status") == "ok" and isinstance(crossref_json.get("message"), dict):
            crossref_found = True
            registry = "Crossref"
            msg = crossref_json["message"]
            title = (msg.get("title") or [""])[0] if isinstance(msg.get("title"), list) else (msg.get("title") or "")
            publisher = msg.get("publisher") or ""
            year = ""
            issued = msg.get("issued", {})
            if isinstance(issued, dict):
                dp = issued.get("date-parts")
                if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
                    year = str(dp[0][0])

        # DataCite evidence (fallback if Crossref not found).
        if not crossref_found:
            if (not datacite_path.exists()) or args.force:
                last_status = None
                last_json = {}
                for attempt in range(args.retries):
                    status, data = http_get_json(datacite_api_url, user_agent=user_agent)
                    last_status, last_json = status, data
                    if status in (429, 500, 502, 503, 504):
                        time.sleep(1.0 + attempt)
                        continue
                    break
                datacite_status = str(last_status)
                datacite_path.write_text(json.dumps(last_json, ensure_ascii=False, indent=2))
            else:
                datacite_status = "cached"

            try:
                datacite_json = json.loads(datacite_path.read_text())
            except Exception:
                datacite_json = {}
            if isinstance(datacite_json.get("data"), dict) and isinstance(datacite_json["data"].get("attributes"), dict):
                datacite_found = True
                registry = "DataCite"
                attr = datacite_json["data"]["attributes"]
                publisher = attr.get("publisher") or ""
                titles = attr.get("titles") or []
                if isinstance(titles, list) and titles:
                    t0 = titles[0]
                    if isinstance(t0, dict):
                        title = t0.get("title") or title
                dates = attr.get("dates") or []
                if isinstance(dates, list):
                    # Prefer issued/publication year if present
                    for d in dates:
                        if isinstance(d, dict) and d.get("dateType") in ("Issued", "Publication"):
                            v = str(d.get("date") or "")
                            if v:
                                year = v.split("-", 1)[0]
                                break
                if not year:
                    pub_year = attr.get("publicationYear")
                    if pub_year:
                        year = str(pub_year)

        if not crossref_found and not datacite_found:
            notes = "NOT_FOUND_IN_CROSSREF_OR_DATACITE"
            missing.append(ref)
        elif registry == "DataCite" and not crossref_found:
            notes = "NOT_FOUND_IN_CROSSREF_FALLBACK_DATACITE"

        rows.append(
            {
                "ref_n": str(ref_n),
                "doi": doi,
                "doi_url": doi_url,
                "registry_verified": registry or "",
                "crossref_status": crossref_status,
                "crossref_found": "1" if crossref_found else "0",
                "datacite_status": datacite_status,
                "datacite_found": "1" if datacite_found else "0",
                "title": title,
                "publisher": publisher,
                "year": year,
                "checked_at_utc": utc_now_iso(),
                "crossref_api_url": crossref_api_url,
                "datacite_api_url": datacite_api_url,
                "notes": notes,
            }
        )

        time.sleep(max(0.0, float(args.sleep_s)))

    fieldnames = [
        "ref_n",
        "doi",
        "doi_url",
        "registry_verified",
        "crossref_status",
        "crossref_found",
        "datacite_status",
        "datacite_found",
        "title",
        "publisher",
        "year",
        "checked_at_utc",
        "crossref_api_url",
        "datacite_api_url",
        "notes",
    ]
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Wrote DOI evidence TSV -> {args.out}")
    if missing:
        print(f"Missing DOI registry evidence for {len(missing)}/{len(refs)} references:")
        for r in missing:
            print(f" - [{r['ref_n']}] {r['doi']}")
        if args.strict:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
