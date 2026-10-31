"""evidence.py: the F2 dossier arithmetic and the signal codes (SPEC 12.10, DECISIONS section 26). Pure functions, no database.

compare.py calls these inside its rebuild transaction. Not a matcher file and not in freeze.hashed_files. Wording is always
"signals present": a signal says a difference is disclosed in the filings, never that it explains or causes a gap.
A field that is None on a holding is not disclosed; it is never filled in and is skipped by every signal.
"""
from __future__ import annotations

from decimal import Decimal

SIGNAL_ORDER = ("NON_ACCRUAL", "PIK_DIFFERS", "FLOOR_DIFFERS", "SPREAD_DIFFERS", "MATURITY_DIFFERS", "COST_BASIS_GAP", "RATE_TYPE_DIFFERS")


def cost_pct_par(cost: Decimal | None, principal: Decimal | None, fair_value_pct_par: Decimal | None) -> Decimal | None:
    """cost / principal * 100, only when the holding has a mark (so principal is nonzero) and a cost."""
    if cost is None or principal is None or principal == 0 or fair_value_pct_par is None:
        return None
    return cost / principal * Decimal(100)


def fv_pct_cost(fair_value: Decimal | None, cost: Decimal | None) -> Decimal | None:
    """fair value / cost * 100, only when cost is non-null and nonzero."""
    if fair_value is None or cost is None or cost == 0:
        return None
    return fair_value / cost * Decimal(100)


def _spread(values: list) -> Decimal | None:
    vals = [v for v in values if v is not None]
    return max(vals) - min(vals) if len(vals) >= 2 else None


def signals(holdings: list[dict], cfg: dict, floor_ciks: set[str]) -> list[str]:
    """holdings: the included holdings of one facility, dicts with non_accrual, pik_bps, floor_bps, bdc_cik, spread_bps, maturity_date,
    cost_pct_par, reference_rate. Returns the codes that fire, in SIGNAL_ORDER."""
    ev = cfg["evidence"]
    out = []
    if any(h.get("non_accrual") for h in holdings):
        out.append("NON_ACCRUAL")
    pik = _spread([h.get("pik_bps") for h in holdings])
    if pik is not None and pik > Decimal(str(ev["pik_differs_min_bps"])):
        out.append("PIK_DIFFERS")
    floor = _spread([h.get("floor_bps") for h in holdings if h["bdc_cik"] in floor_ciks])
    if floor is not None and floor >= Decimal(str(ev["floor_differs_bps"])):
        out.append("FLOOR_DIFFERS")
    spread = _spread([h.get("spread_bps") for h in holdings])
    if spread is not None and spread >= Decimal(str(ev["spread_differs_bps"])):
        out.append("SPREAD_DIFFERS")
    dates = [h["maturity_date"] for h in holdings if h.get("maturity_date") is not None]
    if len(dates) >= 2 and (max(dates) - min(dates)).days >= int(ev["maturity_differs_days"]):
        out.append("MATURITY_DIFFERS")
    cost = _spread([h.get("cost_pct_par") for h in holdings])
    if cost is not None and cost >= Decimal(str(cfg["divergence"]["mild_pts"])):
        out.append("COST_BASIS_GAP")
    rates = [h.get("reference_rate") for h in holdings if h.get("reference_rate") is not None]
    if "FIXED" in rates and any(r != "FIXED" for r in rates):
        out.append("RATE_TYPE_DIFFERS")
    return out


def floor_ciks(cfg: dict) -> set[str]:
    """CIKs of the filers whose floor is disclosed (evidence.floor_filers)."""
    return {cfg["filers"][k]["cik"] for k in cfg["evidence"]["floor_filers"]}
