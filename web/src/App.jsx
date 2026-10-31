import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import { getJson } from "./api.js";

const Ctx = createContext({ overview: null, refresh: () => {} });
export const useShared = () => useContext(Ctx);

const NAV = [
  ["/", "Overview"],
  ["/borrowers", "Borrowers"],
  ["/facilities", "Triage"],
  ["/review", "Review"],
  ["/metrics", "Metrics"],
  ["/filings", "Filings"],
];

function readTheme() {
  try {
    return window.localStorage.getItem("theme") ?? "light";
  } catch {
    return "light";
  }
}

export default function App() {
  const [overview, setOverview] = useState(null);
  const [failed, setFailed] = useState(false);
  const [theme, setTheme] = useState(readTheme);
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  const refresh = useCallback(() => {
    getJson("/api/overview").then(
      (o) => {
        setOverview(o);
        setFailed(false);
      },
      () => setFailed(true),
    );
  }, []);
  useEffect(refresh, [refresh]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem("theme", theme);
    } catch {
      // storage can be blocked; the toggle still works for this visit
    }
  }, [theme]);

  const search = (e) => {
    e.preventDefault();
    navigate(q.trim() ? `/borrowers?search=${encodeURIComponent(q.trim())}` : "/borrowers");
  };

  return (
    <Ctx.Provider value={{ overview, refresh }}>
      <div className="flex min-h-screen flex-col md:flex-row" style={{ background: "var(--color-bg)" }}>
        <nav
          className="flex flex-col border-b p-5 md:w-60 md:shrink-0 md:border-b-0 md:border-r"
          style={{ borderColor: "var(--color-border)", background: "var(--color-surface)" }}
          aria-label="Main"
        >
          <p className="mb-6 text-sm font-bold uppercase tracking-wide leading-tight" style={{ color: "var(--color-text)" }}>
            Valuation<br />Monitor
          </p>
          <ul className="flex flex-wrap gap-1.5 md:block md:space-y-1">
            {NAV.map(([to, label]) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    `flex items-center justify-between gap-2 rounded-xl px-3 py-2 text-sm font-medium transition-colors ${
                      isActive ? "" : "hover:bg-[var(--color-brand-light)]"
                    }`
                  }
                  style={({ isActive }) => ({
                    color: isActive ? "var(--color-brand-dark)" : "var(--color-text-secondary)",
                    background: isActive ? "var(--color-brand-light)" : "transparent",
                  })}
                >
                  <span>{label}</span>
                  {label === "Review" && overview && overview.pendingReviewCount > 0 && (
                    <span
                      className="rounded-full px-1.5 py-0.5 text-xs font-semibold"
                      style={{ background: "var(--color-review-light)", color: "var(--color-review)" }}
                    >
                      {overview.pendingReviewCount}
                    </span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
          {overview && (
            <div className="mt-6 hidden space-y-1 border-t pt-4 text-xs md:block" style={{ borderColor: "var(--color-border)", color: "var(--color-text-secondary)" }}>
              <p>{overview.bdcCount} {overview.bdcCount === 1 ? "Lender" : "Lenders"}</p>
              <p>{overview.quarterCount} {overview.quarterCount === 1 ? "Quarter" : "Quarters"}</p>
            </div>
          )}
        </nav>
        <div className="min-w-0 flex-1 p-6 md:p-8">
          <header className="mb-6 flex items-center gap-3">
            <form onSubmit={search} className="flex-1" role="search">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search borrowers, facilities or lenders"
                aria-label="Search borrowers, facilities or lenders"
                maxLength={200}
                className="w-full max-w-md rounded-xl border px-3.5 py-2 text-sm outline-none transition-colors placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-brand)]"
                style={{ background: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" }}
              />
            </form>
            <button className="btn-secondary" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">
              {theme === "dark" ? "Light" : "Dark"}
            </button>
          </header>
          {failed && (
            <p role="alert" className="mb-5 rounded-2xl border p-3 text-sm" style={{ borderColor: "var(--color-flagged)", background: "var(--color-flagged-light)", color: "var(--color-flagged)" }}>
              The overview could not be loaded, so counts and period tags are hidden.
            </p>
          )}
          <main>
            <Outlet />
          </main>
        </div>
      </div>
    </Ctx.Provider>
  );
}
