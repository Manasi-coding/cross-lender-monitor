"""The matcher hash, the freeze and the period parameter (SPEC section 13 test 25 and section 12.6, phase_wise.md 6.8).

Test 25 (a), (b) and (c) end with the held-out draw and evaluate.py, which are Day 8 afternoon work. Here they are tested
through require_frozen_matching, the check both of them call. (d) and (e) are tested whole."""
import ast
import copy
import json
from datetime import date
from pathlib import Path

import psycopg
import pytest

from pipeline import block, config, match, normalize
from pipeline.config import (frozen_hash, freeze, load_config, matcher_hash, matcher_hash_parts, require_frozen_matching, resolve_period,
                             unfreeze)

from conftest import seed_normalized

CFG = load_config()
REPO = Path(__file__).resolve().parent.parent
P2, P1 = date(2026, 6, 30), date(2026, 3, 31)
FILES = {"pipeline/a.py": "x = 1\ny = 2\n", "pipeline/b.py": "def f():\n    return 'b'\n", "pipeline/c.py": "# c\n"}


def make_root(tmp_path: Path, eol: str = "\n", name: str = "root", files: dict | None = None) -> Path:
    root = tmp_path / name
    (root / "pipeline").mkdir(parents=True)
    for rel, text in (files or FILES).items():
        (root / rel).write_bytes(text.replace("\n", eol).encode())
    return root


def cfg_for(files=tuple(FILES)) -> dict:
    c = copy.deepcopy(CFG)
    c["freeze"]["hashed_files"] = list(files)
    return c


# ------------------------------------------------------------------ the hash
def test_hash_is_deterministic_and_ignores_key_order_and_list_order(tmp_path):
    root = make_root(tmp_path)
    c = cfg_for()
    h = matcher_hash(c, root)
    assert len(h) == 64 and h == matcher_hash(c, root)
    reordered = copy.deepcopy(c)
    reordered["freeze"]["hashed_files"] = list(reversed(reordered["freeze"]["hashed_files"]))
    reordered["bands"] = dict(reversed(list(reordered["bands"].items())))
    assert matcher_hash(reordered, root) == h


def test_hash_is_identical_for_crlf_and_lf_copies_of_the_same_files(tmp_path):
    lf, crlf = make_root(tmp_path, "\n", "lf"), make_root(tmp_path, "\r\n", "crlf")
    assert (lf / "pipeline/a.py").read_bytes() != (crlf / "pipeline/a.py").read_bytes()      # the bytes do differ
    assert matcher_hash(cfg_for(), lf) == matcher_hash(cfg_for(), crlf)


def test_hash_changes_when_one_hashed_byte_changes(tmp_path):
    root = make_root(tmp_path)
    before = matcher_hash(cfg_for(), root)
    f = root / "pipeline/b.py"
    f.write_bytes(f.read_bytes().replace(b"'b'", b"'c'"))                                  # one byte
    assert matcher_hash(cfg_for(), root) != before
    f.write_bytes(f.read_bytes().replace(b"'c'", b"'b'"))
    assert matcher_hash(cfg_for(), root) == before                                          # and back


def test_hash_changes_with_each_hashed_config_section_and_not_with_the_others(tmp_path):
    root = make_root(tmp_path)
    base = matcher_hash(cfg_for(), root)
    for path, value in ((("bands", "auto_min"), 0.93), (("blocking", "spread_window_bps"), 51), (("scoring", "scorer"), "ratio"),
                        (("normalization", "legal_form_tokens"), ["llc"]), (("normalization", "excluded_reason_order"), ["EQUITY_POSITION"]),
                        (("filers", "hps"), {"unfunded_pattern": "something else"})):
        c = cfg_for()
        c[path[0]][path[1]] = value
        assert matcher_hash(c, root) != base, path
    for path, value in ((("divergence", "mild_pts"), 9.0), (("sampling", "seed"), 99), (("sec", "max_requests_per_second"), 1)):
        c = cfg_for()
        c[path[0]][path[1]] = value
        assert matcher_hash(c, root) == base, path                                          # not part of the matcher
    for sub in (("filers", "hps", "unfunded_pattern", "something else"), ("filers", "hps", "currency_ladder", {"rungs": ["a", "b", "c"], "reference_period": "2026-06-30"}),
                ("filers", "ads", "non_accrual_pattern", "x"), ("filers", "orcic", "cik", "0000000000")):
        c = cfg_for()
        c[sub[0]][sub[1]][sub[2]] = sub[3]
        assert matcher_hash(c, root) != base, sub                                           # anything inside filers changes the hash
    for path, value in ((("freeze", "unrelated"), 1), (("currency", "principal_currency_required"), "EUR"), (("evidence", "floor_differs_bps"), 99)):
        c = cfg_for()
        c.setdefault(path[0], {})[path[1]] = value
        assert matcher_hash(c, root) == base, path                                          # still not part of the matcher


def test_hash_refuses_a_missing_file_or_an_empty_list(tmp_path):
    root = make_root(tmp_path)
    with pytest.raises(SystemExit, match="does not exist"):
        matcher_hash(cfg_for(["pipeline/a.py", "pipeline/nope.py"]), root)
    with pytest.raises(SystemExit, match="empty"):
        matcher_hash(cfg_for([]), root)


def test_the_repo_hash_covers_the_four_files_including_currency_and_is_stable():
    parts = matcher_hash_parts(CFG, REPO)
    assert list(parts["files"]) == ["pipeline/block.py", "pipeline/currency.py", "pipeline/match.py", "pipeline/normalize.py"]
    assert list(parts["config"]) == ["normalization", "blocking", "scoring", "bands", "filers"]
    assert matcher_hash(CFG, REPO) == matcher_hash(load_config(), REPO)
    for unhashed in ("pipeline/compare.py", "pipeline/link_history.py"):
        assert unhashed not in parts["files"]                                               # compare.py runs after the freeze


def test_every_pipeline_module_the_hashed_files_import_is_hashed_or_is_the_config_loader():
    hashed = {Path(p).stem for p in CFG["freeze"]["hashed_files"]}
    for rel in CFG["freeze"]["hashed_files"]:
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("pipeline"):
                mods = [node.module.split(".")[1]] if "." in node.module else [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                mods = [a.name.split(".")[1] for a in node.names if a.name.startswith("pipeline.")]
            for m in mods:
                assert m in hashed or m == "config", f"{rel} imports pipeline.{m}, which is neither hashed nor the config loader"


def test_excluded_reason_order_holds_currency_unknown_next_to_non_usd_principal():
    order = CFG["normalization"]["excluded_reason_order"]
    assert order.index("CURRENCY_UNKNOWN") == order.index("NON_USD_PRINCIPAL") + 1
    # the same reason as before for every case the single slot decided
    for ccy, expected in ((None, "CURRENCY_UNKNOWN"), ("EUR", "NON_USD_PRINCIPAL"), ("USD", None)):
        got = normalize.excluded_reason(type_norm="FIRST_LIEN", principal=1, unfunded=False, ccy=ccy, fair_value=None, cfg=CFG)
        assert got == (expected or "NULL_FAIR_VALUE"), ccy
        assert normalize.excluded_reason(type_norm="FIRST_LIEN", principal=1, unfunded=False, ccy=ccy, fair_value=1, cfg=CFG) == expected


# ------------------------------------------------------------------ the freeze (test 25)
def test_freeze_records_one_row_with_the_hash_and_refuses_a_second_time(migrated_db, tmp_path):
    root, c = make_root(tmp_path), cfg_for()
    with psycopg.connect(migrated_db) as conn:
        assert frozen_hash(conn) is None
        h = freeze(conn, c, root, git_sha="abc123")
        assert h == matcher_hash(c, root) and frozen_hash(conn) == h
        assert conn.execute("SELECT count(*), min(git_sha) FROM matcher_freeze").fetchone() == (1, "abc123")
        with pytest.raises(SystemExit, match="already frozen"):
            freeze(conn, c, root)
        assert conn.execute("SELECT count(*) FROM matcher_freeze").fetchone()[0] == 1


def test_25a_the_check_refuses_with_no_freeze_row(migrated_db, tmp_path):
    root = make_root(tmp_path)
    with psycopg.connect(migrated_db) as conn:
        with pytest.raises(SystemExit, match="no matcher_freeze row"):
            require_frozen_matching(conn, "the held-out draw", cfg_for(), root)


def test_25b_and_25c_an_edit_to_a_hashed_file_or_config_key_after_the_freeze_is_refused(migrated_db, tmp_path):
    root = make_root(tmp_path)
    with psycopg.connect(migrated_db) as conn:
        h = freeze(conn, cfg_for(), root)
        assert require_frozen_matching(conn, "the held-out draw", cfg_for(), root) == h              # unchanged: allowed
        f = root / "pipeline/a.py"
        f.write_text(f.read_text() + "z = 3\n")                                                       # a source edit
        with pytest.raises(SystemExit) as err:
            require_frozen_matching(conn, "the held-out draw", cfg_for(), root)
        assert "matcher changed since the freeze" in str(err.value) and h in str(err.value) and matcher_hash(cfg_for(), root) in str(err.value)
        f.write_text(FILES["pipeline/a.py"])                                                           # restored: allowed again
        assert require_frozen_matching(conn, "evaluate.py", cfg_for(), root) == h
        c = cfg_for()
        c["bands"]["auto_min"] = 0.91                                                                  # a hashed config key
        with pytest.raises(SystemExit, match="matcher changed"):
            require_frozen_matching(conn, "evaluate.py", c, root)


def test_25d_normalize_block_and_match_refuse_while_frozen(migrated_db, monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("MEASURED_PERIOD_END", "2026-06-30")
    monkeypatch.setattr(block, "RUN_TIMES", tmp_path / "rt.jsonl")
    with psycopg.connect(migrated_db) as conn:
        conn.execute("INSERT INTO matcher_freeze (matcher_config_hash) VALUES ('abc')")
        conn.commit()
        for name, call in (("normalize", lambda: normalize.run(conn, P2, CFG, verbose=False)), ("match", lambda: match.run(conn, P2, CFG)),
                           ("block", lambda: block.main([])), ("match main", lambda: match.main([]))):
            with pytest.raises(SystemExit) as err:
                call()
            assert "frozen" in str(err.value), name


def seed_heldout(conn):
    a, b, c, d = seed_normalized(conn, [
        {"bdc_cik": "0000000001", "period_end_date": P2, "borrower_normalized": "x", "instrument_type_norm": "FIRST_LIEN"},
        {"bdc_cik": "0000000002", "period_end_date": P2, "borrower_normalized": "x", "instrument_type_norm": "FIRST_LIEN"},
        {"bdc_cik": "0000000001", "period_end_date": P2, "borrower_normalized": "y", "instrument_type_norm": "FIRST_LIEN"},
        {"bdc_cik": "0000000002", "period_end_date": P2, "borrower_normalized": "y", "instrument_type_norm": "FIRST_LIEN"}])
    ids = {}
    for phase, (x, y), band in (("TUNING", (a, b), None), ("HELDOUT", (c, d), "AUTO")):
        sid = conn.execute("INSERT INTO label_samples (holding_id_a, holding_id_b, phase, score_band, draw_order) VALUES (%s, %s, %s, %s, 1) RETURNING sample_id",
                           (x, y, phase, band)).fetchone()[0]
        conn.execute("INSERT INTO labeled_pairs (sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method, score_band) VALUES (%s, %s, %s, 'MATCH', 't', %s, %s)",
                     (sid, x, y, "BLOCKED" if phase == "TUNING" else "STRATIFIED", band))
        ids[phase] = sid
    conn.execute("INSERT INTO band_sizes (score_band, band_size, sample_size, matcher_config_hash) VALUES ('AUTO', 10, 1, 'h')")
    conn.execute("INSERT INTO metric_results (matcher_config_hash, payload) VALUES ('h', '{}')")
    conn.execute("INSERT INTO matcher_freeze (matcher_config_hash) VALUES ('h')")
    conn.commit()
    return ids


def counts(conn):
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("matcher_freeze", "label_samples", "labeled_pairs", "band_sizes", "metric_results")}


def test_25e_unfreeze_removes_the_freeze_and_every_held_out_artifact_and_keeps_tuning(migrated_db, tmp_path):
    with psycopg.connect(migrated_db) as conn:
        ids = seed_heldout(conn)
        assert counts(conn) == {"matcher_freeze": 1, "label_samples": 2, "labeled_pairs": 2, "band_sizes": 1, "metric_results": 1}
        res = unfreeze(conn, tmp_path / "backups", confirmed=True)
        assert counts(conn) == {"matcher_freeze": 0, "label_samples": 1, "labeled_pairs": 1, "band_sizes": 0, "metric_results": 0}
        assert conn.execute("SELECT sample_id, phase FROM label_samples").fetchall() == [(ids["TUNING"], "TUNING")]
        assert conn.execute("SELECT sampling_method FROM labeled_pairs").fetchall() == [("BLOCKED",)]
    dump = json.loads(Path(res["backup"]).read_text())
    assert (len(dump["label_samples_heldout"]), len(dump["labeled_pairs_heldout"]), len(dump["band_sizes"]), len(dump["metric_results"]), len(dump["matcher_freeze"])) == (1, 1, 1, 1, 1)
    assert dump["label_samples_heldout"][0]["sample_id"] == ids["HELDOUT"]
    assert res["label_samples_heldout"] == 1 and Path(res["backup"]).parent == tmp_path / "backups"


def test_unfreeze_does_nothing_without_confirmation(migrated_db, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)                                  # the backup folder is under REPO_ROOT
    with psycopg.connect(migrated_db) as conn:
        seed_heldout(conn)
        before = counts(conn)
        with pytest.raises(SystemExit, match="not confirmed"):
            unfreeze(conn, tmp_path / "backups", confirmed=False)
        monkeypatch.setattr("builtins.input", lambda *_: "no")
        with pytest.raises(SystemExit, match="not confirmed"):
            config.main(["--unfreeze"])
        assert counts(conn) == before and not (tmp_path / "backups").exists()
        monkeypatch.setattr("builtins.input", lambda *_: "UNFREEZE")
        assert config.main(["--unfreeze"]) == 0
        assert counts(conn)["matcher_freeze"] == 0 and len(list((tmp_path / "backups").glob("unfreeze_*.json"))) == 1


def test_cli_hash_prints_the_hash_and_freeze_records_it(migrated_db, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    assert config.main(["--hash"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == matcher_hash(load_config(), REPO) and any(line.startswith("  file pipeline/currency.py ") for line in out)
    assert config.main(["--freeze"]) == 0
    with psycopg.connect(migrated_db) as conn:
        assert frozen_hash(conn) == out[0]
    with pytest.raises(SystemExit, match="already frozen"):
        config.main(["--freeze"])


# ------------------------------------------------------------------ the period parameter
def row(cik, name, period):
    return {"bdc_cik": cik, "period_end_date": period, "borrower_normalized": name, "instrument_type_norm": "FIRST_LIEN"}


def test_resolve_period_defaults_to_the_measured_period_and_rejects_a_bad_date(monkeypatch):
    monkeypatch.setenv("MEASURED_PERIOD_END", "2026-06-30")
    assert resolve_period(None) == P2 and resolve_period("2026-03-31") == P1
    with pytest.raises(SystemExit, match="ISO date"):
        resolve_period("31/03/2026")


def test_block_and_match_run_for_the_named_period_only_and_default_to_the_measured_one(migrated_db, monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("MEASURED_PERIOD_END", "2026-06-30")
    monkeypatch.setattr(block, "RUN_TIMES", tmp_path / "rt.jsonl")
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [row("0000000001", "acme", P2), row("0000000002", "acme", P2), row("0000000001", "zed", P1), row("0000000002", "zed", P1)])
        conn.commit()

    def state():
        with psycopg.connect(migrated_db) as conn:
            keys = conn.execute("SELECT n.period_end_date, count(*) FROM blocking_keys k JOIN normalized_holdings n USING (holding_id) GROUP BY 1 ORDER BY 1").fetchall()
            pairs = conn.execute("SELECT a.period_end_date, count(*) FROM candidate_pairs c JOIN normalized_holdings a ON a.holding_id = c.holding_id_a GROUP BY 1 ORDER BY 1").fetchall()
        return dict(keys), dict(pairs)

    assert block.main([]) == 0 and match.main([]) == 0                                  # no argument: the measured period
    assert state() == ({P2: 4}, {P2: 1})
    assert block.main(["--period", "2026-03-31"]) == 0                                  # the out-of-time run names its period
    assert state() == ({P1: 4, P2: 4}, {P2: 1})
    assert match.main(["--period", "2026-03-31"]) == 0
    assert state() == ({P1: 4, P2: 4}, {P1: 1, P2: 1})                                  # the measured period's rows were not touched
    with pytest.raises(SystemExit):
        block.main(["--period", "nonsense"])
