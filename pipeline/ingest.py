"""SEC ingestion. Phase 0: rate-limited SEC client and submissions check.

Run: python -m pipeline.ingest
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import requests
import yaml

CONFIG_PATH = Path(__file__).with_name("config.yaml")
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
