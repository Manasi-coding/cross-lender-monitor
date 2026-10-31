// Display helpers. NUMERIC values arrive as strings and are rounded here, at the edge. A null never becomes a number or a blank.
export const NOT_YET = "Not yet measured";
export const NOT_DISCLOSED = "Not disclosed";

function group(intPart) {
  return intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Round a decimal string to dp places by string arithmetic on a scaled integer, so 98.125 and large values stay exact enough for display.
export function fixed(v, dp) {
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  const s = Math.abs(n).toFixed(dp);
  const [i, f] = s.split(".");
  return (n < 0 && Number(s) !== 0 ? "-" : "") + group(i) + (f ? "." + f : "");
}

export const points = (v, empty = NOT_YET) => (v === null ? empty : fixed(v, 2));
export const bps = (v, empty = NOT_YET) => (v === null ? empty : fixed(v, 0) + " bps");
export const usd = (v, empty = NOT_YET) => (v === null ? empty : "USD " + fixed(v, 0));
export const pctPar = (v, empty = NOT_YET) => (v === null ? empty : fixed(v, 2));

// A proportion in [0, 1] shown as a percent with one decimal.
export function pct(x) {
  return x === null || x === undefined ? NOT_YET : (x * 100).toFixed(1) + "%";
}

const TYPE_NAMES= { FIRST_LIEN: "First lien", SECOND_LIEN: "Second lien", UNITRANCHE: "Unitranche", MEZZANINE: "Mezzanine" };
export function typeName(t) {
  return TYPE_NAMES[t] ?? t.charAt(0) + t.slice(1).toLowerCase().replace(/_/g, " ");
}

export function spreadRange(min, max) {
  if (min === null || max === null) return NOT_YET;
  return min === max || fixed(min, 0) === fixed(max, 0) ? fixed(min, 0) + " bps" : `${fixed(min, 0)} to ${fixed(max, 0)} bps`;
}

export const FLAG_TEXT= { AGREEMENT: "Agreement", MILD: "Mild", FLAGGED: "Flagged" };
export const PERSISTENCE_TEXT= { WIDENED: "Widened", NARROWED: "Narrowed", CLOSED: "Closed", STABLE: "Stable", NO_PRIOR: "No prior" };
export const SIGNAL_TEXT= {
  NON_ACCRUAL: "Non accrual",
  PIK_DIFFERS: "PIK differs",
  FLOOR_DIFFERS: "Floor differs",
  SPREAD_DIFFERS: "Spread differs",
  MATURITY_DIFFERS: "Maturity differs",
  COST_BASIS_GAP: "Cost basis gap",
  RATE_TYPE_DIFFERS: "Rate type differs",
};
