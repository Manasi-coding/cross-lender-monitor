"""evaluate.py: the label-derived evaluation (SPEC section 12.6, phase_wise.md 6.7), report only.

Run: python -m pipeline.evaluate
It refuses unless a freeze row exists and the current matcher hash equals it and the hash stored in band_sizes (and in
outoftime_band_sizes when that draw exists), or if any held-out sample is unlabeled. It reads label_samples, labeled_pairs,
band_sizes, outoftime_band_sizes and blocking_recall_checks only. It never reads candidate_pairs, so review-queue clicks cannot reach a number, and it
writes only metric_results (one row per run, none with --dry-run). No result changes or suggests a threshold, a rule or a config value.

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
import random
import sys
from decimal import ROUND_HALF_UP, Decimal

import psycopg
from psycopg.types.json import Jsonb

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


# ------------------------------------------------------------------ the E9 payload (metric_results)
def q6(x: Decimal) -> float:
    return float(x.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def ci(k: int, n: int, z: Decimal) -> dict | None:
    """E9 Ci from a Wilson interval, None when n is 0."""
    w = wilson(k, n, z)
    return None if w is None else {"value": q6(w[0]), "low": q6(w[1]), "high": q6(w[2]), "n": n}


def range3(c: dict, z: Decimal) -> dict:
    """E9 Range. unsureAsNoMatch is the worst case, unsureAsMatch the best case, unsureExcluded the headline (null when no decided pair)."""
    m, no, u = c["MATCH"], c["NO_MATCH"], c["UNSURE"]
    return {"unsureAsNoMatch": ci(m, m + no + u, z), "unsureAsMatch": ci(m + u, m + no + u, z), "unsureExcluded": ci(m, m + no, z)}


def m_share(c: dict, mode: str) -> Decimal | None:
    m, no, u = c["MATCH"], c["NO_MATCH"], c["UNSURE"]
    num, den = {"worst": (m, m + no + u), "best": (m + u, m + no + u), "excluded": (m, m + no)}[mode]
    return Decimal(num) / Decimal(den) if den else None


def weighted(counts: dict, frames: dict, mode: str, S: tuple, kind: str) -> Decimal | None:
    """SPEC 12.6: precision = sum(m_b N_b, b in S) / sum(N_b, b in S); recall = sum(m_b N_b, b in S) / sum(m_b N_b, all bands).
    A band with no decided pair in this mode has no share, so it contributes 0 (a stated convention)."""
    def mn(b):
        s = m_share(counts[b], mode)
        return (s if s is not None else Decimal(0)) * frames[b]
    top = sum((mn(b) for b in S), Decimal(0))
    den = sum((frames[b] for b in S), Decimal(0)) if kind == "precision" else sum((mn(b) for b in BANDS), Decimal(0))
    return top / den if den else None


WEIGHTED = {"precisionIfReviewAutoAccepted": (("AUTO", "REVIEW"), "precision"), "recallAutoOnly": (("AUTO",), "recall"),
            "recallIfReviewAutoAccepted": (("AUTO", "REVIEW"), "recall")}
MODES = {"unsureAsNoMatch": "worst", "unsureAsMatch": "best", "unsureExcluded": "excluded"}


def weighted_ranges(held: dict, cfg: dict) -> dict:
    """Band-weighted figures with a bootstrap over bands: each sampled band's labeled pairs are resampled with replacement;
    a band labeled in full is a census and is not resampled. Fixed seed from evaluation.bootstrap_seed."""
    b = held["bands"]
    counts = {k: b[k]["counts"] for k in BANDS}
    frames = {k: Decimal(b[k]["frame"]) for k in BANDS}
    if any(b[k]["sampled"] == 0 and b[k]["frame"] > 0 for k in BANDS):
        return {k: None for k in WEIGHTED}                                    # a band with no sample: recall cannot be weighted
    resamples, seed = int(cfg["evaluation"]["bootstrap_resamples"]), cfg["evaluation"]["bootstrap_seed"]
    rng = random.Random(f"{seed}:weighted")
    labels = {k: ["MATCH"] * counts[k]["MATCH"] + ["NO_MATCH"] * counts[k]["NO_MATCH"] + ["UNSURE"] * counts[k]["UNSURE"]
              for k in BANDS if not b[k]["full"] and b[k]["sampled"]}
    draws = {name: {mode: [] for mode in MODES} for name in WEIGHTED}
    for _ in range(resamples):
        c = dict(counts)
        for k, lab in labels.items():
            r = rng.choices(lab, k=len(lab))
            c[k] = {x: r.count(x) for x in LABELS}
        for name, (S, kind) in WEIGHTED.items():
            for key, mode in MODES.items():
                v = weighted(c, frames, mode, S, kind)
                if v is not None:
                    draws[name][key].append(v)
    out = {}
    for name, (S, kind) in WEIGHTED.items():
        n = sum(b[k]["sampled"] for k in (S if kind == "precision" else BANDS))
        entry = {}
        for key, mode in MODES.items():
            v, d = weighted(counts, frames, mode, S, kind), sorted(draws[name][key])
            if v is None or not d:
                entry[key] = None
                continue
            lo, hi = d[round(0.025 * (len(d) - 1))], d[round(0.975 * (len(d) - 1))]
            entry[key] = {"value": q6(v), "low": q6(min(lo, v)), "high": q6(max(hi, v)), "n": n}
        out[name] = entry
    return out


def band_entries(sec: dict, z: Decimal) -> list[dict]:
    out = []
    for name in BANDS:
        e = sec["bands"][name]
        c = e["counts"]
        out.append({"name": name, "bandSize": e["frame"], "sampleSize": e["sampled"], "labeledInFull": e["full"],
                    "counts": {"match": c["MATCH"], "noMatch": c["NO_MATCH"], "unsure": c["UNSURE"]},
                    "matchRate": range3(c, z) if e["sampled"] and not e["full"] else None})
    return out


def blocking_recall_ci(conn, z: Decimal) -> dict | None:
    n, k = conn.execute("SELECT count(*), count(*) FILTER (WHERE found_by_blocking) FROM blocking_recall_checks").fetchone()
    return ci(k, n, z)


def build_payload(conn, cfg: dict, rep: dict) -> dict:
    """The label-derived E9 fields, HELDOUT only. The out-of-time report is stored apart in outOfTime and is never pooled."""
    z = Decimal(str(cfg["evaluation"]["wilson_z"]))
    held, bands = rep["heldout"], rep["heldout"]["bands"]
    auto, review = bands["AUTO"], bands["REVIEW"]
    heldout_count = sum(sum(e["counts"].values()) for e in bands.values())
    drawn = conn.execute("SELECT count(*) FROM label_samples WHERE phase = 'HELDOUT'").fetchone()[0]
    if heldout_count != drawn:
        raise SystemExit(f"evaluate.py refuses: {heldout_count} held-out labels counted but {drawn} samples were drawn.")
    payload = {
        "precisionAutoOnly": range3(auto["counts"], z) if auto["sampled"] and not auto["full"] else None,
        "precisionReviewBand": range3(review["counts"], z) if review["sampled"] and not review["full"] else None,
        **weighted_ranges(held, cfg),
        "blockingRecall": blocking_recall_ci(conn, z),
        "bands": band_entries(held, z),
        "unsureCount": sum(e["counts"]["UNSURE"] for e in bands.values()),
        "heldOutCount": heldout_count,
        "outOfTime": None,
        "matcherConfigHash": rep["hash"],
    }
    oot = rep["outoftime"]
    if oot["drawn"] and oot["bands"] is not None:
        ob = oot["bands"]
        payload["outOfTime"] = {"periodEnd": cfg["sampling"]["outoftime_period"],
                                "precisionAutoOnly": range3(ob["AUTO"]["counts"], z) if ob["AUTO"]["sampled"] and not ob["AUTO"]["full"] else None,
                                "bands": band_entries(oot, z),
                                "unsureCount": sum(e["counts"]["UNSURE"] for e in ob.values()),
                                "labeledCount": sum(sum(e["counts"].values()) for e in ob.values())}
    return payload


def write_metric_results(conn, cfg: dict, root=REPO_ROOT) -> dict:
    """Refuse unless frozen and matching, then append one metric_results row (the newest row is what E9 serves)."""
    rep = build_report(conn, cfg, root)
    payload = build_payload(conn, cfg, rep)
    conn.execute("INSERT INTO metric_results (matcher_config_hash, payload) VALUES (%s, %s)", (rep["hash"], Jsonb(payload)))
    return payload


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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the report and write nothing")
    args = ap.parse_args(argv)
    load_env_file()
    cfg = load_config()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        print(render(build_report(conn, cfg)))
        if args.dry_run:
            return 0
        write_metric_results(conn, cfg)
        print("\nmetric_results: one row written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
