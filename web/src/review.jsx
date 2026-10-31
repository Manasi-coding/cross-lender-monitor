import { useCallback, useEffect, useState } from "react";
import { ApiFailure, getJson, postJson } from "./api.js";
import { useShared } from "./App.jsx";
import { Card, EmptyState, Load, PageTitle, PeriodTag, SourceLink, StatCard, Toast, useFetch } from "./components.jsx";
import { bps, fixed, typeName } from "./format.js";
// 4.6 Review queue. The score is shown here (it is hidden only on the labeling page).
const key = (i) => (i.type === "pair" ? `p${i.holdingIdA}-${i.holdingIdB}` : `c${i.clusterId}`);
const FADE_MS = 320;
const PAGE_SIZE = 5;

export function ReviewPage() {
  const [version, setVersion] = useState(0);
  const f = useFetch(() => getJson("/api/review-queue"), [version]);
  const { refresh, overview } = useShared();
  const [skipped, setSkipped] = useState(new Set());
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [fading, setFading] = useState(new Set());
  const [toast, setToast] = useState(null);
  const [visible, setVisible] = useState(PAGE_SIZE);

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
      <PageTitle sub="Cases that need a human decision">Review queue</PageTitle>
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
          const page = shown.slice(0, visible);

          return (
            <>
              <div className="grid gap-5 sm:grid-cols-3">
                <StatCard label="Need review" value={shown.length} tone="review" />
                <StatCard label="Groups" value={clusterCount} tone="neutral" />
                <StatCard label="Pairs" value={pairCount} tone="brand" />
              </div>
              <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>Decisions apply after the next compare run.</p>

              <h2 className="mb-4 mt-6 text-lg font-semibold" style={{ color: "var(--color-text)" }}>Cases needing your decision</h2>

              {shown.length === 0 ? (
                <EmptyState>Nothing is waiting for review.</EmptyState>
              ) : (
                <>
                  <div className="space-y-4">
                    {page.map((i) =>
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
                  <div className="mt-5 text-center">
                    <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>Showing {page.length} of {shown.length} cases</p>
                    {visible < shown.length && (
                      <button className="btn-secondary mt-2" onClick={() => setVisible((v) => v + PAGE_SIZE)}>
                        View all &rarr;
                      </button>
                    )}
                  </div>
                </>
              )}
            </>
          );
        }}
      </Load>
      {toast && <Toast>{toast}</Toast>}
    </>
  );
}

// A small pill badge, reusing the app's green/amber tokens.
function Badge({ children, tone = "review" }) {
  const styles = tone === "brand" ? { color: "var(--color-brand-dark)", background: "var(--color-brand-light)" } : { color: "var(--color-review)", background: "var(--color-review-light)" };
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold" style={styles}>
      {children}
    </span>
  );
}

function SectionLabel({ tone = "review", children }) {
  const dot = tone === "brand" ? "var(--color-brand)" : "var(--color-review)";
  return (
    <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>
      <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: dot }} />
      {children}
    </p>
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

// E6's pair shape has no lender name (only clusters' holdings carry bdcName), so each side shows
// only what the API actually returns for a pair: the raw name, maturity, spread and filing link.
function RecordBox({ label, name, maturity, spread, sourceUrl }) {
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: "var(--color-border)" }}>
      <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>{label}</p>
      <p className="mt-1 text-sm font-medium" style={{ color: "var(--color-text)" }}>{name ?? "Name not disclosed"}</p>
      <p className="mt-2 text-xs" style={{ color: "var(--color-text-secondary)" }}>Maturity</p>
      <p className="text-sm" style={{ color: "var(--color-text)" }}>{maturity ?? "Not disclosed"}</p>
      <p className="mt-2 text-xs" style={{ color: "var(--color-text-secondary)" }}>Spread</p>
      <p className="text-sm" style={{ color: "var(--color-text)" }}>{bps(spread, "Not disclosed")}</p>
      <p className="mt-2"><SourceLink url={sourceUrl}>View filing</SourceLink></p>
    </div>
  );
}

function PairCard({ p, measured, busy, fading, onAct, onSkip }) {
  const pct = Math.round(Number(p.score) * 100);
  return (
    <Card className={fading ? "fade-out-card" : ""}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <SectionLabel tone="brand">Possible match<PeriodTag periodEnd={p.periodEnd} measured={measured} /></SectionLabel>
        <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>{typeName(p.instrumentType)}</span>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <RecordBox label="Record A" name={p.rawNameA} maturity={p.maturityDateA} spread={p.spreadBpsA} sourceUrl={p.sourceUrlA} />
        <RecordBox label="Record B" name={p.rawNameB} maturity={p.maturityDateB} spread={p.spreadBpsB} sourceUrl={p.sourceUrlB} />
      </div>
      <div className="mt-3">
        <ConfidenceBar pct={pct} />
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={onSkip}>Skip</button>
        <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onAct(p.holdingIdA, p.holdingIdB, "reject")}>Reject</button>
        <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onAct(p.holdingIdA, p.holdingIdB, "confirm")}>Accept</button>
      </div>
    </Card>
  );
}

function ClusterCard({ c, measured, busy, fading, onReject }) {
  const title = c.holdings[0]?.rawName ?? "Name not disclosed";
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <SectionLabel>Group needs review<PeriodTag periodEnd={c.periodEnd} measured={measured} /></SectionLabel>
        <Badge>{c.pairs.length} {c.pairs.length === 1 ? "pair" : "pairs"}</Badge>
      </div>
      <p className="mt-1 font-semibold uppercase" style={{ color: "var(--color-text)" }}>{title}</p>
      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>Several holdings have been grouped together.</p>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr style={{ color: "var(--color-text-secondary)" }}>
              <th className="py-1.5 pr-4 font-medium">Lender</th>
              <th className="py-1.5 pr-4 font-medium">Maturity</th>
              <th className="py-1.5 pr-4 font-medium">Spread</th>
              <th className="py-1.5 pr-2 font-medium">Source</th>
            </tr>
          </thead>
          <tbody>
            {c.holdings.map((h) => (
              <tr key={h.holdingId} className="border-t" style={{ borderColor: "var(--color-border)" }}>
                <td className="py-1.5 pr-4" style={{ color: "var(--color-text)" }}>{h.bdcName}</td>
                <td className="py-1.5 pr-4" style={{ color: "var(--color-text)" }}>{h.maturityDate ?? "Not disclosed"}</td>
                <td className="py-1.5 pr-4" style={{ color: "var(--color-text)" }}>{bps(h.spreadBps, "Not disclosed")}</td>
                <td className="py-1.5 pr-2"><SourceLink url={h.sourceUrl}>View filing</SourceLink></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-sm" style={{ color: "var(--color-text-secondary)" }}>
        <span className="font-semibold" style={{ color: "var(--color-text)" }}>Why review? </span>
        Multiple holdings from the same lender were grouped together.
      </p>

      <p className="mt-3 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Pairs that formed it</p>
      <ul className="mt-1 space-y-1.5 text-sm" style={{ color: "var(--color-text-secondary)" }}>
        {c.pairs.map((p) => (
          <li key={`${p.holdingIdA}-${p.holdingIdB}`} className={`flex flex-wrap items-center justify-between gap-2 ${fading.has(`pair-${p.holdingIdA}-${p.holdingIdB}`) ? "fade-out-card" : ""}`}>
            <span>Holdings {p.holdingIdA} and {p.holdingIdB}, score {fixed(p.score, 2)}, {p.status}</span>
            <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onReject(p.holdingIdA, p.holdingIdB)}>Reject</button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
