import { useCallback, useEffect, useState } from "react";
import { ApiFailure, getJson, postJson } from "./api.js";
import { useShared } from "./App.jsx";
import { BarList, Card, CardLabel, EmptyState, Load, PageTitle, PeriodTag, SourceLink, StatCard, Toast, useFetch } from "./components.jsx";
import { bps, fixed, typeName } from "./format.js";
// 4.6 Review queue. The score is shown here (it is hidden only on the labeling page), and only
// inside each case's "Technical details" toggle on this page's default plain-language view.
const key = (i) => (i.type === "pair" ? `p${i.holdingIdA}-${i.holdingIdB}` : `c${i.clusterId}`);
const FADE_MS = 320;

export function ReviewPage() {
  const [version, setVersion] = useState(0);
  const f = useFetch(() => getJson("/api/review-queue"), [version]);
  const { refresh, overview } = useShared();
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [fading, setFading] = useState(new Set());
  const [toast, setToast] = useState(null);
  const [current, setCurrent] = useState(0);
  // A running count of decisions made this browser session (resets on reload); the API has no
  // "completed" concept of its own, since a decided pair simply drops out of the REVIEW queue.
  const [completed, setCompleted] = useState(0);

  useEffect(() => setCurrent(0), [version]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  // The card is only faded and the list only refetched after the write has actually succeeded,
  // never before. A failure leaves the card exactly as it was and shows the error instead.
  const act = useCallback(
    async (a, b, action, fadeKey) => {
      if (busy) return;
      setBusy(true);
      try {
        await postJson(`/api/review-queue/${a}/${b}/${action}`);
        setNotice(null);
        setFading((prev) => new Set(prev).add(fadeKey));
        await new Promise((resolve) => setTimeout(resolve, FADE_MS));
        setCompleted((n) => n + 1);
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
      <PageTitle sub="A short list of cases that need your decision">Review queue</PageTitle>
      {notice && (
        <p role="alert" className="mb-4 rounded-2xl border p-3 text-sm" style={{ borderColor: "var(--color-flagged)", background: "var(--color-flagged-light)", color: "var(--color-flagged)" }}>
          {notice}
        </p>
      )}
      <Load f={f}>
        {(items) => {
          const matches = items.filter((i) => i.type === "pair");
          const groups = items.filter((i) => i.type === "cluster");
          const idx = Math.min(current, Math.max(0, items.length - 1));
          const primary = items[idx];
          const secondary = items[idx + 1];
          const majority = matches.length >= groups.length ? "Most cases are possible borrower matches." : "Most cases are from grouped records.";

          return (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatCard compact label="Need review" value={items.length} tone="review" />
                <StatCard compact label="Possible match" value={matches.length} tone="brand" />
                <StatCard compact label="Group issues" value={groups.length} tone="flagged" />
                <StatCard compact label="Completed" value={completed} tone="neutral" />
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <Card compact>
                  <CardLabel>Review status</CardLabel>
                  <BarList
                    compact
                    rows={[
                      { label: "Possible match", value: matches.length, color: "var(--color-brand)" },
                      { label: "Group issue", value: groups.length, color: "var(--color-flagged)" },
                    ]}
                  />
                </Card>
                <Card compact>
                  <CardLabel>What needs attention</CardLabel>
                  <div className="space-y-1.5 text-sm">
                    <p className="flex items-center gap-2" style={{ color: "var(--color-text)" }}>
                      <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: "var(--color-brand)" }} />
                      Possible match <span className="ml-auto font-semibold">{matches.length}</span>
                    </p>
                    <p className="flex items-center gap-2" style={{ color: "var(--color-text)" }}>
                      <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: "var(--color-flagged)" }} />
                      Group issue <span className="ml-auto font-semibold">{groups.length}</span>
                    </p>
                  </div>
                  {items.length > 0 && <p className="mt-2 text-xs" style={{ color: "var(--color-text-secondary)" }}>{majority}</p>}
                </Card>
              </div>

              <h2 className="mb-3 mt-5 text-lg font-semibold" style={{ color: "var(--color-text)" }}>Cases to review</h2>

              {items.length === 0 ? (
                <EmptyState>Nothing is waiting for review.</EmptyState>
              ) : (
                <>
                  <div className="space-y-3">
                    {primary.type === "cluster" ? (
                      <ClusterCard c={primary} measured={overview?.measuredPeriodEnd} busy={busy} fading={fading} index={idx + 1} total={items.length} onReject={(a, b) => act(a, b, "reject", `pair-${a}-${b}`)} />
                    ) : (
                      <PairCard
                        p={primary}
                        measured={overview?.measuredPeriodEnd}
                        busy={busy}
                        fading={fading.has(key(primary))}
                        index={idx + 1}
                        total={items.length}
                        onAct={(a, b, action) => act(a, b, action, key(primary))}
                      />
                    )}
                    {secondary && <SecondaryPreview item={secondary} index={idx + 2} total={items.length} />}
                  </div>

                  <div className="mt-4 flex items-center justify-between">
                    <button className="btn-secondary disabled:opacity-50" disabled={idx === 0} onClick={() => setCurrent((c) => Math.max(0, c - 1))}>
                      &larr; Previous
                    </button>
                    <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{idx + 1} of {items.length} cases</p>
                    <button className="btn-secondary disabled:opacity-50" disabled={idx >= items.length - 1} onClick={() => setCurrent((c) => Math.min(items.length - 1, c + 1))}>
                      Next &rarr;
                    </button>
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

function SectionLabel({ tone = "review", children }) {
  const dot = tone === "brand" ? "var(--color-brand)" : tone === "flagged" ? "var(--color-flagged)" : "var(--color-review)";
  return (
    <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>
      <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: dot }} />
      {children}
    </p>
  );
}

// A compact, non-interactive look at the next case, so the page shows "what's coming" without
// listing every one of the 24 at once.
function SecondaryPreview({ item, index, total }) {
  const isPair = item.type === "pair";
  const title = isPair ? (item.rawNameA ?? item.rawNameB ?? "Name not disclosed") : (item.holdings[0]?.rawName ?? "Name not disclosed");
  return (
    <div className="rounded-[var(--radius-card)] border p-3 opacity-70" style={{ borderColor: "var(--color-border)", background: "var(--color-surface)" }}>
      <div className="flex items-center justify-between gap-2">
        <SectionLabel tone={isPair ? "brand" : "flagged"}>{isPair ? "Possible match" : "Group issue"}</SectionLabel>
        <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>{index}/{total}</span>
      </div>
      <p className="mt-1 text-sm font-medium uppercase" style={{ color: "var(--color-text)" }}>{title}</p>
    </div>
  );
}

// Likelihood colour follows the app's green/amber/red language: a high score reads as likely, the
// middle of the REVIEW band as worth a closer look, the low end as more likely not the same.
function likelihoodColor(pct) {
  if (pct >= 88) return "var(--color-brand)";
  if (pct >= 84) return "var(--color-review)";
  return "var(--color-flagged)";
}

function LikelihoodBar({ pct }) {
  const color = likelihoodColor(pct);
  return (
    <div>
      <p className="text-center text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>Match likelihood</p>
      <div className="relative mt-2 h-2 w-full rounded-full" style={{ background: "var(--color-border)" }}>
        <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${pct}%`, background: color }} />
        <div className="absolute top-1/2 h-3 w-3 -translate-y-1/2 -translate-x-1/2 rounded-full border-2" style={{ left: `${pct}%`, background: color, borderColor: "var(--color-surface)" }} />
      </div>
      <div className="mt-1 flex justify-between text-xs" style={{ color: "var(--color-text-muted)" }}>
        <span>Low</span>
        <span>High</span>
      </div>
      <p className="mt-1 text-center text-lg font-bold" style={{ color: "var(--color-text)" }}>{pct}%</p>
    </div>
  );
}

// E6's pair shape has no lender name (only a cluster's holdings carry bdcName) and no reported
// value (that only exists once holdings are matched into a facility), so a record shows only what
// the API actually returns for a review-queue pair: name, maturity, spread and a filing link.
function RecordBox({ label, name, maturity, spread, sourceUrl }) {
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: "var(--color-border)" }}>
      <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>{label}</p>
      <p className="mt-1 text-sm font-medium" style={{ color: "var(--color-text)" }}>{name ?? "Name not disclosed"}</p>
      <div className="mt-2 flex items-center justify-between text-sm">
        <span style={{ color: "var(--color-text-secondary)" }}>Maturity</span>
        <span style={{ color: "var(--color-text)" }}>{maturity ?? "Not disclosed"}</span>
      </div>
      <div className="mt-1 flex items-center justify-between text-sm">
        <span style={{ color: "var(--color-text-secondary)" }}>Spread</span>
        <span style={{ color: "var(--color-text)" }}>{bps(spread, "Not disclosed")}</span>
      </div>
      <p className="mt-2"><SourceLink url={sourceUrl}>View filing</SourceLink></p>
    </div>
  );
}

function PairCard({ p, measured, busy, fading, index, total, onAct }) {
  const pct = Math.round(Number(p.score) * 100);
  return (
    <Card className={fading ? "fade-out-card" : ""}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <SectionLabel tone="brand">Possible match<PeriodTag periodEnd={p.periodEnd} measured={measured} /></SectionLabel>
        <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>{index}/{total}</span>
      </div>
      <p className="mt-1 font-semibold uppercase" style={{ color: "var(--color-text)" }}>{p.rawNameA ?? p.rawNameB ?? "Name not disclosed"}</p>
      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>Are these two records the same borrower?</p>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <RecordBox label="Record A" name={p.rawNameA} maturity={p.maturityDateA} spread={p.spreadBpsA} sourceUrl={p.sourceUrlA} />
        <RecordBox label="Record B" name={p.rawNameB} maturity={p.maturityDateB} spread={p.spreadBpsB} sourceUrl={p.sourceUrlB} />
      </div>

      <div className="mt-4">
        <LikelihoodBar pct={pct} />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs" style={{ color: "var(--color-text-secondary)" }}>{typeName(p.instrumentType)}</span>
        <div className="flex gap-2">
          <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onAct(p.holdingIdA, p.holdingIdB, "reject")}>Not the same</button>
          <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onAct(p.holdingIdA, p.holdingIdB, "confirm")}>Same borrower</button>
        </div>
      </div>
    </Card>
  );
}

function ClusterCard({ c, measured, busy, fading, index, total, onReject }) {
  const [open, setOpen] = useState(false);
  const title = c.holdings[0]?.rawName ?? "Name not disclosed";
  const lender = c.holdings[0]?.bdcName ?? "Not disclosed";
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <SectionLabel tone="flagged">Group issue<PeriodTag periodEnd={c.periodEnd} measured={measured} /></SectionLabel>
        <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>{index}/{total}</span>
      </div>
      <p className="mt-1 font-semibold uppercase" style={{ color: "var(--color-text)" }}>{title}</p>
      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>Several records from the same lender were grouped together.</p>

      <div className="mt-3 flex items-center justify-between rounded-xl border p-3 text-sm" style={{ borderColor: "var(--color-border)" }}>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Lender</p>
          <p style={{ color: "var(--color-text)" }}>{lender}</p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Records</p>
          <p style={{ color: "var(--color-text)" }}>{c.holdings.length} {c.holdings.length === 1 ? "record" : "records"}</p>
        </div>
        <button type="button" className="text-sm font-medium hover:underline" style={{ color: "var(--color-brand-dark)" }} onClick={() => setOpen((o) => !o)}>
          {open ? "Hide details" : "View details"} &rarr;
        </button>
      </div>

      {open && (
        <div className="mt-3 space-y-3">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr style={{ color: "var(--color-text-secondary)" }}>
                  <th className="py-1.5 pr-4 font-medium">Record</th>
                  <th className="py-1.5 pr-4 font-medium">Maturity</th>
                  <th className="py-1.5 pr-4 font-medium">Spread</th>
                  <th className="py-1.5 pr-2 font-medium">Source</th>
                </tr>
              </thead>
              <tbody>
                {c.holdings.map((h) => (
                  <tr key={h.holdingId} className="border-t" style={{ borderColor: "var(--color-border)" }}>
                    <td className="py-1.5 pr-4" style={{ color: "var(--color-text)" }}>{h.rawName ?? "Name not disclosed"}</td>
                    <td className="py-1.5 pr-4" style={{ color: "var(--color-text)" }}>{h.maturityDate ?? "Not disclosed"}</td>
                    <td className="py-1.5 pr-4" style={{ color: "var(--color-text)" }}>{bps(h.spreadBps, "Not disclosed")}</td>
                    <td className="py-1.5 pr-2"><SourceLink url={h.sourceUrl}>View filing</SourceLink></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Technical details: pairs that formed this group</p>
            <ul className="mt-1 space-y-1.5 text-sm" style={{ color: "var(--color-text-secondary)" }}>
              {c.pairs.map((p) => (
                <li key={`${p.holdingIdA}-${p.holdingIdB}`} className={`flex flex-wrap items-center justify-between gap-2 ${fading.has(`pair-${p.holdingIdA}-${p.holdingIdB}`) ? "fade-out-card" : ""}`}>
                  <span>Holdings {p.holdingIdA} and {p.holdingIdB}, score {fixed(p.score, 2)}, {p.status}</span>
                  <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onReject(p.holdingIdA, p.holdingIdB)}>Separate this pair</button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Card>
  );
}
