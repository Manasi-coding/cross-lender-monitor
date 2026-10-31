import { useCallback, useEffect, useState } from "react";
import { ApiFailure, getJson, postJson } from "./api.js";
import { useShared } from "./App.jsx";
import { Card, EmptyState, Load, PageTitle, PeriodTag, SourceLink, Toast, useFetch } from "./components.jsx";
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
          return (
            <>
              <p className="mb-4 font-semibold" style={{ color: "var(--color-text)" }}>{shown.length} pending</p>
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

function PairCard({ p, measured, busy, fading, onAct, onSkip }) {
  return (
    <Card className={fading ? "fade-out-card" : ""}>
      <p className="font-bold uppercase" style={{ color: "var(--color-text)" }}>{p.rawNameA ?? "Name not disclosed"} and {p.rawNameB ?? "Name not disclosed"}<PeriodTag periodEnd={p.periodEnd} measured={measured} /></p>
      <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>Score {fixed(p.score, 2)}. {typeName(p.instrumentType)}.</p>
      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>Maturity {p.maturityDateA ?? "Not disclosed"} and {p.maturityDateB ?? "Not disclosed"}. Spread {bps(p.spreadBpsA, "Not disclosed")} and {bps(p.spreadBpsB, "Not disclosed")}.</p>
      <p className="text-sm"><SourceLink url={p.sourceUrlA}>Source A</SourceLink> <SourceLink url={p.sourceUrlB}>Source B</SourceLink></p>
      <div className="mt-3 flex gap-2">
        <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onAct(p.holdingIdA, p.holdingIdB, "confirm")}>Confirm</button>
        <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onAct(p.holdingIdA, p.holdingIdB, "reject")}>Reject</button>
        <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={onSkip}>Skip</button>
      </div>
    </Card>
  );
}

function ClusterCard({ c, measured, busy, fading, onReject }) {
  return (
    <Card>
      <p className="font-bold" style={{ color: "var(--color-text)" }}>CLUSTER NEEDS REVIEW<PeriodTag periodEnd={c.periodEnd} measured={measured} /></p>
      <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>Two holdings from the same BDC landed in one cluster.</p>
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
