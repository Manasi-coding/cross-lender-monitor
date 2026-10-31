import { useCallback, useEffect, useState } from "react";
import { ApiFailure, getJson, postJson } from "./api.js";
import { useShared } from "./App.jsx";
import { Card, EmptyState, Load, PageTitle, PeriodTag, SourceLink, useFetch } from "./components.jsx";
import { bps, fixed, typeName } from "./format.js";
// 4.6 Review queue. The score is shown here (it is hidden only on the labeling page).
const key = (i) => (i.type === "pair" ? `p${i.holdingIdA}-${i.holdingIdB}` : `c${i.clusterId}`);

export function ReviewPage() {
  const [version, setVersion] = useState(0);
  const f = useFetch(() => getJson("/api/review-queue"), [version]);
  const { refresh, overview } = useShared();
  const [skipped, setSkipped] = useState(new Set());
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => setSkipped(new Set()), [version]);

  const act = useCallback(
    async (a, b, action) => {
      if (busy) return;
      setBusy(true);
      try {
        await postJson(`/api/review-queue/${a}/${b}/${action}`);
        setNotice(null);
      } catch (e) {
        if (e instanceof ApiFailure && e.status === 409) setNotice("This pair was already decided.");
        else if (e instanceof ApiFailure && e.status === 404) setNotice("This pair is not in the review queue any more.");
        else setNotice((e).message);
      } finally {
        setBusy(false);
        setVersion((v) => v + 1);
        refresh();
      }
    },
    [busy, refresh],
  );

  return (
    <>
      <PageTitle sub="Decisions apply after the next compare run.">Review queue</PageTitle>
      {notice && <p role="alert" className="mb-4 rounded border border-red-600 p-2">{notice}</p>}
      <Load f={f}>
        {(items) => {
          const shown = items.filter((i) => !skipped.has(key(i)));
          return (
            <>
              <p className="mb-4 font-semibold">{shown.length} pending</p>
              {shown.length === 0 ? (
                <EmptyState>Nothing is waiting for review.</EmptyState>
              ) : (
                <div className="space-y-4">
                  {shown.map((i) =>
                    i.type === "cluster" ? (
                      <ClusterCard key={key(i)} c={i} measured={overview?.measuredPeriodEnd} busy={busy} onReject={(a, b) => act(a, b, "reject")} />
                    ) : (
                      <PairCard key={key(i)} p={i} measured={overview?.measuredPeriodEnd} busy={busy} onAct={act} onSkip={() => setSkipped(new Set(skipped).add(key(i)))} />
                    ),
                  )}
                </div>
              )}
            </>
          );
        }}
      </Load>
    </>
  );
}

function PairCard({ p, measured, busy, onAct, onSkip }) {
  return (
    <Card>
      <p className="font-bold uppercase">{p.rawNameA ?? "Name not disclosed"} and {p.rawNameB ?? "Name not disclosed"}<PeriodTag periodEnd={p.periodEnd} measured={measured} /></p>
      <p>Score {fixed(p.score, 2)}. {typeName(p.instrumentType)}.</p>
      <p>Maturity {p.maturityDateA ?? "Not disclosed"} and {p.maturityDateB ?? "Not disclosed"}. Spread {bps(p.spreadBpsA, "Not disclosed")} and {bps(p.spreadBpsB, "Not disclosed")}.</p>
      <p><SourceLink url={p.sourceUrlA}>Source A</SourceLink> <SourceLink url={p.sourceUrlB}>Source B</SourceLink></p>
      <div className="mt-2 flex gap-2">
        <button disabled={busy} className="rounded border px-3 py-1" onClick={() => onAct(p.holdingIdA, p.holdingIdB, "confirm")}>Confirm</button>
        <button disabled={busy} className="rounded border px-3 py-1" onClick={() => onAct(p.holdingIdA, p.holdingIdB, "reject")}>Reject</button>
        <button disabled={busy} className="rounded border px-3 py-1" onClick={onSkip}>Skip</button>
      </div>
    </Card>
  );
}

function ClusterCard({ c, measured, busy, onReject }) {
  return (
    <Card>
      <p className="font-bold">CLUSTER NEEDS REVIEW<PeriodTag periodEnd={c.periodEnd} measured={measured} /></p>
      <p>Two holdings from the same BDC landed in one cluster.</p>
      <ul className="my-2 space-y-1">
        {c.holdings.map((h) => (
          <li key={h.holdingId}>{h.rawName ?? "Name not disclosed"}, {h.bdcName}, maturity {h.maturityDate ?? "Not disclosed"}, spread {bps(h.spreadBps, "Not disclosed")} <SourceLink url={h.sourceUrl} /></li>
        ))}
      </ul>
      <p className="font-semibold">Pairs that formed it:</p>
      <ul className="space-y-1">
        {c.pairs.map((p) => (
          <li key={`${p.holdingIdA}-${p.holdingIdB}`} className="flex flex-wrap items-center gap-2">
            Holdings {p.holdingIdA} and {p.holdingIdB}, score {fixed(p.score, 2)}, {p.status}
            <button disabled={busy} className="rounded border px-3 py-1" onClick={() => onReject(p.holdingIdA, p.holdingIdB)}>Reject</button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
