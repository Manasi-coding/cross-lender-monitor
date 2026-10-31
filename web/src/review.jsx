import { useCallback, useEffect, useState } from "react";
import { ApiFailure, getJson, postJson } from "./api.js";
import { useShared } from "./App.jsx";
import { Card, CardLabel, EmptyState, Load, PageTitle, PeriodTag, SourceLink, StatCard, Toast, useFetch } from "./components.jsx";
import { clearDecisions, getDecisions, recordDecision } from "./decisions.js";
import { bps, typeName } from "./format.js";
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
  // A running count of decisions made from this browser, read from the local decisions log so it
  // survives a reload (the API has no "completed" concept of its own: a decided pair simply drops
  // out of the REVIEW queue, it is not counted anywhere server side).
  const [completed, setCompleted] = useState(() => getDecisions().length);
  // The queue size the first time it was fetched this session, so "To review" stays fixed while
  // "Remaining" (the live fetch) counts down as decisions are made.
  const [initialTotal, setInitialTotal] = useState(null);

  useEffect(() => setCurrent(0), [version]);
  useEffect(() => {
    if (f.state === "ready" && initialTotal === null) setInitialTotal(f.data.length);
  }, [f, initialTotal]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  // The card is only faded and the list only refetched after the write has actually succeeded,
  // never before. A failure leaves the card exactly as it was and shows the error instead.
  const act = useCallback(
    async (a, b, action, fadeKey, title, context) => {
      if (busy) return;
      setBusy(true);
      try {
        const result = await postJson(`/api/review-queue/${a}/${b}/${action}`);
        setNotice(null);
        recordDecision({ holdingIdA: result.holdingIdA, holdingIdB: result.holdingIdB, status: result.status, title, context });
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
      <PageTitle>Review queue</PageTitle>
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

          const toReview = initialTotal ?? items.length;
          const pct = (n) => (toReview === 0 ? 0 : Math.round((n / toReview) * 100));
          const reviewedPct = toReview === 0 ? 0 : Math.round((completed / toReview) * 100);

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
                  <CardLabel>Review queue</CardLabel>
                  <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{items.length} {items.length === 1 ? "case needs" : "cases need"} review</p>
                  <div className="mt-3 space-y-2.5">
                    {[
                      ["Possible match", matches.length, "var(--color-chart-green)"],
                      ["Group issue", groups.length, "var(--color-chart-red)"],
                    ].map(([label, n, color]) => (
                      <div key={label}>
                        <div className="mb-1 flex items-center justify-between text-sm">
                          <span style={{ color: "var(--color-text-secondary)" }}>{label}</span>
                          <span className="font-semibold" style={{ color: "var(--color-text)" }}>{n}</span>
                        </div>
                        <div className="h-2 w-full overflow-hidden rounded-full" style={{ background: "var(--color-border)" }}>
                          <div className="h-full rounded-full" style={{ width: `${pct(n)}%`, background: color }} />
                        </div>
                        <p className="mt-0.5 text-right text-xs" style={{ color: "var(--color-text-secondary)" }}>{pct(n)}%</p>
                      </div>
                    ))}
                  </div>
                </Card>
                <Card compact>
                  <CardLabel>Review progress</CardLabel>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <p className="text-xl font-bold" style={{ color: "var(--color-text)" }}>{toReview}</p>
                      <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>To review</p>
                    </div>
                    <div>
                      <p className="text-xl font-bold" style={{ color: "var(--color-chart-green)" }}>{completed}</p>
                      <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Completed</p>
                    </div>
                    <div>
                      <p className="text-xl font-bold" style={{ color: "var(--color-text)" }}>{items.length}</p>
                      <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Remaining</p>
                    </div>
                  </div>
                  <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full" style={{ background: "var(--color-border)" }}>
                    <div className="h-full rounded-full" style={{ width: `${reviewedPct}%`, background: "var(--color-chart-green)" }} />
                  </div>
                  <p className="mt-1.5 text-center text-xs" style={{ color: "var(--color-text-secondary)" }}>{reviewedPct}% reviewed</p>
                </Card>
              </div>

              <h2 className="mb-3 mt-5 text-lg font-semibold" style={{ color: "var(--color-text)" }}>Cases to review</h2>

              {items.length === 0 ? (
                <EmptyState>Nothing is waiting for review.</EmptyState>
              ) : (
                <>
                  <div className="space-y-3">
                    {primary.type === "cluster" ? (
                      <ClusterCard
                        c={primary}
                        measured={overview?.measuredPeriodEnd}
                        busy={busy}
                        fading={fading}
                        index={idx + 1}
                        total={items.length}
                        onReject={(a, b) => act(a, b, "reject", `pair-${a}-${b}`, primary.holdings[0]?.rawName ?? "Name not disclosed", "cluster")}
                      />
                    ) : (
                      <PairCard
                        p={primary}
                        measured={overview?.measuredPeriodEnd}
                        busy={busy}
                        fading={fading.has(key(primary))}
                        index={idx + 1}
                        total={items.length}
                        onAct={(a, b, action) => act(a, b, action, key(primary), primary.rawNameA ?? primary.rawNameB ?? "Name not disclosed", "pair")}
                      />
                    )}
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
  const dot = tone === "brand" ? "var(--color-chart-green)" : tone === "flagged" ? "var(--color-chart-red)" : "var(--color-chart-yellow)";
  return (
    <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>
      <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: dot }} />
      {children}
    </p>
  );
}

// A compact, non-interactive look at the next case, so the page shows "what's coming" without
// listing every one of the 24 at once.
// Likelihood colour follows the app's green/amber/red language: a high score reads as likely, the
// middle of the REVIEW band as worth a closer look, the low end as more likely not the same.
function likelihoodColor(pct) {
  if (pct >= 88) return "var(--color-chart-green)";
  if (pct >= 84) return "var(--color-chart-yellow)";
  return "var(--color-chart-red)";
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
  // Open by default: this is the one case on screen to act on, so its decision controls (the
  // per-pair reject buttons below) should not require an extra click to find.
  const [open, setOpen] = useState(true);
  // "Same" has no server action to call: a pair already sits in this cluster (AUTO or CONFIRMED),
  // so leaving it alone already means "same". This only fades the row from view locally, it is not
  // a decision E7/E8 would record, and is never written to the local decisions log.
  const [dismissedPairs, setDismissedPairs] = useState(() => new Set());
  const onDismiss = (a, b) => setDismissedPairs((prev) => new Set(prev).add(`${a}-${b}`));
  const byHoldingId = new Map(c.holdings.map((h) => [h.holdingId, h]));
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
          {open ? "Hide records" : "View records and decide"} &rarr;
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
            <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Are these the same record?</p>
            <p className="mt-0.5 text-xs" style={{ color: "var(--color-text-secondary)" }}>
              These pairs are already grouped together. Leave as is if they belong together, or mark a pair as not the same to split it out.
            </p>
            <ul className="mt-2 space-y-2">
              {c.pairs.map((p) => {
                const nameA = byHoldingId.get(p.holdingIdA)?.rawName ?? "Name not disclosed";
                const nameB = byHoldingId.get(p.holdingIdB)?.rawName ?? "Name not disclosed";
                const dismissed = dismissedPairs.has(`${p.holdingIdA}-${p.holdingIdB}`);
                return (
                  <li
                    key={`${p.holdingIdA}-${p.holdingIdB}`}
                    className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border p-2.5 text-sm ${fading.has(`pair-${p.holdingIdA}-${p.holdingIdB}`) || dismissed ? "fade-out-card" : ""}`}
                    style={{ borderColor: "var(--color-border)" }}
                  >
                    <span style={{ color: "var(--color-text)" }}>{nameA} <span style={{ color: "var(--color-text-muted)" }}>and</span> {nameB}</span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={busy}
                        className="btn-secondary disabled:opacity-50"
                        onClick={() => onDismiss(p.holdingIdA, p.holdingIdB)}
                      >
                        Same
                      </button>
                      <button disabled={busy} className="btn-secondary disabled:opacity-50" onClick={() => onReject(p.holdingIdA, p.holdingIdB)}>Not the same</button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ Decisions record
// A local, browser-stored history of review decisions. Every row is a real past Accept/Reject/
// Separate action this browser sent, built from the holdingIdA/holdingIdB/status that E7 or E8
// actually returned at the time. There is no server endpoint listing past decisions, so this is a
// local convenience record, not a database export, and it does not reflect decisions made from any
// other browser or device.
export function DecisionsPage() {
  const [entries, setEntries] = useState(() => getDecisions());

  const confirmedCount = entries.filter((e) => e.status === "CONFIRMED").length;
  const rejectedCount = entries.filter((e) => e.status === "REJECTED").length;

  return (
    <>
      <PageTitle>Decisions</PageTitle>
      <p className="mb-5 text-sm" style={{ color: "var(--color-text-secondary)" }}>
        A record of review decisions made from this browser. It is stored locally, not on the server, so it will not show decisions made elsewhere, and clearing it does not undo anything.
      </p>

      <div className="grid gap-5 sm:grid-cols-3">
        <StatCard label="Decisions logged" value={entries.length} tone="neutral" />
        <StatCard label="Same borrower / Accepted" value={confirmedCount} tone="brand" />
        <StatCard label="Not the same / Separated" value={rejectedCount} tone="flagged" />
      </div>

      <Card compact className="mt-5">
        <div className="flex items-center justify-between">
          <CardLabel>Decision log</CardLabel>
          {entries.length > 0 && (
            <button
              type="button"
              className="text-xs font-medium hover:underline"
              style={{ color: "var(--color-text-secondary)" }}
              onClick={() => {
                clearDecisions();
                setEntries([]);
              }}
            >
              Clear log
            </button>
          )}
        </div>
        {entries.length === 0 ? (
          <EmptyState>No decisions recorded in this browser yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr style={{ color: "var(--color-text-secondary)" }}>
                  <th className="py-1.5 pr-4 font-medium">When</th>
                  <th className="py-1.5 pr-4 font-medium">Case</th>
                  <th className="py-1.5 pr-4 font-medium">From</th>
                  <th className="py-1.5 pr-2 font-medium">Decision</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => {
                  const confirmed = e.status === "CONFIRMED";
                  return (
                    <tr key={`${e.holdingIdA}-${e.holdingIdB}-${e.at}-${i}`} className="border-t" style={{ borderColor: "var(--color-border)" }}>
                      <td className="py-2 pr-4 whitespace-nowrap" style={{ color: "var(--color-text-secondary)" }}>{new Date(e.at).toLocaleString()}</td>
                      <td className="py-2 pr-4 font-medium" style={{ color: "var(--color-text)" }}>{e.title ?? "Name not disclosed"}</td>
                      <td className="py-2 pr-4" style={{ color: "var(--color-text-secondary)" }}>{e.context === "cluster" ? "Group issue" : "Possible match"}</td>
                      <td className="py-2 pr-2">
                        <span className="inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: confirmed ? "var(--color-chart-green)" : "var(--color-chart-red)" }}>
                          <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: confirmed ? "var(--color-chart-green)" : "var(--color-chart-red)" }} />
                          {confirmed ? "Confirmed" : "Rejected"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
