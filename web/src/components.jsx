import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { FLAG_TEXT, NOT_YET, fixed, pct } from "./format.js";

// Refresh on focus; ignore responses from effects that have been cleaned up.
export function useFetch(load, deps) {
  const [s, setS] = useState({ state: "loading" });
  const [tick, setTick] = useState(0);
  const retry = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    let live = true;
    setS({ state: "loading" });
    load().then(
      (data) => live && setS({ state: "ready", data }),
      (error) => live && setS({ state: "error", error, retry }),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  useEffect(() => {
    const onFocus = () => retry();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [retry]);
  return s;
}

export function useCountUp(target, durationMs = 700) {
  const [value, setValue] = useState(() => (Number.isFinite(target) ? 0 : target));
  useEffect(() => {
    if (!Number.isFinite(target)) {
      setValue(target);
      return;
    }
    let raf;
    const start = performance.now();
    const from = 0;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - (1 - t) * (1 - t);
      setValue(from + (target - from) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else setValue(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs]);
  return value;
}

export function Skeleton() {
  return (
    <div className="animate-pulse space-y-3" aria-busy="true" aria-label="Loading">
      {[0, 1, 2].map((i) => <div key={i} className="h-16 rounded-2xl bg-[var(--color-border)]" />)}
    </div>
  );
}

export function ErrorState({ error, retry }) {
  return (
    <div role="alert" className="rounded-2xl border p-5" style={{ borderColor: "var(--color-flagged)", background: "var(--color-flagged-light)" }}>
      <p className="font-semibold" style={{ color: "var(--color-text)" }}>Something went wrong.</p>
      <p className="break-words text-sm" style={{ color: "var(--color-text-secondary)" }}>{error.message}</p>
      <button className="btn-secondary mt-3" onClick={retry}>Retry</button>
    </div>
  );
}

export function EmptyState({ children }) {
  return (
    <p className="rounded-2xl border border-dashed p-6 text-center text-sm" style={{ borderColor: "var(--color-border)", color: "var(--color-text-secondary)" }}>
      {children}
    </p>
  );
}

export function Load({ f, children }) {
  if (f.state === "loading") return <Skeleton />;
  if (f.state === "error") return <ErrorState error={f.error} retry={f.retry} />;
  return <>{children(f.data)}</>;
}

export const FLAG_STATUS = {
  AGREEMENT: { fg: "var(--color-brand-dark)", bg: "var(--color-brand-light)", faint: "var(--color-brand-faint)", dot: "var(--color-chart-green)" },
  MILD: { fg: "var(--color-review)", bg: "var(--color-review-light)", faint: "var(--color-review-faint)", dot: "var(--color-chart-yellow)" },
  FLAGGED: { fg: "var(--color-flagged)", bg: "var(--color-flagged-light)", faint: "var(--color-flagged-faint)", dot: "var(--color-chart-red)" },
};

export function Card({ children, to, onClick, compact = false, className = "", id }) {
  const base = `card-shadow rounded-[var(--radius-card)] border ${compact ? "p-3.5" : "p-5"} ${className}`;
  const style = { background: "var(--color-surface)", borderColor: "var(--color-border-strong)" };
  if (to) {
    return (
      <Link id={id} to={to} className={`block transition-colors hover:bg-[var(--color-brand-light)]/40 ${base}`} style={style}>
        {children}
      </Link>
    );
  }
  if (onClick) {
    return (
      <button id={id} type="button" onClick={onClick} className={`block w-full text-left transition-colors hover:bg-[var(--color-brand-light)]/40 ${base}`} style={style}>
        {children}
      </button>
    );
  }
  return <div id={id} className={base} style={style}>{children}</div>;
}

export function CardLabel({ children }) {
  return <p className="mb-3 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>{children}</p>;
}

const ICON_PATHS = {
  layers: "M10 2 2 6l8 4 8-4-8-4ZM2 10l8 4 8-4M2 14l8 4 8-4",
  flag: "M4 17V3m0 2h11l-2.5 3L15 11H4",
  alert: "M10 2 2 17h16L10 2ZM10 8v4m0 3h.01",
  check: "M3 10.5 8 15l9-10.5",
  chart: "M3 17V8m5 9V3m5 14v-6m5 6V6",
  search: "M9 16a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM18 18l-4-4",
  doc: "M5 2h7l4 4v12H5V2Zm7 0v4h4",
  grid: "M3 3h6v6H3V3Zm8 0h6v6h-6V3ZM3 11h6v6H3v-6Zm8 0h6v6h-6v-6Z",
};

export function Icon({ name, size = 18, className = "" }) {
  const d = ICON_PATHS[name];
  if (!d) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

const TONE = {
  neutral: { bg: "var(--color-brand-light)", fg: "var(--color-brand-dark)" },
  brand: { bg: "var(--color-brand-light)", fg: "var(--color-brand-dark)" },
  review: { bg: "var(--color-review-light)", fg: "var(--color-review)" },
  flagged: { bg: "var(--color-flagged-light)", fg: "var(--color-flagged)" },
};

export function StatCard({ label, value, countTo, format, to, onClick, note, tone = "neutral", icon, compact = false }) {
  const t = TONE[tone] ?? TONE.neutral;
  const animated = useCountUp(countTo ?? NaN);
  const shown = Number.isFinite(countTo) ? format(animated) : value;
  return (
    <Card to={to} onClick={onClick} compact={compact}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>{label}</p>
          <p className={`mt-2 font-bold leading-none tabular-nums ${compact ? "text-xl" : "text-[28px]"}`} style={{ color: "var(--color-text)" }}>{shown}</p>
          {note && <p className="mt-1.5 text-sm" style={{ color: "var(--color-text-secondary)" }}>{note}</p>}
        </div>
        {icon && (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full" style={{ background: t.bg, color: t.fg }}>
            <Icon name={icon} />
          </span>
        )}
      </div>
    </Card>
  );
}

export function HeroCard({ eyebrow, title, subtitle, actions }) {
  return (
    <div className="hero-solid card-shadow rounded-[var(--radius-card)] p-6 sm:p-7" style={{ color: "var(--color-brand-dark)" }}>
      {eyebrow && <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-brand-dark)", opacity: 0.75 }}>{eyebrow}</p>}
      {title && <p className="mt-2 text-2xl font-bold leading-snug sm:text-[28px]">{title}</p>}
      {subtitle && <p className="mt-2 max-w-xl text-sm" style={{ opacity: 0.85 }}>{subtitle}</p>}
      {actions && <div className="mt-5 flex flex-wrap gap-2.5">{actions}</div>}
    </div>
  );
}

export function HeroLink({ to, children }) {
  return (
    <Link
      to={to}
      className="rounded-xl px-4 py-2 text-sm font-semibold transition-colors"
      style={{ background: "rgba(22, 48, 31, 0.14)", color: "var(--color-brand-dark)" }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(22, 48, 31, 0.22)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(22, 48, 31, 0.14)")}
    >
      {children}
    </Link>
  );
}

export function DivergenceDonut({ agreement, mild, flagged }) {
  const total = agreement + mild + flagged;
  const r = 15.9155;
  const c = 2 * Math.PI * r;
  const segs = [
    ["AGREEMENT", agreement, "var(--color-chart-green)"],
    ["MILD", mild, "var(--color-chart-yellow)"],
    ["FLAGGED", flagged, "var(--color-chart-red)"],
  ];
  let offset = 0;
  const sharePct = (n) => (total === 0 ? null : Math.round((n / total) * 100));
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="relative h-32 w-32 shrink-0">
        <svg viewBox="0 0 36 36" className="h-32 w-32 -rotate-90" role="img" aria-label="Share of facilities by agreement status">
          <circle cx="18" cy="18" r={r} fill="none" stroke="var(--color-border)" strokeWidth="4" />
          {total > 0 &&
            segs.map(([name, n, color]) => {
              if (n === 0) return null;
              const frac = n / total;
              const dash = `${frac * c} ${c - frac * c}`;
              const el = <circle key={name} cx="18" cy="18" r={r} fill="none" stroke={color} strokeWidth="4" strokeDasharray={dash} strokeDashoffset={-offset} strokeLinecap="butt" />;
              offset += frac * c;
              return el;
            })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold leading-none" style={{ color: "var(--color-text)" }}>{total}</span>
          <span className="mt-1 text-[11px] font-medium uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Facilities</span>
        </div>
      </div>
      <div className="min-w-[160px] flex-1 space-y-3 text-sm">
        {segs.map(([name, n, color]) => {
          const p = sharePct(n);
          return (
            <div key={name} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
                <span style={{ color: "var(--color-text-secondary)" }}>{FLAG_TEXT[name]}</span>
              </span>
              <span style={{ color: "var(--color-text)" }}>
                <span className="font-semibold">{n}</span>
                {p !== null && <span className="ml-1.5 text-xs" style={{ color: "var(--color-text-muted)" }}>({p}%)</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ClickableDivergenceBar({ agreement, mild, flagged }) {
  const total = agreement + mild + flagged;
  const segs = [
    ["AGREEMENT", agreement],
    ["MILD", mild],
    ["FLAGGED", flagged],
  ];
  if (total === 0) return null;
  return (
    <div>
      <div className="flex h-3.5 w-full overflow-hidden rounded-full" style={{ background: "var(--color-border)" }}>
        {segs.map(([flag, n]) => {
          if (n === 0) return null;
          const s = FLAG_STATUS[flag];
          return (
            <Link
              key={flag}
              to={`/facilities?flag=${flag}`}
              title={`${FLAG_TEXT[flag]}: ${n} facilities. View in Triage.`}
              aria-label={`${FLAG_TEXT[flag]}, ${n} facilities. View in Triage.`}
              className="h-full transition-opacity hover:opacity-80 focus-visible:opacity-80"
              style={{ width: `${(n / total) * 100}%`, background: s.dot }}
            />
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-xs">
        {segs.map(([flag, n]) => {
          const s = FLAG_STATUS[flag];
          return (
            <Link key={flag} to={`/facilities?flag=${flag}`} className="flex items-center gap-1.5 hover:underline" style={{ color: "var(--color-text-secondary)" }}>
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: s.dot }} />
              {FLAG_TEXT[flag]} ({n})
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export function Toast({ children }) {
  return (
    <div role="status" aria-live="polite" className="fixed bottom-5 right-5 z-50 rounded-xl border px-4 py-2.5 text-sm font-medium shadow-lg animate-toast-in" style={{ background: "var(--color-brand-dark)", borderColor: "var(--color-brand-dark)", color: "#ffffff" }}>
      {children}
    </div>
  );
}

export function RangeBar({ ci: c }) {
  if (!c) return null;
  const lowPct = Math.max(0, Math.min(100, c.low * 100));
  const highPct = Math.max(0, Math.min(100, c.high * 100));
  const valuePct = Math.max(0, Math.min(100, c.value * 100));
  return (
    <div className="mt-1.5" aria-hidden="true">
      <div className="relative h-2 w-full rounded-full" style={{ background: "var(--color-border)" }}>
        <div className="absolute inset-y-0 rounded-full" style={{ left: `${lowPct}%`, width: `${Math.max(0, highPct - lowPct)}%`, background: "var(--color-chart-green)", opacity: 0.5 }} />
        <div className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2" style={{ left: `${valuePct}%`, background: "var(--color-chart-green-dark)", borderColor: "var(--color-surface)" }} />
      </div>
    </div>
  );
}

export function PeriodTag({ periodEnd, measured }) {
  return measured && periodEnd !== measured ? (
    <span className="ml-2 rounded-full border px-2 py-0.5 text-xs" style={{ borderColor: "var(--color-border)", color: "var(--color-text-secondary)" }}>
      Outside measured quarter
    </span>
  ) : null;
}

export function SourceLink({ url, children = "View filing" }) {
  return (
    <a className="font-medium underline-offset-2 hover:underline" style={{ color: "var(--color-brand-dark)" }} href={url} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}

export function StatusPill({ flag }) {
  const s = FLAG_STATUS[flag] ?? { fg: "var(--color-text-secondary)", bg: "var(--color-border)", dot: "var(--color-text-secondary)" };
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold" style={{ color: s.fg, background: s.bg }}>
      <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: s.dot }} />
      {FLAG_TEXT[flag] ?? flag}
    </span>
  );
}

export function StatusDot({ flag, label }) {
  const s = FLAG_STATUS[flag] ?? { dot: "var(--color-text-secondary)" };
  return <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: s.dot }} role="img" aria-label={label ?? FLAG_TEXT[flag] ?? flag} title={label ?? FLAG_TEXT[flag] ?? flag} />;
}

export function BarList({ rows, compact = false }) {
  const total = Math.max(1, rows.reduce((sum, r) => sum + r.value, 0));
  return (
    <div className={compact ? "space-y-2" : "space-y-3"}>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-3">
          <span className="w-20 shrink-0 text-xs font-medium" style={{ color: "var(--color-text-secondary)" }}>{r.label}</span>
          <div className={`${compact ? "h-2" : "h-2.5"} flex-1 overflow-hidden rounded-full`} style={{ background: "var(--color-border)" }}>
            <div className="h-full rounded-full" style={{ width: `${(r.value / total) * 100}%`, background: r.color }} />
          </div>
          <span className="w-8 shrink-0 text-right text-sm font-semibold" style={{ color: "var(--color-text)" }}>{r.value}</span>
        </div>
      ))}
    </div>
  );
}

export function DivergenceSplitChart({ agreement, mild, flagged }) {
  return (
    <BarList
      rows={[
        { label: FLAG_TEXT.AGREEMENT, value: agreement, color: FLAG_STATUS.AGREEMENT.dot },
        { label: FLAG_TEXT.MILD, value: mild, color: FLAG_STATUS.MILD.dot },
        { label: FLAG_TEXT.FLAGGED, value: flagged, color: FLAG_STATUS.FLAGGED.dot },
      ]}
    />
  );
}

export function RankedShareList({ rows, total }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="space-y-3">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-3">
          <span className="w-44 shrink-0 truncate text-sm font-medium sm:w-56" style={{ color: "var(--color-text)" }} title={r.label}>{r.label}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full" style={{ background: "var(--color-border)" }}>
            <div className="h-full rounded-full" style={{ width: `${(r.value / max) * 100}%`, background: "var(--color-chart-red)" }} />
          </div>
          <span className="w-10 shrink-0 text-right text-xs font-semibold" style={{ color: "var(--color-text-secondary)" }}>
            {total ? `${((r.value / total) * 100).toFixed(0)}%` : r.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export function ci(c, interval = "95% interval") {
  return c ? `${pct(c.value)} (${interval} ${pct(c.low)} to ${pct(c.high)}, n ${c.n})` : NOT_YET;
}

// kind "recall" labels the two UNSURE treatments by what they do, because counting UNSURE as no match raises recall (no worst or best wording).
// weighted marks a band weighted figure: its interval is a bootstrap over bands, which has zero width when every sampled AUTO label is a match.
export function RangeStat({ title, range, kind = "precision", weighted = false }) {
  if (!range) return <Card><p className="font-semibold">{title}</p><p>{NOT_YET}</p></Card>;
  const lines = [
    ["UNSURE excluded (headline)", range.unsureExcluded],
    [kind === "recall" ? "UNSURE counted as no match" : "Worst case, UNSURE counted as no match", range.unsureAsNoMatch],
    [kind === "recall" ? "UNSURE counted as match" : "Best case, UNSURE counted as match", range.unsureAsMatch],
  ];
  const interval = weighted ? "bootstrap, weighted, 95% interval" : "95% interval";
  const known = lines.map(([, c]) => c).filter((c) => c !== null).sort((a, b) => a.value - b.value);
  return (
    <Card>
      <p className="font-semibold">{title}</p>
      {known.length >= 2 && <p className="text-sm">Range across treatments: {pct(known[0].value)} to {pct(known[known.length - 1].value)}</p>}
      <ul className="mt-1 space-y-2.5">
        {lines.map(([label, c]) => (
          <li key={label}>
            <span className="font-medium">{label}:</span> {ci(c, interval)}
            <RangeBar ci={c} />
          </li>
        ))}
      </ul>
      {weighted && <p className="mt-1 text-xs">The bootstrap interval has zero width when every sampled AUTO label is a match.</p>}
    </Card>
  );
}

export function BandTable({ bands }) {
  const name = (n) => ({ AUTO: "AUTO", REVIEW: "REVIEW", JUST_BELOW: "Just below", LOW: "Low" })[n] ?? n;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr><th className="p-1">Band</th><th className="p-1">Band size</th><th className="p-1">Sample</th><th className="p-1">Match</th><th className="p-1">No match</th><th className="p-1">Unsure</th><th className="p-1">Match rate</th></tr>
        </thead>
        <tbody>
          {bands.map((b) => (
            <tr key={b.name} className="border-t">
              <td className="p-1">{name(b.name)}</td>
              <td className="p-1">{b.bandSize}</td>
              <td className="p-1">{b.sampleSize}{b.labeledInFull ? " (all)" : ""}</td>
              <td className="p-1">{b.counts.match}</td>
              <td className="p-1">{b.counts.noMatch}</td>
              <td className="p-1">{b.counts.unsure}</td>
              <td className="p-1">
                {b.matchRate ? ci(b.matchRate.unsureExcluded) : b.sampleSize === 0 ? "Not sampled" : `Counts only: ${b.counts.match} of ${b.sampleSize} matched`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function range(values) {
  return [Math.min(...values), Math.max(...values)];
}

const DOT_COLORS = ["var(--color-chart-green-dark)", "var(--color-chart-green)", "#15803d", "#4ade80"];

// Zoom the shared axis around the reported marks to make small gaps visible.
export function LenderValueBars({ rows }) {
  const [lo, hi] = range(rows.map((r) => r.value));
  const pad = Math.max((hi - lo) * 0.4, 0.3);
  const axisMin = Math.max(0, lo - pad), axisMax = Math.min(100, hi + pad);
  const axisMid = (axisMin + axisMax) / 2;
  const widthPct = (v) => ((v - axisMin) / (axisMax - axisMin)) * 100;
  const summary = `Reported value by lender: ${rows.map((r) => `${r.label} ${r.value.toFixed(2)} percent`).join(", ")}.`;
  return (
    <div role="img" aria-label={summary}>
      <div aria-hidden="true">
        <div className="space-y-3">
          {rows.map((r, i) => (
            <div key={r.label}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="font-medium" style={{ color: "var(--color-text)" }}>{r.label}</span>
                <span className="font-semibold" style={{ color: "var(--color-text)" }}>{r.value.toFixed(2)}%</span>
              </div>
              <div className="h-2.5 w-full overflow-hidden rounded-full" style={{ background: "var(--color-border)" }}>
                <div className="h-full rounded-full" style={{ width: `${widthPct(r.value)}%`, background: DOT_COLORS[i % DOT_COLORS.length] }} />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-2 flex justify-between text-xs" style={{ color: "var(--color-text-muted)" }}>
          <span>{axisMin.toFixed(1)}%</span>
          <span>{axisMid.toFixed(1)}%</span>
          <span>{axisMax.toFixed(1)}%</span>
        </div>
      </div>
    </div>
  );
}

export function PageTitle({ children, sub }) {
  return (
    <div className="mb-6">
      <h1 className="text-[28px] font-bold leading-tight" style={{ color: "var(--color-text)" }}>{children}</h1>
      {sub && <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>{sub}</p>}
    </div>
  );
}

export const inputClass = "w-full rounded-xl border px-3.5 py-2 text-sm outline-none transition-colors placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-brand)]";
export const inputStyle = { background: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" };
