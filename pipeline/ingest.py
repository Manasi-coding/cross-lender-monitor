"""SEC ingestion. Phase 0: rate-limited SEC client and submissions check.

Run: python -m pipeline.ingest
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
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


def main() -> int:
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


if __name__ == "__main__":
    sys.exit(main())
