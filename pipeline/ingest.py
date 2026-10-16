"""SEC ingestion: rate-limited SEC client and the load of each configured filer's filing.

Run: python -m pipeline.ingest [--filers ads,hps,orcic]
One transaction per filing: the filing row and its schedule rows (raw_filings, raw_holdings).
A rerun is a no-op. Per-filer parsing lives in pipeline/adapters.py.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import threading
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import requests
import yaml
from lxml import etree

CONFIG_PATH = Path(__file__).with_name("config.yaml")
RAW_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
ADS_CIK = "0001837532"
ADS_EXPECTED_NAME = "Apollo Debt Solutions BDC"


def load_sec_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["sec"]


class SecClient:
    """Minimal SEC HTTP client: User-Agent from env, rate limit, backoff on 429/5xx."""

    def __init__(self, user_agent: str | None = None, sec_config: dict | None = None):
        ua = user_agent if user_agent is not None else os.environ.get("SEC_USER_AGENT", "")
        if not ua.strip():
            raise RuntimeError(
                "SEC_USER_AGENT is not set. SEC requires a User-Agent with your name and "
                "email, for example: SEC_USER_AGENT='Jane Doe jane@example.com'"
            )
        cfg = sec_config or load_sec_config()
        self.min_interval = 1.0 / float(cfg["max_requests_per_second"])
        self.backoff = [float(s) for s in cfg["backoff_seconds"]]
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
        self._lock = threading.Lock()
        self._last = 0.0
        self.status_log: list[tuple[str, int]] = []

    def _throttle(self) -> None:
        with self._lock:
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def get(self, url: str, timeout: float = 30.0) -> requests.Response:
        attempts = len(self.backoff) + 1
        for i in range(attempts):
            self._throttle()
            resp = self.session.get(url, timeout=timeout)
            self.status_log.append((url, resp.status_code))
            retryable = resp.status_code == 429 or 500 <= resp.status_code < 600
            if not retryable:
                if resp.status_code == 403:
                    raise RuntimeError(f"403 Forbidden from SEC for {url}. Check SEC_USER_AGENT.")
                resp.raise_for_status()
                return resp
            if i < len(self.backoff):
                time.sleep(self.backoff[i])
        resp.raise_for_status()
        return resp

    def get_json(self, url: str) -> dict:
        return self.get(url).json()


def recent_10q(submissions: dict, n: int = 10) -> list[dict]:
    r = submissions["filings"]["recent"]
    rows = [
        {"accession": r["accessionNumber"][i], "period_end": r["reportDate"][i], "filing_date": r["filingDate"][i]}
        for i in range(len(r["form"]))
        if r["form"][i] == "10-Q"
    ]
    rows.sort(key=lambda x: x["filing_date"], reverse=True)
    return rows[:n]


def filing_folder_url(cik: str | int, accession: str) -> str:
    return f"{ARCHIVES}/{int(cik)}/{accession.replace('-', '')}/"


def find_primary_document(client: SecClient, cik: str | int, accession: str) -> tuple[str, str]:
    """Return (filename, url) of the primary Inline XBRL document.

    Uses the filing folder index.json for the file list and the submissions
    feed's primaryDocument field to pick the main document (not an exhibit).
    """
    folder = filing_folder_url(cik, accession)
    index = client.get_json(folder + "index.json")
    files = {item["name"] for item in index["directory"]["item"]}
    subs = client.get_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    r = subs["filings"]["recent"]
    primary = None
    for i, acc in enumerate(r["accessionNumber"]):
        if acc == accession:
            primary = r["primaryDocument"][i]
            break
    if not primary:
        raise RuntimeError(f"{accession} not in recent filings for CIK {cik}")
    if primary not in files:
        raise RuntimeError(f"Primary document {primary} not listed in {folder}")
    return primary, folder + primary


def download_filing(client: SecClient, cik: str | int, accession: str, label: str,
                    period_end: str, dest_dir: Path = RAW_DIR) -> tuple[Path, str]:
    """Download the primary document to dest_dir/<label>_10q_<period_end>.htm."""
    _, url = find_primary_document(client, cik, accession)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{label}_10q_{period_end}.htm"
    path.write_bytes(client.get(url, timeout=120).content)
    return path, url


def inspect_ixbrl(path: Path) -> dict:
    """Count ix:nonFraction facts and distinct contexts; check for a Schedule of Investments."""
    ix = "http://www.xbrl.org/2013/inlineXBRL"
    xbrli = "http://www.xbrl.org/2003/instance"
    tree = etree.parse(str(path), etree.XMLParser(huge_tree=True, recover=True))
    facts = tree.findall(f".//{{{ix}}}nonFraction")
    ctx_refs = {f.get("contextRef") for f in facts}
    ctx_defs = tree.findall(f".//{{{xbrli}}}context")
    text = " ".join(tree.getroot().itertext())
    return {
        "size_bytes": path.stat().st_size,
        "nonfraction_facts": len(facts),
        "distinct_contexts_used": len(ctx_refs),
        "contexts_defined": len(ctx_defs),
        "has_schedule_of_investments": bool(re.search(r"schedule of investments", text, re.I)),
    }


def phase0_check() -> int:
    """Phase 0 check, kept for reference: confirm the CIK name and list recent 10-Q filings."""
    client = SecClient()
    url = f"https://data.sec.gov/submissions/CIK{ADS_CIK}.json"
    data = client.get_json(url)
    name = data.get("name", "")
    print(f"CIK {data.get('cik')} name: {name}")
    ok = name.strip().lower() == ADS_EXPECTED_NAME.lower()
    print(f"Name matches '{ADS_EXPECTED_NAME}': {ok}")
    print("\n10 most recent 10-Q filings:")
    print(f"{'accession':<22} {'period_end':<12} {'filing_date':<12}")
    for row in recent_10q(data):
        print(f"{row['accession']:<22} {row['period_end']:<12} {row['filing_date']:<12}")
    n403 = sum(1 for _, s in client.status_log if s == 403)
    print(f"\nRequests: {len(client.status_log)}, statuses: {[s for _, s in client.status_log]}, 403s: {n403}")
    return 0 if ok and n403 == 0 else 1


HASHES_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "filing_hashes.json"


class CommittedHashMismatch(RuntimeError):
    """A filing document differs from the hash committed in fixtures/filing_hashes.json."""


def check_committed_hash(key: str, period_end: date, accession: str, sha256: str,
                         hashes_path: Path = HASHES_PATH) -> str:
    """Compare the document hash and accession with the committed record. Returns 'ok' or
    'no committed hash'. Raises CommittedHashMismatch, naming both values, on any difference."""
    import json

    recorded = json.loads(hashes_path.read_text(encoding="utf-8")) if hashes_path.exists() else {}
    entry = recorded.get(period_end.isoformat(), {}).get(key)
    if entry is None:
        return "no committed hash"
    if entry["accession"] != accession:
        raise CommittedHashMismatch(
            f"[{key}] accession differs. committed {entry['accession']}, EDGAR now lists {accession}.")
    if entry["sha256"] != sha256:
        raise CommittedHashMismatch(
            f"[{key}] {accession} document hash differs. "
            f"committed sha256: {entry['sha256']}  downloaded sha256: {sha256}")
    return "ok"


class HashMismatch(RuntimeError):
    """The document on disk differs from the hash recorded when the filing was loaded."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def insert_filing(conn, filing: dict, holdings: list[tuple], sha256: str) -> tuple[str, int | None, int]:
    """One transaction per filing. Returns (status, filing_id, holdings inserted).

    status is 'loaded' (new filing), 'unchanged' (accession already loaded, hash matches, nothing
    written) or 'hash_recorded' (already loaded before hashes existed: the hash is recorded once).
    Raises HashMismatch when the filing is loaded and the hash differs."""
    with conn.transaction():
        row = conn.execute(
            "INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, "
            "accession_number, source_url, source_sha256) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (accession_number) DO NOTHING RETURNING filing_id",
            (filing["cik"], filing["bdc_name"], filing["form_type"], filing["period_end"],
             filing["filing_date"], filing["accession"], filing["source_url"], sha256),
        ).fetchone()
        if row is None:
            recorded = conn.execute(
                "SELECT filing_id, source_sha256 FROM raw_filings WHERE accession_number = %s",
                (filing["accession"],),
            ).fetchone()
            filing_id, stored = recorded
            if stored is None:
                conn.execute("UPDATE raw_filings SET source_sha256 = %s WHERE filing_id = %s", (sha256, filing_id))
                return "hash_recorded", filing_id, 0
            if stored != sha256:
                raise HashMismatch(
                    f"{filing['accession']}: file sha256 {sha256[:12]} differs from recorded {stored[:12]}")
            return "unchanged", filing_id, 0
        filing_id = row[0]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO raw_holdings (filing_id, portfolio_company_raw, industry_raw, "
                "instrument_type_raw, interest_rate_raw, maturity_date_raw, principal_raw, "
                "principal_unit_raw, cost_raw, fair_value_raw, footnotes_raw, row_order, source_url) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [(filing_id, *h) for h in holdings],
            )
    return "loaded", filing_id, len(holdings)


def load_filer(conn, client: SecClient, key: str, cfg: dict, period_end: date):
    """Look up one filer's filing for period_end, read the saved document, run its adapter and load it.
    Returns (status, filing_id, holdings inserted, adapter stats)."""
    from pipeline.adapters import Filing, make_adapter

    cik = cfg["cik"]
    subs = client.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    edgar_name = subs.get("name", "")
    if cfg["expected_name_fragment"] not in edgar_name.strip().lower():
        raise RuntimeError(f"CIK {cik} name is {edgar_name!r}, expected it to contain {cfg['expected_name_fragment']!r}")
    match = [r for r in recent_10q(subs, n=50) if r["period_end"] == period_end.isoformat()]
    if len(match) != 1:
        raise RuntimeError(f"{key}: expected 1 {cfg['form_type']} for {period_end}, found {len(match)}")
    accession = match[0]["accession"]
    _, source_url = find_primary_document(client, cik, accession)
    path = RAW_DIR / f"{cfg['fixture_label']}_10q_{period_end.isoformat()}.htm"
    if not path.exists():
        path, _ = download_filing(client, cik, accession, cfg["fixture_label"], period_end.isoformat())
    sha = sha256_file(path)
    committed = check_committed_hash(key, period_end, accession, sha)
    filing = Filing(label=cfg["fixture_label"], cik=cik, edgar_name=edgar_name, period_end=period_end,
                    path=path, source_url=source_url, accession=accession)
    adapter = make_adapter(key, cfg)
    holdings = adapter.parse(filing)
    meta = {"cik": cik, "bdc_name": edgar_name, "form_type": cfg["form_type"], "period_end": period_end,
            "filing_date": match[0]["filing_date"], "accession": accession, "source_url": source_url}
    status, filing_id, n = insert_filing(conn, meta, holdings, sha)
    adapter.stats["committed_hash_" + committed.replace(" ", "_")] = 1
    return status, filing_id, n, adapter.stats


def main(argv: list[str] | None = None) -> int:
    import argparse

    import psycopg

    from pipeline.config import load_config, load_env_file, measured_period_end

    parser = argparse.ArgumentParser(description="Load the measured quarter's filings into raw_filings and raw_holdings.")
    parser.add_argument("--filers", default="", help="comma separated filer keys from config.yaml (default: all)")
    args = parser.parse_args(argv)

    load_env_file()
    period_end = measured_period_end()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    filers = load_config()["filers"]
    wanted = [k.strip() for k in args.filers.split(",") if k.strip()] or list(filers)
    unknown = [k for k in wanted if k not in filers]
    if unknown:
        raise RuntimeError(f"unknown filer keys {unknown}; config.yaml has {list(filers)}")

    client = SecClient()
    code = 0
    with psycopg.connect(url) as conn:
        for key in wanted:
            try:
                status, filing_id, n, stats = load_filer(conn, client, key, filers[key], period_end)
            except CommittedHashMismatch as e:
                print("!!! FILING DOCUMENT DOES NOT MATCH THE COMMITTED HASH. Nothing was loaded for this filer. !!!")
                print(f"    {e}")
                return 2
            except HashMismatch as e:
                print(f"[{key}] Refused: the filing document on disk does not match the recorded hash. {e}")
                code = 1
                continue
            if status == "loaded":
                print(f"[{key}] Loaded filing_id {filing_id} with {n} holdings for {period_end}.")
            elif status == "hash_recorded":
                print(f"[{key}] Already loaded (filing_id {filing_id}), no changes to holdings. Document hash recorded for the first time.")
            else:
                print(f"[{key}] Already loaded (filing_id {filing_id}), no changes.")
            for k in sorted(stats):
                print(f"      {k}: {stats[k]}")
    print(f"SEC requests: {len(client.status_log)}, 403s: {sum(1 for _, s in client.status_log if s == 403)}")
    return code


if __name__ == "__main__":
    sys.exit(main())
