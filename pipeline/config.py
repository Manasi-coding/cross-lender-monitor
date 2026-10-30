"""Config loading, the matcher hash and the freeze (SPEC sections 12.6 and 13 test 25, phase_wise.md 6.8).

Tunables come from config.yaml, the measured quarter from env.

The matcher hash is sha256 over a canonical JSON document with two parts: the normalization, blocking, scoring,
bands and filers sections of config.yaml, and the sha256 of each file in freeze.hashed_files with CRLF turned into LF (so
a Windows checkout and CI agree). Keys are sorted and files are taken in sorted path order, so the list order does not
matter. filers is included because normalize.py reads it (unfunded and non-accrual patterns, the currency ladder). Anything
else (sampling, divergence, evidence, sec, currency, freeze) is not part of it.

Commands:
  python -m pipeline.config --hash       print the current hash (read only)
  python -m pipeline.config --freeze     insert the single matcher_freeze row; refuses if one exists
  python -m pipeline.config --unfreeze   dump the held-out artifacts to backups/ as JSON, delete them and the freeze row
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).with_name("config.yaml")
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
REPO_ROOT = Path(__file__).resolve().parent.parent
MATCHER_SECTIONS = ("normalization", "blocking", "scoring", "bands", "filers")


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Return config.yaml parsed as a dict. Nothing is added or changed."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _env_file_value(key: str, env_path: Path = ENV_PATH) -> str | None:
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return None


def measured_period_end(env_path: Path = ENV_PATH) -> date:
    """MEASURED_PERIOD_END from the environment, falling back to .env. ISO date, required."""
    raw = os.environ.get("MEASURED_PERIOD_END") or _env_file_value("MEASURED_PERIOD_END", env_path)
    if not raw or not raw.strip():
        raise RuntimeError("MEASURED_PERIOD_END is not set. Put an ISO date such as 2026-06-30 in .env.")
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as e:
        raise RuntimeError(f"MEASURED_PERIOD_END must be an ISO date (YYYY-MM-DD), got {raw!r}") from e


def load_env_file(env_path: Path = ENV_PATH) -> None:
    """Load KEY=VALUE lines from .env into os.environ without overriding variables already set."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def resolve_period(arg: str | None) -> date:
    """The period a stage runs for: an explicit --period (YYYY-MM-DD), else MEASURED_PERIOD_END from the environment."""
    if arg is None:
        return measured_period_end()
    try:
        return date.fromisoformat(arg.strip())
    except ValueError as e:
        raise SystemExit(f"--period must be an ISO date (YYYY-MM-DD), got {arg!r}") from e


# --------------------------------------------------------------------------- the matcher hash
def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def matcher_hash_parts(cfg: dict | None = None, root: Path = REPO_ROOT) -> dict:
    """{"config": {section: value}, "files": {relative posix path: sha256 of the LF content}}."""
    cfg = cfg if cfg is not None else load_config()
    missing = [s for s in MATCHER_SECTIONS if s not in cfg]
    if missing:
        raise SystemExit(f"config.yaml has no {missing} section: the matcher hash needs {list(MATCHER_SECTIONS)}.")
    listed = cfg.get("freeze", {}).get("hashed_files")
    if not listed:
        raise SystemExit("config.yaml freeze.hashed_files is empty: the matcher hash needs the matcher source files.")
    files = {}
    for rel in sorted({Path(p).as_posix() for p in listed}):
        f = root / rel
        if not f.is_file():
            raise SystemExit(f"freeze.hashed_files names {rel}, which does not exist under {root}.")
        files[rel] = _file_digest(f)
    return {"config": {s: cfg[s] for s in MATCHER_SECTIONS}, "files": files}


def matcher_hash(cfg: dict | None = None, root: Path = REPO_ROOT) -> str:
    doc = json.dumps(matcher_hash_parts(cfg, root), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(doc.encode("ascii")).hexdigest()


def git_info(root: Path = REPO_ROOT, files: list[str] | None = None) -> tuple[str | None, list[str]]:
    """(HEAD sha or None, hashed files with uncommitted changes). Best effort: no git, no sha."""
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", *(files or [])], cwd=root, capture_output=True, text=True, check=True).stdout
        return sha, [line[3:] for line in dirty.splitlines()]
    except (OSError, subprocess.CalledProcessError):
        return None, []


# --------------------------------------------------------------------------- the freeze
def frozen_hash(conn) -> str | None:
    row = conn.execute("SELECT matcher_config_hash FROM matcher_freeze").fetchone()
    return row[0] if row else None


def freeze(conn, cfg: dict | None = None, root: Path = REPO_ROOT, git_sha: str | None = None) -> str:
    """Insert the single matcher_freeze row with the current hash. Refuses if a row already exists."""
    stored = frozen_hash(conn)
    if stored is not None:
        raise SystemExit(f"--freeze refuses: the matcher is already frozen (hash {stored}). Use --unfreeze first.")
    h = matcher_hash(cfg, root)
    with conn.transaction():
        conn.execute("INSERT INTO matcher_freeze (matcher_config_hash, git_sha) VALUES (%s, %s)", (h, git_sha))
    return h


def require_frozen_matching(conn, who: str, cfg: dict | None = None, root: Path = REPO_ROOT) -> str:
    """For the held-out draw and evaluate.py: refuse unless a freeze row exists and the current hash equals it."""
    stored = frozen_hash(conn)
    if stored is None:
        raise SystemExit(f"{who} refuses: no matcher_freeze row. Run python -m pipeline.config --freeze first.")
    current = matcher_hash(cfg, root)
    if current != stored:
        raise SystemExit(f"{who} refuses: the matcher changed since the freeze. Frozen hash {stored}, current hash {current}. "
                         "A matcher change invalidates the held-out set (SPEC section 12.6).")
    return stored


def unfreeze(conn, backup_dir: Path, confirmed: bool) -> dict:
    """Dump the held-out label_samples, held-out labeled_pairs, band_sizes and metric_results to backup_dir as JSON, delete them
    and the freeze row. Tuning samples and tuning labels stay. Nothing happens unless confirmed is True."""
    if not confirmed:
        raise SystemExit("--unfreeze not confirmed: nothing was changed.")

    def rows(sql: str) -> list[dict]:
        cur = conn.execute(sql)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    dump = {
        "dumped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "matcher_freeze": rows("SELECT * FROM matcher_freeze"),
        "label_samples_heldout": rows("SELECT * FROM label_samples WHERE phase = 'HELDOUT' ORDER BY sample_id"),
        "labeled_pairs_heldout": rows("SELECT l.* FROM labeled_pairs l JOIN label_samples s USING (sample_id) WHERE s.phase = 'HELDOUT' ORDER BY l.pair_id"),
        "band_sizes": rows("SELECT * FROM band_sizes ORDER BY score_band"),
        "metric_results": rows("SELECT * FROM metric_results ORDER BY metric_id"),
    }
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / f"unfreeze_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(dump, indent=2, default=str), encoding="utf-8")
    with conn.transaction():
        conn.execute("DELETE FROM labeled_pairs WHERE sample_id IN (SELECT sample_id FROM label_samples WHERE phase = 'HELDOUT')")
        conn.execute("DELETE FROM label_samples WHERE phase = 'HELDOUT'")
        conn.execute("DELETE FROM band_sizes")
        conn.execute("DELETE FROM metric_results")
        conn.execute("DELETE FROM matcher_freeze")
    return {"backup": str(path), **{k: len(v) for k, v in dump.items() if isinstance(v, list)}}


def main(argv: list[str] | None = None) -> int:
    import argparse

    import psycopg

    ap = argparse.ArgumentParser(description="The matcher hash and the freeze.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--hash", action="store_true", help="print the current matcher hash (read only)")
    g.add_argument("--freeze", action="store_true", help="record the matcher hash in matcher_freeze")
    g.add_argument("--unfreeze", action="store_true", help="delete the freeze and every held-out artifact (dumped to backups/ first)")
    ap.add_argument("--yes", action="store_true", help="with --unfreeze: do not ask for confirmation")
    args = ap.parse_args(argv)
    load_env_file()
    cfg = load_config()
    parts = None
    if args.hash or args.freeze:
        parts = matcher_hash_parts(cfg)
        if args.hash:
            print(matcher_hash(cfg))
            for rel, d in parts["files"].items():
                print(f"  file {rel} {d}")
            sections = hashlib.sha256(json.dumps(parts["config"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            print(f"  config sections {', '.join(MATCHER_SECTIONS)} {sections}")
            return 0
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is not set.")
    with psycopg.connect(url) as conn:
        if args.freeze:
            sha, dirty = git_info(REPO_ROOT, [*parts["files"], "pipeline/config.yaml"])   # the hashed files and the config the sections come from
            if dirty:
                print(f"warning: hashed files with uncommitted changes: {dirty}. Commit the config and code before freezing.", file=sys.stderr)
            recorded = freeze(conn, cfg, git_sha=sha)
            print(f"frozen: matcher_config_hash {recorded}, git_sha {sha}")
            return 0
        answer = "UNFREEZE" if args.yes else input("This deletes the freeze row, every held-out sample and label, band_sizes and metric_results. Type UNFREEZE to confirm: ")
        res = unfreeze(conn, REPO_ROOT / "backups", answer.strip() == "UNFREEZE")
        print("unfrozen: " + ", ".join(f"{k} {v}" for k, v in res.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
