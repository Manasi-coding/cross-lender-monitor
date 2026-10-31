// A local, in-memory record of review decisions this interface has sent, for this page load only:
// it starts empty on every refresh and is not written to disk (localStorage, sessionStorage or
// otherwise), by request. CONTRACT.md's E7 and E8 only return { holdingIdA, holdingIdB, status }
// and write candidate_pairs.status; there is no endpoint that lists past decisions, so this was
// never a server audit trail. It is a convenience log of what this browser did since the last
// reload, built only from successful API responses, never invented.
const MAX_ENTRIES = 500;
let decisions = [];

export function getDecisions() {
  return decisions;
}

// entry: { holdingIdA, holdingIdB, status, title, context } where status is exactly what E7/E8
// returned ("CONFIRMED" | "REJECTED"), or "ACKNOWLEDGED" for a group-issue record left as is
// (no server call made), and context is "pair" or "cluster".
export function recordDecision(entry) {
  decisions = [{ ...entry, at: new Date().toISOString() }, ...decisions].slice(0, MAX_ENTRIES);
}

export function clearDecisions() {
  decisions = [];
}
