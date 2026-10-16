"""ingest fails loudly, naming both hashes, when a filing document differs from the committed hash."""
import json
from datetime import date

import pytest

from pipeline.ingest import CommittedHashMismatch, HASHES_PATH, check_committed_hash

PERIOD = date(2026, 6, 30)


def _write(tmp_path, entry):
    path = tmp_path / "hashes.json"
    path.write_text(json.dumps({"2026-06-30": {"ads": entry}}), encoding="utf-8")
    return path


def test_matching_hash_passes(tmp_path):
    path = _write(tmp_path, {"accession": "0001193125-26-341358", "sha256": "a" * 64})
    assert check_committed_hash("ads", PERIOD, "0001193125-26-341358", "a" * 64, path) == "ok"


def test_different_hash_fails_and_names_both_hashes(tmp_path):
    path = _write(tmp_path, {"accession": "0001193125-26-341358", "sha256": "a" * 64})
    with pytest.raises(CommittedHashMismatch) as err:
        check_committed_hash("ads", PERIOD, "0001193125-26-341358", "b" * 64, path)
    assert "a" * 64 in str(err.value) and "b" * 64 in str(err.value)


def test_different_accession_fails(tmp_path):
    path = _write(tmp_path, {"accession": "0001193125-26-341358", "sha256": "a" * 64})
    with pytest.raises(CommittedHashMismatch):
        check_committed_hash("ads", PERIOD, "0001193125-26-000000", "a" * 64, path)


def test_filer_or_period_without_a_committed_hash_is_reported_not_failed(tmp_path):
    path = _write(tmp_path, {"accession": "x", "sha256": "a" * 64})
    assert check_committed_hash("hps", PERIOD, "x", "a" * 64, path) == "no committed hash"
    assert check_committed_hash("ads", date(2026, 3, 31), "x", "a" * 64, path) == "no committed hash"


def test_committed_file_lists_the_three_measured_filings():
    recorded = json.loads(HASHES_PATH.read_text(encoding="utf-8"))["2026-06-30"]
    assert set(recorded) == {"ads", "hps", "orcic"}
    assert all(len(v["sha256"]) == 64 and v["accession"].count("-") == 2 for v in recorded.values())
