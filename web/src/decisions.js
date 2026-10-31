// A local, browser-stored record of review decisions this interface has sent. CONTRACT.md's E7
// and E8 only return { holdingIdA, holdingIdB, status } and write candidate_pairs.status; there is
// no endpoint that lists past decisions, so this is not a server audit trail. It is a convenience
// log of what this browser actually did, built only from successful API responses, never invented.
const KEY = "review-decisions-v1";
const MAX_ENTRIES = 500;

function read() {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function getDecisions() {
  return read();
}

// entry: { holdingIdA, holdingIdB, status, title, context } where status is exactly what E7/E8
// returned ("CONFIRMED" | "REJECTED") and context is "pair" (a possible-match case) or "cluster"
// (a pair rejected from within a group-issue case).
export function recordDecision(entry) {
  const list = read();
  list.unshift({ ...entry, at: new Date().toISOString() });
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX_ENTRIES)));
  } catch {
    // storage can be blocked or full; the decision still happened server side, only the local log is lost
  }
}

export function clearDecisions() {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
