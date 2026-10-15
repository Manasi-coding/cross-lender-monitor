"""SEC ingestion: rate-limited SEC client (Phase 0) and the Day 2 load of the ADS filing.

Run: python -m pipeline.ingest
Loads one filing into raw_filings and its schedule rows into raw_holdings, one transaction.
"""
from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Day 2 vertical slice: ADS filing into raw_filings and raw_holdings
# ---------------------------------------------------------------------------
ADS_FORM_TYPE = "10-Q"


def plain(value: Decimal | None) -> str | None:
    """Decimal as plain text (no exponent), as parsed. None stays None."""
    return None if value is None else format(value, "f")


def split_identifier_raw(ident: str) -> tuple[str, str | None, str | None, str | None]:
    """Raw text pieces of the ADS investment identifier, unchanged:
    '<industry> <company> Investment Type <type> Interest Rate <rate> Maturity Date <date>'.
    The industry and company run together in the first piece, so industry_raw stays NULL."""
    parts = re.split(r"\s+Investment Type\s+", ident, maxsplit=1)
    name = parts[0].strip()
    rest = parts[1] if len(parts) > 1 else None
    inst = rate = maturity = None
    if rest:
        m = re.search(r"\s+Maturity Date\s+(.*)$", rest)
        if m:
            maturity = m.group(1).strip() or None
            rest = rest[: m.start()]
        m = re.search(r"\s+Interest Rate\s+(.*)$", rest)
        if m:
            rate = m.group(1).strip() or None
            rest = rest[: m.start()]
        inst = rest.strip() or None
    return name.strip(), inst, rate, maturity


def linked_footnotes(path: Path, contexts: dict, facts: list, period_end: str) -> dict[str, list[str]]:
    """Footnote texts (ix:footnote linked by ix:relationship) of each investment identifier at period_end."""
    from pipeline.ixbrl import IDENTIFIER_AXIS, NS_IX
    root = etree.parse(str(path), etree.XMLParser(huge_tree=True, recover=True)).getroot()
    notes = {el.get("id"): " ".join("".join(el.itertext()).split())
             for el in root.iter(f"{{{NS_IX}}}footnote")}
    fact_notes: dict[str, set[str]] = {}
    for rel in root.iter(f"{{{NS_IX}}}relationship"):
        for src in (rel.get("fromRefs") or "").split():
            fact_notes.setdefault(src, set()).update((rel.get("toRefs") or "").split())
    elements = list(root.iter(f"{{{NS_IX}}}nonFraction"))
    if len(elements) != len(facts):
        raise RuntimeError("nonFraction element count differs from parsed facts")
    out: dict[str, set[str]] = {}
    for el, fact in zip(elements, facts):
        fid = el.get("id")
        if not fid or fid not in fact_notes:
            continue
        c = contexts.get(fact.context_ref)
        if c and c.instant == period_end and IDENTIFIER_AXIS in c.typed and len(c.dims) == 1:
            out.setdefault(c.typed[IDENTIFIER_AXIS], set()).update(
                notes[n] for n in fact_notes[fid] if n in notes)
    return {k: sorted(v) for k, v in out.items()}


def build_holding_rows(path: Path, period_end: str, source_url: str) -> list[tuple]:
    """One tuple per schedule row (a row with a fair value or a cost), values as parsed."""
    from pipeline.ixbrl import assemble_investments, parse_ixbrl
    contexts, facts, text_facts = parse_ixbrl(path)
    rows = assemble_investments(contexts, facts, text_facts, period_end)
    schedule = [r for r in rows if r["fair_value"] is not None or r["cost"] is not None]
    notes = linked_footnotes(path, contexts, facts, period_end)
    out = []
    for order, r in enumerate(schedule, start=1):
        name, inst, rate, maturity = split_identifier_raw(r["identifier"])
        out.append((
            name, None, inst, rate, maturity,
            plain(r["principal"]), r["principal_unit"], plain(r["cost"]), plain(r["fair_value"]),
            " | ".join(notes.get(r["identifier"], [])) or None, order, source_url,
        ))
    return out


def load_ads(conn, client: SecClient, period_end: date) -> tuple[int, int]:
    """Look up the filing, read the saved document and insert one filing and its holdings
    in one transaction. Returns (filing_id, holdings inserted)."""
    subs = client.get_json(f"https://data.sec.gov/submissions/CIK{ADS_CIK}.json")
    if subs.get("name", "").strip().lower() != ADS_EXPECTED_NAME.lower():
        raise RuntimeError(f"CIK {ADS_CIK} name is {subs.get('name')!r}, expected {ADS_EXPECTED_NAME!r}")
    match = [r for r in recent_10q(subs, n=50) if r["period_end"] == period_end.isoformat()]
    if len(match) != 1:
        raise RuntimeError(f"expected 1 {ADS_FORM_TYPE} for {period_end}, found {len(match)}")
    filing = match[0]
    _, source_url = find_primary_document(client, ADS_CIK, filing["accession"])
    path = RAW_DIR / f"ads_10q_{period_end.isoformat()}.htm"
    if not path.exists():
        path, _ = download_filing(client, ADS_CIK, filing["accession"], "ads", period_end.isoformat())
    holdings = build_holding_rows(path, period_end.isoformat(), source_url)
    with conn.transaction():
        row = conn.execute(
            "INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, "
            "accession_number, source_url) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING filing_id",
            (ADS_CIK, ADS_EXPECTED_NAME, ADS_FORM_TYPE, period_end, filing["filing_date"],
             filing["accession"], source_url),
        ).fetchone()
        filing_id = row[0]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO raw_holdings (filing_id, portfolio_company_raw, industry_raw, "
                "instrument_type_raw, interest_rate_raw, maturity_date_raw, principal_raw, "
                "principal_unit_raw, cost_raw, fair_value_raw, footnotes_raw, row_order, source_url) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [(filing_id, *h) for h in holdings],
            )
    return filing_id, len(holdings)


def main() -> int:
    import psycopg
    from pipeline.config import load_env_file, measured_period_end

    load_env_file()
    period_end = measured_period_end()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    client = SecClient()
    with psycopg.connect(url) as conn:
        try:
            filing_id, n = load_ads(conn, client, period_end)
        except psycopg.errors.UniqueViolation:
            print("This filing is already loaded (accession_number is unique). Nothing was changed.")
            return 1
    print(f"Loaded filing_id {filing_id} with {n} holdings for {period_end}.")
    print(f"SEC requests: {len(client.status_log)}, 403s: {sum(1 for _, s in client.status_log if s == 403)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
