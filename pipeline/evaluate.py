"""evaluate.py: the label-derived evaluation (SPEC section 12.6, phase_wise.md 6.7), report only.

Run: python -m pipeline.evaluate
It refuses unless a freeze row exists and the current matcher hash equals it and the hash stored in band_sizes (and in
outoftime_band_sizes when that draw exists), or if any held-out sample is unlabeled. It reads label_samples, labeled_pairs,
band_sizes and outoftime_band_sizes only. It never reads candidate_pairs, so review-queue clicks cannot reach a number, and it
writes nothing. No result changes or suggests a threshold, a rule or a config value.

Reporting rules, fixed before the held-out labels existed (DECISIONS.md):
  Held-out (phase HELDOUT only): per band the frame size, the sampled n and the MATCH, NO_MATCH and UNSURE counts. Precision is
  MATCH / (MATCH + NO_MATCH) with UNSURE excluded, the worst case MATCH / (MATCH + NO_MATCH + UNSURE) with UNSURE counted as
  wrong, and the best case (MATCH + UNSURE) / (MATCH + NO_MATCH + UNSURE) with UNSURE counted as MATCH, each with a 95% Wilson
  interval. A band labeled in full is reported as counts, not as an estimate. REVIEW is reported as
  "x of n". Only AUTO and REVIEW are predicted matches, so only they have a precision; JUST_BELOW and LOW show the match rate
  (matches the matcher missed), which is not a precision.
  Out-of-time (phase OUTOFTIME): the same table and the same three numbers, with its own sizes, never pooled with held-out.
  Tuning (phase TUNING): counts only, diagnostic, no precision, never in a metric.
"""
from __future__ import annotations

import os
import sys
from decimal import ROUND_HALF_UP, Decimal

import psycopg

from pipeline.config import REPO_ROOT, load_config, load_env_file, require_frozen_matching
from pipeline.sample_labels import BANDS

LABELS = ("MATCH", "NO_MATCH", "UNSURE")
PREDICTED_MATCH = ("AUTO", "REVIEW")           # the bands the matcher calls a match


def wilson(k: int, n: int, z: Decimal) -> tuple[Decimal, Decimal, Decimal] | None:
    """(p, low, high) for k successes in n trials, SPEC 12.6 / phase_wise 6.7 formula. None when n is 0."""
    if n == 0:
        return None
    p = Decimal(k) / Decimal(n)
    nn, z2 = Decimal(n), z * z
    denom = 1 + z2 / nn
    center = (p + z2 / (2 * nn)) / denom
    half = z * (p * (1 - p) / nn + z2 / (4 * nn * nn)).sqrt() / denom
    return p, max(Decimal(0), center - half), min(Decimal(1), center + half)


def pct(x: Decimal) -> str:
    return f"{(x * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


def three_numbers(c: dict, z: Decimal) -> dict:
    """UNSURE excluded: MATCH over MATCH + NO_MATCH. Worst case: UNSURE counted as wrong, MATCH over all labeled.
    Best case: UNSURE counted as MATCH, MATCH + UNSURE over all labeled."""
    m, no, u = c["MATCH"], c["NO_MATCH"], c["UNSURE"]
    return {"excluded": {"k": m, "n": m + no, "ci": wilson(m, m + no, z)},
            "worst_case": {"k": m, "n": m + no + u, "ci": wilson(m, m + no + u, z)},
            "best_case": {"k": m + u, "n": m + no + u, "ci": wilson(m + u, m + no + u, z)}}


def phase_counts(conn, phase: str) -> dict[str, dict[str, int]]:
    """{band: {label: n}} from the labels of one phase, the band being the one stored with the sample at draw time."""
    out = {b: dict.fromkeys(LABELS, 0) for b in BANDS}
    for band, label, n in conn.execute(
            "SELECT s.score_band, l.label, count(*) FROM label_samples s JOIN labeled_pairs l ON l.sample_id = s.sample_id "
            "WHERE s.phase = %s GROUP BY 1, 2", (phase,)).fetchall():
        out[band][label] = n
    return out


def unlabeled(conn, phase: str) -> int:
    return conn.execute("SELECT count(*) FROM label_samples s LEFT JOIN labeled_pairs l ON l.sample_id = s.sample_id "
                        "WHERE s.phase = %s AND l.sample_id IS NULL", (phase,)).fetchone()[0]


def section(conn, phase: str, sizes_table: str, stored_hash: str, z: Decimal) -> dict:
    """One draw: per band frame, sampled and label counts, and the two precision numbers for the sampled bands."""
    sizes = {b: (frame, sample, h) for b, frame, sample, h in conn.execute(
        f"SELECT score_band, band_size, sample_size, matcher_config_hash FROM {sizes_table}").fetchall()}
    if not sizes:
        return {"drawn": False}
    if {h for *_, h in sizes.values()} != {stored_hash}:
        raise SystemExit(f"evaluate.py refuses: {sizes_table} holds a hash that differs from the freeze row.")
    left = unlabeled(conn, phase)
    if left:
        return {"drawn": True, "bands": None, "unlabeled": left}
    counts = phase_counts(conn, phase)
    bands = {}
    for b in BANDS:
        frame, sample, _ = sizes.get(b, (0, 0, None))
        c = counts[b]
        n = sum(c.values())
        if n != sample:
            raise SystemExit(f"evaluate.py refuses: {phase} band {b} has {n} labels but {sizes_table} says {sample} were drawn.")
        full = sample == frame and sample > 0
        entry = {"frame": frame, "sampled": sample, "full": full, "counts": c}
        if sample and not full:
            entry.update(three_numbers(c, z))
        bands[b] = entry
    return {"drawn": True, "bands": bands, "unlabeled": 0}


def build_report(conn, cfg: dict, root=REPO_ROOT) -> dict:
    stored = require_frozen_matching(conn, "evaluate.py", cfg, root)
    z = Decimal(str(cfg["evaluation"]["wilson_z"]))
    if conn.execute("SELECT count(*) FROM band_sizes").fetchone()[0] == 0:
        raise SystemExit("evaluate.py refuses: no held-out draw (band_sizes is empty).")
    left = unlabeled(conn, "HELDOUT")
    if left:
        raise SystemExit(f"evaluate.py refuses: {left} held-out samples are unlabeled.")
    held = section(conn, "HELDOUT", "band_sizes", stored, z)
    oot = section(conn, "OUTOFTIME", "outoftime_band_sizes", stored, z)
    tuning = dict.fromkeys(LABELS, 0)
    for label, n in conn.execute("SELECT l.label, count(*) FROM label_samples s JOIN labeled_pairs l ON l.sample_id = s.sample_id "
                                 "WHERE s.phase = 'TUNING' GROUP BY 1").fetchall():
        tuning[label] = n
    return {"hash": stored, "heldout": held, "outoftime": oot, "tuning": tuning}


def fmt_number(name: str, d: dict) -> str:
    if d["ci"] is None:
        return f"    {name}: {d['k']} of {d['n']}, not defined (n is 0)"
    p, lo, hi = d["ci"]
    return f"    {name}: {d['k']} of {d['n']} = {pct(p)}, 95% Wilson {pct(lo)} to {pct(hi)}"


def render_section(title: str, sec: dict, note: str) -> list[str]:
    lines = [title, f"  {note}"]
    if not sec["drawn"]:
        return lines + ["  not drawn"]
    if sec["bands"] is None:
        return lines + [f"  not reported: {sec['unlabeled']} samples are unlabeled"]
    lines.append(f"  {'band':<11}{'frame':>6}{'sampled':>9}{'MATCH':>7}{'NO_MATCH':>10}{'UNSURE':>8}")
    for b in BANDS:
        e = sec["bands"][b]
        c = e["counts"]
        lines.append(f"  {b:<11}{e['frame']:>6}{e['sampled']:>9}{c['MATCH']:>7}{c['NO_MATCH']:>10}{c['UNSURE']:>8}")
    for b in BANDS:
        e = sec["bands"][b]
        c, n = e["counts"], e["sampled"]
        what = "precision" if b in PREDICTED_MATCH else "match rate (matches the matcher missed, not a precision)"
        if e["sampled"] == 0:
            lines.append(f"  {b}: not sampled, frame {e['frame']}")
        elif e["full"]:
            lines.append(f"  {b}: labeled in full, {n} of {e['frame']}. Counts, not an estimate. MATCH {c['MATCH']} of {n}, "
                         f"NO_MATCH {c['NO_MATCH']}, UNSURE {c['UNSURE']}")
        else:
            head = f"  {b}: sampled {n} of {e['frame']}. {what}"
            if b == "REVIEW":
                head += f". MATCH {c['MATCH']} of {n}"
            lines += [head, fmt_number("UNSURE excluded", e["excluded"]), fmt_number("worst case, UNSURE counted as wrong", e["worst_case"]),
                      fmt_number("best case, UNSURE counted as MATCH", e["best_case"])]
    return lines


def render(rep: dict) -> str:
    out = [f"evaluate.py, matcher hash {rep['hash']} equals the freeze row and the stored draw hashes",
           "No result here changes or suggests a threshold, a rule or a config value.", ""]
    out += render_section("HELD-OUT (phase HELDOUT, measured period)", rep["heldout"],
                          "Frame is the measured-period candidate pairs minus the tuning pairs, banded by stored score.")
    out += [""] + render_section("OUT-OF-TIME (phase OUTOFTIME, prior quarter), reported separately, never pooled with held-out", rep["outoftime"],
                                 "A report-only check on a quarter the matcher was not built on. LOW was not sampled.")
    t = rep["tuning"]
    out += ["", "TUNING (diagnostic, counts only, no precision, not in any metric)",
            f"  labeled {sum(t.values())}: MATCH {t['MATCH']}, NO_MATCH {t['NO_MATCH']}, UNSURE {t['UNSURE']}"]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    cfg = load_config()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.read_only = True
        print(render(build_report(conn, cfg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
