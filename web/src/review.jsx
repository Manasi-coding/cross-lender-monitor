import { useCallback, useEffect, useState } from "react";
import { ApiFailure, getJson, postJson } from "./api.js";
import { useShared } from "./App.jsx";
import { Card, CardLabel, EmptyState, Load, PageTitle, PeriodTag, SourceLink, StatCard, Toast, useFetch } from "./components.jsx";
import { bps, fixed, typeName } from "./format.js";
// 4.6 Review queue. The score is shown here (it is hidden only on the labeling page).
const key = (i) => (i.type === "pair" ? `p${i.holdingIdA}-${i.holdingIdB}` : `c${i.clusterId}`);
const FADE_MS = 320;

export function ReviewPage() {
  const [version, setVersion] = useState(0);
  const f = useFetch(() => getJson("/api/review-queue"), [version]);
  const { refresh, overview } = useShared();
  const [skipped, setSkipped] = useState(new Set());
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [fading, setFading] = useState(new Set());
  const [toast, setToast] = useState(null);

  useEffect(() => setSkipped(new Set()), [version]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  // The card (or, for a cluster pair, its row) is only faded and the list only refetched after the
  // write has actually succeeded, never before. A failure leaves the card exactly as it was and
  // shows the error instead.
  const act = useCallback(
    async (a, b, action, fadeKey) => {
      if (busy) return;
      setBusy(true);
      try {
        await postJson(`/api/review-queue/${a}/${b}/${action}`);
        setNotice(null);
        setFading((prev) => new Set(prev).add(fadeKey));
        await new Promise((resolve) => setTimeout(resolve, FADE_MS));
        setVersion((v) => v + 1);
        refresh();
        setToast("Decision saved");
      } catch (e) {
        if (e instanceof ApiFailure && e.status === 409) setNotice("This pair was already decided.");
        else if (e instanceof ApiFailure && e.status === 404) setNotice("This pair is not in the review queue any more.");
        else setNotice(e.message);
      } finally {
        setBusy(false);
      }
    },
    [busy, refresh],
  );

  return (
    <>
      <PageTitle sub="Decisions apply after the next compare run.">Review queue</PageTitle>
      {notice && (
        <p role="alert" className="mb-4 rounded-2xl border p-3 text-sm" style={{ borderColor: "var(--color-flagged)", background: "var(--color-flagged-light)", color: "var(--color-flagged)" }}>
          {notice}
        </p>
      )}
      <Load f={f}>
        {(items) => {
          const shown = items.filter((i) => !skipped.has(key(i)));
          const clusterCount = shown.filter((i) => i.type === "cluster").length;
          const pairCount = shown.filter((i) => i.type === "pair").length;

          return (
            <>
              <div className="grid gap-5 sm:grid-cols-2">
                <StatCard label="Waiting" value={shown.length} note={`${clusterCount} ${clusterCount === 1 ? "cluster" : "clusters"}, ${pairCount} ${pairCount === 1 ? "pair" : "pairs"}`} tone="review" />
                <Card>
                  <CardLabel>What does review mean?</CardLabel>
                  <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>
                    The system found a possible match or grouping that needs a human decision.
                  </p>
                </Card>
              </div>

              <h2 className="mb-4 mt-6 text-lg font-semibold" style={{ color: "var(--color-text)" }}>Cases requiring a decision</h2>

              {shown.length === 0 ? (
                <EmptyState>Nothing is waiting for review.</EmptyState>
              ) : (
                <div className="space-y-4">
                  {shown.map((i) =>
                    i.type === "cluster" ? (
                      <ClusterCard key={key(i)} c={i} measured={overview?.measuredPeriodEnd} busy={busy} fading={fading} onReject={(a, b) => act(a, b, "reject", `pair-${a}-${b}`)} />
                    ) : (
                      <PairCard
                        key={key(i)}
                        p={i}
                        measured={overview?.measuredPeriodEnd}
                        busy={busy}
                        fading={fading.has(key(i))}
                        onAct={(a, b, action) => act(a, b, action, key(i))}
                        onSkip={() => setSkipped(new Set(skipped).add(key(i)))}
                      />
                    ),
                  )}
                </div>
              )}
            </>
          );
        }}
      </Load>
      {toast && <Toast>{toast}</Toast>}
    </>
  );
}

// A small pill badge, reusing the app's green/amber/red tokens: green for an actual match
// confidence, amber for a cluster still needing a human look.
function Badge({ children, tone = "review" }) {
  const styles = tone === "brand" ? { color: "var(--color-brand-dark)", background: "var(--color-brand-light)" } : { color: "var(--color-review)", background: "var(--color-review-light)" };
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold" style={styles}>
      {children}
    </span>
  );
}

function ConfidenceBar({ pct }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs" style={{ color: "var(--color-text-secondary)" }}>
        <span>Match confidence</span>
        <span className="font-semibold" style={{ color: "var(--color-text)" }}>{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full" style={{ background: "var(--color-border)" }}>
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: "var(--color-brand)" }} />
      </div>
    </div>
  );
}

function PairCard({ p, measured, busy, fading, onAct, onSkip }) {
  const pct = Math.round(Number(p.score) * 100);
  return (
    <Card className={fading ? "fade-out-card" : ""}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>Possible match</p>
        <Badge tone="brand">{pct}% match</Badge>
      </div>
      <p className="mt-1 font-semibold uppercase" style={{ color: "var(--color-text)" }}>
        {p.rawNameA ?? "Name not disclosed"} and {p.rawNameB ?? "Name not disclosed"}<PeriodTag periodEnd={p.periodEnd} measured={measured} />
      </p>
      <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>{typeName(p.instrumentType)}</p>
      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>Maturity {p.maturityDateA ?? "Not disclosed"} and {p.maturityDateB ?? "Not disclosed"}. Spread {bps(p.spreadBpsA, "Not disclosed")} and {bps(p.spreadBpsB, "Not disclosed")}.</p>
      <p className="mt-1 text-sm"><SourceLink url={p.sourceUrlA}>Source A</SourceLink> <SourceLink url={p.sourceUrlB}>Source B</SourceLink></p>
      <div className="mt-3">
        <ConfidenceBar pct={pct} />
      </div>
      <div className="mt-3 flex gap-2">
        <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onAct(p.holdingIdA, p.holdingIdB, "confirm")}>Accept</button>
        <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onAct(p.holdingIdA, p.holdingIdB, "reject")}>Reject</button>
        <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={onSkip}>Skip</button>
      </div>
    </Card>
  );
}

function ClusterCard({ c, measured, busy, fading, onReject }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>
          Cluster needs review<PeriodTag periodEnd={c.periodEnd} measured={measured} />
        </p>
        <Badge>{c.pairs.length} {c.pairs.length === 1 ? "pair" : "pairs"}</Badge>
      </div>
      <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>Two holdings from the same lender landed in one cluster.</p>
      <ul className="my-2 space-y-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>
        {c.holdings.map((h) => (
          <li key={h.holdingId}>{h.rawName ?? "Name not disclosed"}, {h.bdcName}, maturity {h.maturityDate ?? "Not disclosed"}, spread {bps(h.spreadBps, "Not disclosed")} <SourceLink url={h.sourceUrl} /></li>
        ))}
      </ul>
      <p className="font-semibold" style={{ color: "var(--color-text)" }}>Pairs that formed it:</p>
      <ul className="space-y-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>
        {c.pairs.map((p) => (
          <li key={`${p.holdingIdA}-${p.holdingIdB}`} className={`flex flex-wrap items-center gap-2 ${fading.has(`pair-${p.holdingIdA}-${p.holdingIdB}`) ? "fade-out-card" : ""}`}>
            Holdings {p.holdingIdA} and {p.holdingIdB}, score {fixed(p.score, 2)}, {p.status}
            <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onReject(p.holdingIdA, p.holdingIdB)}>Reject</button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
